"""Check the citations of a manuscript against its reference list (WP10).

Works on author–year citations. It reports four things: works cited in the
text but missing from the list, works listed but never cited, citations whose
authors do not match the listed reference (``et al.`` for a two-author work,
a missing co-author…), and listed references that need an a/b suffix.

The output is a list for a person to review: the extraction is heuristic.
"""

import html
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from palet.errors import PaletError
from rapidfuzz import fuzz

from palet.models import normalize_title

YEAR = r"(?:19|20)\d{2}[a-z]?"
_WORD = r"[A-ZÀ-ÖØ-Þ][\w'’\-]*"
_PARTICLE = r"\b(?:de|del|della|van|von|der|den|di|da|dos|la|le|ten|ter)\b"
_NAME_TOKEN = rf"(?:{_WORD}|{_PARTICLE}|\bet\s+al\.?|\band\b|&)"
_CITATION_RE = re.compile(
    rf"(?<![\w'’\-])(?P<names>(?:{_NAME_TOKEN}[\s,]+){{0,8}}(?:{_WORD}|\bet\s+al\.?))"
    rf"(?:\s*,\s*|\s*\(\s*|\s+)"
    rf"(?P<years>{YEAR}(?:\s*(?:,|and|&)\s*{YEAR})*)"
)
_REFERENCE_RE = re.compile(rf"^(?P<authors>.{{2,300}}?)\s*\((?P<year>{YEAR}|n\.d\.)\)")
_PERSON_RE = re.compile(r"([^,]+?),\s*(?:[A-ZÀ-ÖØ-Þ]\.\s*-?\s*)+")

# Capitalised words that often precede a year without being an author.
_NOT_AUTHORS = {
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
    "november", "december", "figure", "table", "section", "chapter", "agenda", "com", "in", "since",
    "from", "until", "by", "between", "during", "after", "before", "see", "while", "as", "the", "and",
    "strategy", "horizon", "europe", "deal", "eu", "regulation", "directive", "nuts", "rq", "pi",
}


@dataclass
class Reference:
    raw: str
    authors_raw: str
    year: str
    surnames: list[str]              # normalised; one element for an organisation
    is_organisation: bool
    abbreviated: bool = False        # the list itself says "et al." instead of naming every author
    cited: bool = False

    @property
    def citation_key(self) -> tuple:
        """How the work is cited in the text: this is what needs an a/b suffix."""
        if self.is_organisation or len(self.surnames) == 1:
            who = self.surnames[0]
        elif len(self.surnames) == 2 and not self.abbreviated:
            who = " and ".join(self.surnames)
        else:
            who = self.surnames[0] + " et al"
        return who, self.year

    @property
    def label(self) -> str:
        return f"{self.authors_raw.strip()} ({self.year})"


@dataclass
class Citation:
    names: str
    year: str
    context: str
    surnames: list[str] = field(default_factory=list)
    et_al: bool = False

    @property
    def label(self) -> str:
        return f"{self.names.strip()} ({self.year})"


# ── Reading the manuscript ──────────────────────────────────────────────────

def read_paragraphs(path) -> list[str]:
    """Paragraphs of a .docx (including table cells), or lines of a text file."""
    path = Path(path)
    if not path.is_file():
        raise PaletError(f"Manuscript not found: {path}")
    if path.suffix.lower() == ".docx":
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml").decode("utf-8")
        paragraphs = []
        for block in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S):
            text = "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", block))
            text = html.unescape(text).strip()
            if text:
                paragraphs.append(text)
        return paragraphs
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def split_manuscript(paragraphs: list[str], body_start: str = "Abstract",
                     references_heading: str = "References") -> tuple[list[str], list[str]]:
    """(body paragraphs, reference-list paragraphs).

    The body starts at the first paragraph equal to ``body_start`` (so that a
    cover letter placed before the manuscript is ignored) and the list at the
    last paragraph equal to ``references_heading``.
    """
    def find(heading, last=False):
        hits = [i for i, p in enumerate(paragraphs) if p.strip().lower().rstrip(":") == heading.lower()]
        if not hits:
            raise PaletError(f"Heading not found in the manuscript: '{heading}'")
        return hits[-1] if last else hits[0]

    start = find(body_start)
    refs = find(references_heading, last=True)
    if refs <= start:
        raise PaletError("The reference list comes before the body; check the headings given")
    return paragraphs[start:refs], paragraphs[refs + 1:]


