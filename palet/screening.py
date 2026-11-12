"""Title-and-abstract screening against explicit eligibility criteria (WP5).

The model judges each criterion separately and quotes its evidence. The
decision (include / exclude / unclear) is taken here, in code, and so is the
check that every quote really appears in the record. Two independent
screeners judge each record; anything they do not agree on goes to a person.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from rapidfuzz import fuzz

from palet import llm
from palet.errors import PaletConfigError
from palet.models import Record, normalize_title
from palet.protocol import Criterion, Protocol

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "screen_system_v1.txt"

# Criteria on these dimensions are checked against metadata, not by the model.
METADATA_DIMENSIONS = {"study_type", "language", "period"}

# Order in which the reason for an exclusion is chosen when several apply.
REASON_PRECEDENCE = [
    "WRONG_DOC_TYPE", "WRONG_LANGUAGE", "OUT_OF_PERIOD",
    "WRONG_CONTEXT", "WRONG_CONCEPT", "WRONG_PHENOMENON", "NO_POLICY_CONTENT",
]
NO_ABSTRACT = "NO_ABSTRACT"

QUOTE_THRESHOLD = 0.90
MAX_ATTEMPTS = 3

Met = Literal["yes", "no", "unclear"]
Decision = Literal["include", "exclude", "unclear", "error"]


class CriterionJudgement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    met: Met
    evidence_quote: Optional[str] = None
    quote_verified: bool = False
    rationale: str = ""


class ScreeningDecision(BaseModel):
    """What one screener concluded about one record."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    screener: str                      # "A:claude-opus-5-5", "metadata", "human:RMVP"
    judgements: list[CriterionJudgement] = Field(default_factory=list)
    decision: Decision
    reason_code: Optional[str] = None
    failed_reasons: list[str] = Field(default_factory=list)   # every reason this screener found
    notes: str = ""
    prompt_sha256: Optional[str] = None
    decided_at: Optional[str] = None   # None for rules applied to metadata (they have no date)


