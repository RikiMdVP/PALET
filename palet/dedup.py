"""Deduplication of records (WP4).

Pass 1 merges records with the same normalised DOI. Pass 2 compares titles:
two records are merged when their titles are near-identical, they share an
author surname and their years differ by at most one. Pairs that look alike
but do not meet every condition are reported for human review and are never
merged automatically.
"""

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from palet.models import Record, author_surname, normalize_title

MERGE_THRESHOLD = 0.92
REVIEW_THRESHOLD = 0.85

_NUMBERING = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
              "part", "volume", "vol", "one", "two", "three"}


def title_variants(title: str) -> list[str]:
    """Normalised title plus each part of a bilingual title.

    Scopus writes translated titles as ``English title; [Título original]``.
    """
    variants = []
    for part in [title, *re.split(r"[;\[\]]", title or "")]:
        normalized = normalize_title(part)
        if len(normalized) >= 15 and normalized not in variants:
            variants.append(normalized)
    return variants or [normalize_title(title)]


def title_similarity(title_a: str, title_b: str) -> float:
    """Best similarity (0-1) between any two variants of the titles."""
    best = 0.0
    for a in title_variants(title_a):
        for b in title_variants(title_b):
            if not a or not b:
                continue
            # token_set_ratio ignores word order and repeated words, but it is
            # 100 when one title is contained in the other, so the plain ratio
            # must agree too.
            score = min(fuzz.token_set_ratio(a, b), fuzz.token_sort_ratio(a, b)) / 100
            best = max(best, score)
    return best


def _numbering_differs(title_a: str, title_b: str) -> bool:
    """True when the titles differ in a number or series marker (Part I / Part II)."""
    tokens_a, tokens_b = set(normalize_title(title_a).split()), set(normalize_title(title_b).split())
    for token in tokens_a ^ tokens_b:
        if token.isdigit() or token in _NUMBERING:
            return True
    return False


def surname_tokens(record: Record) -> set[str]:
    """Words of all author surnames (handles double surnames written in part)."""
    tokens = set()
    for author in record.authors:
        tokens.update(t for t in author_surname(author).split() if len(t) >= 3)
    return tokens


def _richness(record: Record) -> tuple:
    """Sort key: prefer the record with a DOI, then the one with more metadata."""
    filled = sum(bool(v) for v in (record.abstract, record.authors, record.year, record.source_title,
                                   record.keywords, record.language, record.doc_type))
    return (record.doi is not None, filled, len(record.abstract or ""))


@dataclass
class DoubtfulPair:
    record_id_a: str
    record_id_b: str
    title_a: str
    title_b: str
    similarity: float
    reason: str


@dataclass
class DedupResult:
    records: list[Record]                       # unique records, in input order
    duplicates: list[Record]                    # removed records, status="duplicate"
    merges: list[dict] = field(default_factory=list)
    doubtful: list[DoubtfulPair] = field(default_factory=list)

    @property
    def stats(self) -> dict:
        by_rule: dict = {}
        for merge in self.merges:
            by_rule[merge["rule"]] = by_rule.get(merge["rule"], 0) + 1
        return {
            "input": len(self.records) + len(self.duplicates),
            "unique": len(self.records),
            "duplicates_removed": len(self.duplicates),
            "merged_by_rule": by_rule,
            "doubtful_pairs": len(self.doubtful),
        }


def _merge(keep: Record, drop: Record) -> tuple[Record, Record]:
    queries = keep.found_by_queries + [q for q in drop.found_by_queries if q not in keep.found_by_queries]
    merged = keep.model_copy(update={
        "merged_from": keep.merged_from + [drop.record_id] + drop.merged_from,
        "found_by_queries": queries,
        "abstract": keep.abstract or drop.abstract,
        "doi": keep.doi or drop.doi,
        "issn": keep.issn + [i for i in drop.issn if i not in keep.issn],
        "source_title": keep.source_title or drop.source_title,
    })
    return merged, drop.model_copy(update={"status": "duplicate"})


def deduplicate(records: list[Record]) -> DedupResult:
    kept: list[Record] = []
    duplicates: list[Record] = []
    merges: list[dict] = []
    doubtful: list[DoubtfulPair] = []

    def absorb(index: int, incoming: Record, rule: str, similarity: float) -> None:
        current = kept[index]
        keep, drop = (current, incoming) if _richness(current) >= _richness(incoming) else (incoming, current)
        merged, dropped = _merge(keep, drop)
        kept[index] = merged
        duplicates.append(dropped)
        merges.append({"kept": merged.record_id, "dropped": dropped.record_id,
                       "rule": rule, "similarity": round(similarity, 3)})

    for record in records:
        # Pass 1: same DOI (record_id is the normalised DOI) or same content hash.
        same_id = next((i for i, k in enumerate(kept) if k.record_id == record.record_id), None)
        if same_id is not None:
            absorb(same_id, record, "same_id", 1.0)
            continue

        # Pass 2: near-identical title + shared author surname + close year.
        match, review = None, []
        for i, candidate in enumerate(kept):
            similarity = title_similarity(record.title, candidate.title)
            if similarity < REVIEW_THRESHOLD:
                continue
            # Two different DOIs may still be one work (preprint and article),
            # but that is for a person to decide.
            different_dois = bool(record.doi and candidate.doi)
            shares_author = bool(surname_tokens(record) & surname_tokens(candidate))
            close_year = (record.year is None or candidate.year is None
                          or abs(record.year - candidate.year) <= 1)
            numbering = _numbering_differs(record.title, candidate.title)
            if (similarity >= MERGE_THRESHOLD and shares_author and close_year
                    and not numbering and not different_dois):
                match = (i, similarity)
                break
            reasons = []
            if similarity < MERGE_THRESHOLD:
                reasons.append("similar but not near-identical titles")
            if not shares_author:
                reasons.append("no shared author surname")
            if not close_year:
                reasons.append("years differ by more than one")
            if numbering:
                reasons.append("titles differ in a number or part marker")
            if different_dois:
                reasons.append("different DOIs")
            review.append((candidate, similarity, "; ".join(reasons)))

        if match is not None:
            absorb(match[0], record, "title_author_year", match[1])
            continue

        for candidate, similarity, reason in review:
            doubtful.append(DoubtfulPair(candidate.record_id, record.record_id,
                                         candidate.title, record.title, round(similarity, 3), reason))
        kept.append(record)

    return DedupResult(records=kept, duplicates=duplicates, merges=merges, doubtful=doubtful)