# ── Parsing ─────────────────────────────────────────────────────────────────

def parse_references(paragraphs: list[str]) -> list[Reference]:
    references = []
    for paragraph in paragraphs:
        match = _REFERENCE_RE.match(paragraph)
        if not match:
            continue
        authors = match.group("authors").strip().rstrip(",")
        people = [normalize_title(s) for s in _PERSON_RE.findall(authors + ",")]
        people = [re.sub(r"^and ", "", s).strip() for s in people if s]
        if people:
            references.append(Reference(paragraph, authors, match.group("year"), people, False,
                                        abbreviated="et al" in authors.lower()))
        else:
            references.append(Reference(paragraph, authors, match.group("year"), [normalize_title(authors)], True))
    return references


def _clean_names(names: str) -> tuple[str, list[str], bool]:
    """Drop leading non-author words; return (text, surnames, has 'et al.')."""
    tokens = re.findall(rf"\bet\s+al\.?|{_WORD}|{_PARTICLE}|\band\b|&", names)
    while tokens and (tokens[0].lower() in _NOT_AUTHORS or tokens[0] in {"and", "&"}):
        tokens.pop(0)
    et_al = any(t.lower().startswith("et") and "al" in t.lower() for t in tokens)
    surnames, current = [], []
    for token in tokens:
        if token in {"and", "&"} or token.lower().startswith("et "):
            if current:
                surnames.append(normalize_title(" ".join(current)))
                current = []
        else:
            current.append(token)
    if current:
        surnames.append(normalize_title(" ".join(current)))
    return " ".join(tokens), [s for s in surnames if s], et_al


def extract_citations(body: list[str]) -> list[Citation]:
    citations = []
    for paragraph in body:
        for match in _CITATION_RE.finditer(paragraph):
            names, surnames, et_al = _clean_names(match.group("names"))
            if not surnames or surnames[-1] in _NOT_AUTHORS:
                continue
            context = paragraph[max(0, match.start() - 40):match.end() + 20]
            for year in re.findall(YEAR, match.group("years")):
                citations.append(Citation(names, year, context, surnames, et_al))
    return citations


# ── Matching ────────────────────────────────────────────────────────────────

def _matches(citation: Citation, reference: Reference) -> bool:
    if citation.year != reference.year:
        return False
    cited = " ".join(citation.surnames)
    if reference.is_organisation:
        organisation = reference.surnames[0]
        return bool(cited) and (organisation.endswith(cited) or cited.endswith(organisation))
    first = reference.surnames[0]
    # The citation's words may start with leftovers ("While Benner"), so the
    # reference's first surname only has to be among the cited surnames.
    return any(s == first or s.endswith(" " + first) for s in citation.surnames)


def _author_mismatch(citation: Citation, reference: Reference) -> str | None:
    if reference.is_organisation or reference.abbreviated:
        return None
    n = len(reference.surnames)
    if citation.et_al and n < 3:
        return f"cited with 'et al.' but the reference has {n} author(s)"
    if not citation.et_al:
        cited_n = len(citation.surnames)
        if n >= 3:
            return f"the reference has {n} authors; cite as '{reference.authors_raw.split(',')[0]} et al.'"
        if cited_n != n:
            return f"cited with {cited_n} author(s) but the reference has {n}"
        if n == 2 and not citation.surnames[-1].endswith(reference.surnames[1]):
            return "second author differs from the reference"
    return None