class FinalDecision(BaseModel):
    """Outcome for one record after combining the screeners."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    decision: Literal["include", "exclude", "pending"]
    reason_code: Optional[str] = None
    reasons_shared: Optional[bool] = None   # exclusions by agreement: did both screeners give this reason?
    decided_by: str                    # "metadata", "agreement", "human:RMVP", "pending"
    pending_reason: Optional[str] = None
    screener_decisions: dict[str, str] = Field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Prompt ──────────────────────────────────────────────────────────────────

def llm_criteria(protocol: Protocol) -> list[Criterion]:
    """Criteria the model judges (everything not decidable from metadata)."""
    return [c for c in protocol.criteria if c.dimension not in METADATA_DIMENSIONS]


def build_system_prompt(protocol: Protocol) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    questions = "\n".join(f"- {key}: {text}" for key, text in protocol.research_questions.items())
    lines = []
    for criterion in llm_criteria(protocol):
        kind = "INCLUSION" if criterion.kind == "include" else "EXCLUSION"
        lines.append(f"- {criterion.id} | {kind} | {criterion.dimension} | {criterion.rule}")
        if criterion.examples_in:
            lines.append(f"    examples that satisfy it: {'; '.join(criterion.examples_in)}")
        if criterion.examples_out:
            lines.append(f"    examples that do not: {'; '.join(criterion.examples_out)}")
    return (template
            .replace("{{REVIEW_TITLE}}", protocol.title)
            .replace("{{RESEARCH_QUESTIONS}}", questions)
            .replace("{{CRITERIA}}", "\n".join(lines)))


def build_user_message(record: Record) -> str:
    keywords = "; ".join(record.keywords) if record.keywords else "(none)"
    return (f"Record ID: {record.record_id}\n"
            f"Title: {record.title}\n"
            f"Author keywords: {keywords}\n"
            f"Abstract: {record.abstract}")


def screened_text(record: Record) -> str:
    """The text a screener sees; quotes are verified against it."""
    return " ".join([record.title or "", "; ".join(record.keywords), record.abstract or ""])


# ── Quote verification ──────────────────────────────────────────────────────

def quote_is_in_text(quote: Optional[str], text: str, threshold: float = QUOTE_THRESHOLD) -> bool:
    """True when the quote appears in the text, allowing for minor differences
    in punctuation, case, accents and line breaks (fuzzy match >= threshold)."""
    quote_norm, text_norm = normalize_title(quote), normalize_title(text)
    if len(quote_norm) < 8 or not text_norm:
        return False
    if quote_norm in text_norm:
        return True
    return fuzz.partial_ratio(quote_norm, text_norm) / 100 >= threshold


# ── Decision rule ───────────────────────────────────────────────────────────

def reason_for(criterion: Criterion) -> str:
    return criterion.reason_code or f"FAILED_{criterion.id}"


def _first_by_precedence(codes: list[str]) -> str:
    return min(codes, key=lambda code: (REASON_PRECEDENCE.index(code)
                                        if code in REASON_PRECEDENCE else len(REASON_PRECEDENCE), code))


def decide(protocol: Protocol, judgements: list[CriterionJudgement]) -> tuple[str, Optional[str], str, list[str]]:
    """Apply the decision rule to verified judgements.

    Returns (decision, reason_code, notes, all failed reasons). The rule
    favours sensitivity:

    * exclude  — an inclusion criterion is "no", or an exclusion criterion is
                 "yes" with a verified quote;
    * include  — every inclusion criterion is "yes" with a verified quote and
                 every exclusion criterion is "no";
    * unclear  — anything else, including any "yes" whose quote could not be
                 found in the record.
    """
    by_id = {j.criterion_id: j for j in judgements}
    failing, doubts = [], []

    for criterion in llm_criteria(protocol):
        judgement = by_id[criterion.id]
        needs_quote = judgement.met == "yes"
        if needs_quote and not judgement.quote_verified:
            doubts.append(f"{criterion.id}: quote not found in the record")
            continue
        if judgement.met == "unclear":
            doubts.append(f"{criterion.id}: unclear")
        elif criterion.kind == "include" and judgement.met == "no":
            failing.append(reason_for(criterion))
        elif criterion.kind == "exclude" and judgement.met == "yes":
            failing.append(reason_for(criterion))

    failing = sorted(set(failing), key=lambda code: (_first_by_precedence([code, *failing]) != code, code))
    if failing:
        return "exclude", _first_by_precedence(failing), "", failing
    if doubts:
        return "unclear", None, "; ".join(doubts), []
    return "include", None, "", []


def metadata_decision(protocol: Protocol, record: Record) -> Optional[ScreeningDecision]:
    """Decide from metadata alone when that is enough; None otherwise."""
    reason = None
    if record.doc_type and protocol.document_types and record.doc_type not in protocol.document_types:
        reason = "WRONG_DOC_TYPE"
    elif record.language and protocol.languages and record.language not in protocol.languages:
        reason = "WRONG_LANGUAGE"
    elif record.year is not None and (
            (protocol.year_from and record.year < protocol.year_from)
            or (protocol.year_to and record.year > protocol.year_to)):
        reason = "OUT_OF_PERIOD"

    if reason:
        return ScreeningDecision(record_id=record.record_id, screener="metadata", decision="exclude",
                                 reason_code=reason,
                                 notes=f"type={record.doc_type}, language={record.language}, year={record.year}")
    if not record.abstract or not record.abstract.strip():
        # Not an exclusion: a person decides from the title (or retrieves the abstract).
        return ScreeningDecision(record_id=record.record_id, screener="metadata", decision="unclear",
                                 reason_code=NO_ABSTRACT, notes="no abstract available")
    return None


# ── One screener, one record ────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in the reply")
    return json.loads(text[start:end + 1])


def parse_judgements(reply: str, protocol: Protocol) -> list[CriterionJudgement]:
    """Validate the model reply: exactly one well-formed judgement per criterion."""
    data = _extract_json(reply)
    raw = data.get("judgements")
    if not isinstance(raw, list):
        raise ValueError("'judgements' must be a list")
    judgements = []
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("evidence_quote"), str):
            if item["evidence_quote"].strip().lower() in {"", "null", "none", "n/a"}:
                item["evidence_quote"] = None
        judgements.append(CriterionJudgement.model_validate(item))
    expected = [c.id for c in llm_criteria(protocol)]
    got = [j.criterion_id for j in judgements]
    if sorted(got) != sorted(expected):
        raise ValueError(f"expected one judgement for each of {expected}, got {got}")
    order = {criterion_id: i for i, criterion_id in enumerate(expected)}
    return sorted(judgements, key=lambda j: order[j.criterion_id])


def screen_record(protocol: Protocol, record: Record, screener_name: str, model: str,
                  system_prompt: str, prompt_sha256: str, cache_scope: str | None = None) -> ScreeningDecision:
    """Ask one screener about one record and apply the decision rule."""
    screener = f"{screener_name}:{model}"
    text = screened_text(record)
    last_error = ""

    for attempt in range(MAX_ATTEMPTS):
        try:
            response = llm.complete(f"screen_{screener_name}", "screen_max_tokens",
                                    system=system_prompt, user=build_user_message(record),
                                    attempt=attempt, model=model, cache_scope=cache_scope)
            judgements = parse_judgements(response.text, protocol)
        except (ValueError, ValidationError) as e:
            last_error = f"unusable reply: {str(e)[:200]}"
            continue
        except PaletConfigError:
            raise                               # missing key or settings: stop everything
        except Exception as e:                  # API or network failure for this record
            last_error = f"{type(e).__name__}: {str(e)[:200]}"
            continue

        for judgement in judgements:
            judgement.quote_verified = quote_is_in_text(judgement.evidence_quote, text)
        decision, reason, notes, failed = decide(protocol, judgements)
        return ScreeningDecision(record_id=record.record_id, screener=screener, judgements=judgements,
                                 decision=decision, reason_code=reason, failed_reasons=failed, notes=notes,
                                 prompt_sha256=prompt_sha256,
                                 # Date of the model reply, so a replayed run is identical.
                                 decided_at=response.created_at or _now())

    # A failure is never an exclusion: the record goes to a person.
    return ScreeningDecision(record_id=record.record_id, screener=screener, decision="error",
                             notes=last_error, prompt_sha256=prompt_sha256, decided_at=_now())


# ── Combining screeners ─────────────────────────────────────────────────────

def combine(record_id: str, decisions: list[ScreeningDecision]) -> FinalDecision:
    """Final outcome from the screeners' decisions for one record."""
    summary = {d.screener: d.decision + (f" ({d.reason_code})" if d.reason_code else "") for d in decisions}

    metadata = next((d for d in decisions if d.screener == "metadata"), None)
    if metadata is not None:
        if metadata.decision == "exclude":
            return FinalDecision(record_id=record_id, decision="exclude", reason_code=metadata.reason_code,
                                 decided_by="metadata", screener_decisions=summary)
        return FinalDecision(record_id=record_id, decision="pending", reason_code=metadata.reason_code,
                             decided_by="pending", pending_reason=metadata.notes, screener_decisions=summary)

    outcomes = {d.decision for d in decisions}
    if outcomes == {"include"}:
        return FinalDecision(record_id=record_id, decision="include", decided_by="agreement",
                             screener_decisions=summary)
    if outcomes == {"exclude"}:
        # Prefer a reason that every screener found; fall back to any reason given.
        per_screener = [set(d.failed_reasons or ([d.reason_code] if d.reason_code else [])) for d in decisions]
        shared = set.intersection(*per_screener) if per_screener else set()
        candidates = shared or set.union(*per_screener)
        return FinalDecision(record_id=record_id, decision="exclude",
                             reason_code=_first_by_precedence(sorted(candidates)),
                             reasons_shared=bool(shared), decided_by="agreement", screener_decisions=summary)

    if "error" in outcomes:
        why = "a screener failed"
    elif "unclear" in outcomes:
        why = "at least one screener was unsure"
    else:
        why = "screeners disagree"
    return FinalDecision(record_id=record_id, decision="pending", decided_by="pending",
                         pending_reason=why, screener_decisions=summary)


def screen_records(protocol: Protocol, records: list[Record], screeners: list[dict],
                   workers: int = 4, progress=None) -> tuple[list[ScreeningDecision], list[FinalDecision], str]:
    """Screen every record with every screener.

    ``screeners`` is a list of {"name": "A", "model": "<model id>"}.
    Returns (all screener decisions, final decisions, prompt sha256).
    """
    from palet.runs import sha256_text

    if len(screeners) < 2:
        raise PaletConfigError("Screening needs at least two independent screeners")
    system_prompt = build_system_prompt(protocol)
    prompt_sha = sha256_text(system_prompt)
    llm.get_client() if not llm._settings["replay"] else None      # fail early, before the pool

    all_decisions: dict[str, list[ScreeningDecision]] = {r.record_id: [] for r in records}
    jobs = []
    for record in records:
        metadata = metadata_decision(protocol, record)
        if metadata is not None:
            all_decisions[record.record_id].append(metadata)
            continue
        for screener in screeners:
            jobs.append((record, screener))

    # Screeners that share a model send identical requests. Each one after the
    # first gets its own cache scope, so that it is a separate pass and not a
    # copy of the first one's stored reply.
    scopes, seen_models = {}, set()
    for screener in screeners:
        scopes[screener["name"]] = f"screener:{screener['name']}" if screener["model"] in seen_models else None
        seen_models.add(screener["model"])

    def run(job):
        record, screener = job
        return screen_record(protocol, record, screener["name"], screener["model"], system_prompt, prompt_sha,
                             cache_scope=scopes[screener["name"]])

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for decision in pool.map(run, jobs):
            all_decisions[decision.record_id].append(decision)
            done += 1
            if progress and (done % 10 == 0 or done == len(jobs)):
                progress(done, len(jobs))

    flat = [d for record in records for d in all_decisions[record.record_id]]
    finals = [combine(record.record_id, all_decisions[record.record_id]) for record in records]
    return flat, finals, prompt_sha