def check_citations(body: list[str], reference_paragraphs: list[str]) -> dict:
    references = parse_references(reference_paragraphs)
    citations = extract_citations(body)

    missing, mismatches = {}, {}
    for citation in citations:
        matched = [r for r in references if _matches(citation, r)]
        if not matched:
            missing.setdefault(citation.label, citation.context)
            continue
        for reference in matched:
            reference.cited = True
        problem = _author_mismatch(citation, matched[0])
        if problem:
            mismatches.setdefault((citation.label, matched[0].label), problem)

    by_key: dict = {}
    for reference in references:
        by_key.setdefault(reference.citation_key, []).append(reference)
    need_suffix = [[r.label for r in group] for group in by_key.values() if len(group) > 1]

    # A citation and a reference of the same year whose first surnames almost
    # coincide are probably one work spelt in two ways, not two problems.
    uncited = [r for r in references if not r.cited]
    variants = []
    for label, context in sorted(missing.items()):
        citation = next(c for c in citations if c.label == label)
        for reference in uncited:
            if reference.year != citation.year or reference.is_organisation != (len(citation.surnames) == 0):
                pass
            if reference.year != citation.year:
                continue
            first_ref = reference.surnames[0]
            first_cited = citation.surnames[0] if citation.surnames else ""
            close = (fuzz.ratio(first_ref, first_cited) >= 80
                     or first_ref.split()[0] == first_cited.split()[0]
                     or fuzz.token_set_ratio(first_ref, " ".join(citation.surnames)) >= 90)
            if close:
                variants.append({"citation": label, "reference": reference.label})
                break
    variant_citations = {v["citation"] for v in variants}
    variant_references = {v["reference"] for v in variants}

    return {
        "references_in_list": len(references),
        "citations_found": len(citations),
        "cited_not_listed": [{"citation": k, "context": v} for k, v in sorted(missing.items())
                             if k not in variant_citations],
        "listed_not_cited": sorted(r.label for r in uncited if r.label not in variant_references),
        "probable_spelling_variants": variants,
        "incomplete_references": sorted(r.label for r in references if r.abbreviated),
        "author_mismatches": [{"citation": c, "reference": r, "problem": p}
                              for (c, r), p in sorted(mismatches.items())],
        "same_authors_and_year": need_suffix,
    }


def format_report(result: dict) -> str:
    lines = ["# Citation check", "",
             f"References in the list: {result['references_in_list']}  ",
             f"Citations found in the text: {result['citations_found']}", "",
             "The extraction is heuristic: review every item before changing the manuscript.", ""]
    lines += [f"## Cited in the text but not in the reference list ({len(result['cited_not_listed'])})", ""]
    lines += [f"- **{item['citation']}** — …{item['context']}…" for item in result["cited_not_listed"]] or ["- none"]
    lines += ["", f"## In the reference list but never cited ({len(result['listed_not_cited'])})", ""]
    lines += [f"- {label}" for label in result["listed_not_cited"]] or ["- none"]
    lines += ["", f"## Citation and reference disagree on the authors ({len(result['author_mismatches'])})", ""]
    lines += [f"- **{m['citation']}** vs. *{m['reference']}*: {m['problem']}"
              for m in result["author_mismatches"]] or ["- none"]
    lines += ["", "## Probably the same work, spelt differently in text and list "
                  f"({len(result['probable_spelling_variants'])})", ""]
    lines += [f"- **{v['citation']}** ↔ *{v['reference']}*"
              for v in result["probable_spelling_variants"]] or ["- none"]
    lines += ["", f"## References that say 'et al.' instead of listing the authors "
                  f"({len(result['incomplete_references'])})", ""]
    lines += [f"- {label}" for label in result["incomplete_references"]] or ["- none"]
    lines += ["", f"## Cited the same way and same year: need a/b ({len(result['same_authors_and_year'])})", ""]
    lines += [f"- {'; '.join(group)}" for group in result["same_authors_and_year"]] or ["- none"]
    return "\n".join(lines) + "\n"