# ── Agreement between screeners ─────────────────────────────────────────────

def cohen_kappa(labels_a: list[str], labels_b: list[str]) -> Optional[float]:
    """Cohen's kappa for two raters; None when it is undefined."""
    n = len(labels_a)
    if n == 0 or n != len(labels_b):
        return None
    categories = sorted(set(labels_a) | set(labels_b))
    observed = sum(a == b for a, b in zip(labels_a, labels_b)) / n
    expected = sum((labels_a.count(c) / n) * (labels_b.count(c) / n) for c in categories)
    if expected == 1:
        return None
    return round((observed - expected) / (1 - expected), 3)


def agreement(decisions: list[ScreeningDecision]) -> dict:
    """Agreement between the model screeners on the records both judged."""
    by_record: dict[str, dict[str, str]] = {}
    for d in decisions:
        if d.screener == "metadata" or d.screener.startswith("human:"):
            continue
        by_record.setdefault(d.record_id, {})[d.screener] = d.decision
    names = sorted({s for per in by_record.values() for s in per})
    if len(names) != 2:
        return {"screeners": names, "records_compared": 0}
    pairs = [(per[names[0]], per[names[1]]) for per in by_record.values() if len(per) == 2]
    a, b = [p[0] for p in pairs], [p[1] for p in pairs]
    table: dict = {}
    for x, y in pairs:
        table[f"{x}/{y}"] = table.get(f"{x}/{y}", 0) + 1
    return {
        "screeners": names,
        "records_compared": len(pairs),
        "same_decision": sum(x == y for x, y in pairs),
        "percent_agreement": round(100 * sum(x == y for x, y in pairs) / len(pairs), 1) if pairs else None,
        "cohen_kappa": cohen_kappa(a, b),
        "cross_table": dict(sorted(table.items())),
    }


def summarize(finals: list[FinalDecision]) -> dict:
    counts = {"include": 0, "exclude": 0, "pending": 0}
    reasons: dict = {}
    decided_by: dict = {}
    for final in finals:
        counts[final.decision] += 1
        decided_by[final.decided_by] = decided_by.get(final.decided_by, 0) + 1
        if final.decision == "exclude":
            reasons[final.reason_code] = reasons.get(final.reason_code, 0) + 1
    return {"records": len(finals), **counts,
            "exclusion_reasons": dict(sorted(reasons.items())),
            "decided_by": dict(sorted(decided_by.items()))}


_RE_SPACES = re.compile(r"\s+")


def clip(text: Optional[str], limit: int = 300) -> str:
    text = _RE_SPACES.sub(" ", text or "").strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"
