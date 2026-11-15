"""Protocol assistant: from a context and research questions to a draft protocol.

Two model calls, both advisory:
1. ``analyse_questions`` reviews the wording of the research questions and suggests sharper versions;
2. ``draft_protocol`` proposes eligibility criteria and one search per question.

The result is a protocol file with ``status: draft`` and every search ``proposed``. Nothing is
screened against it until the authors approve it (``approve_protocol``): the model proposes,
people decide.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from palet import config, llm
from palet.errors import PaletConfigError, PaletError
from palet.protocol import load_protocol

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
MAX_ATTEMPTS = 2
MAX_QUESTIONS = 12

_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,23}$")
_BLOCK = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_]{1,60}$")
_JSON = re.compile(r"\{.*\}", re.S)


class QuestionAdvice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    issues: list[str] = Field(default_factory=list)
    suggested: str = Field(min_length=10)
    change: Literal["none", "minor", "major"]
    rationale: str = ""


class QuestionAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: str
    questions: list[QuestionAdvice]
    gaps: list[str] = Field(default_factory=list)


class DraftCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["include", "exclude"]
    dimension: Literal["population", "concept", "context"]
    rule: str = Field(min_length=10)
    reason_code: str


class DraftSearch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rq: str
    blocks: dict[str, list[str]]


class ProtocolDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3)
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    criteria: list[DraftCriterion]
    searches: list[DraftSearch]
    notes: list[str] = Field(default_factory=list)


def clean_questions(questions: list[str]) -> list[str]:
    """Trim, drop empty lines and leading numbering ("1.", "RQ2:", "- ")."""
    cleaned = []
    for question in questions:
        text = re.sub(r"^\s*(?:[-*•]|\(?\d+[.)]|(?:RQ|PI|Q)\s*-?\d+\s*[:.)-])\s*", "", str(question), flags=re.I).strip()
        if text:
            cleaned.append(" ".join(text.split()))
    if not 1 <= len(cleaned) <= MAX_QUESTIONS:
        raise PaletError(f"A review needs between 1 and {MAX_QUESTIONS} research questions; {len(cleaned)} given")
    short = [q for q in cleaned if len(q) < 15]
    if short:
        raise PaletError(f"This does not look like a research question: '{short[0]}'")
    return cleaned


def _user_message(context: str, questions: list[str]) -> str:
    lines = "\n".join(f"RQ{i}: {text}" for i, text in enumerate(questions, 1))
    return f"<context>\n{context.strip()}\n</context>\n\n<research_questions>\n{lines}\n</research_questions>"


def _ask(prompt_file: str, user: str, parse):
    """Call the assistant model and parse its JSON reply; one retry on an unusable reply."""
    system = (PROMPTS / prompt_file).read_text(encoding="utf-8")
    model = config.get_assistant_model()
    last_error = ""
    for attempt in range(MAX_ATTEMPTS):
        response = llm.complete("protocol_assistant", "protocol_max_tokens", system=system, user=user,
                                attempt=attempt, model=model)
        try:
            match = _JSON.search(response.text)
            if not match:
                raise ValueError("the reply has no JSON object")
            return parse(json.loads(match.group(0)))
        except (ValueError, ValidationError) as e:
            last_error = str(e)
    raise PaletError(f"The model did not return a usable reply ({last_error[:200]})")


def analyse_questions(context: str, questions: list[str]) -> QuestionAnalysis:
    """Advice on the wording of each research question. ``questions`` must already be clean."""
    expected = [f"RQ{i}" for i in range(1, len(questions) + 1)]

    def parse(data: dict) -> QuestionAnalysis:
        analysis = QuestionAnalysis.model_validate(data)
        if [q.id for q in analysis.questions] != expected:
            raise ValueError(f"expected advice for {expected}")
        for advice, original in zip(analysis.questions, questions):
            if advice.change == "none":
                advice.suggested = original          # "unchanged" must mean exactly that
        return analysis

    return _ask("questions_system_v1.txt", _user_message(context, questions), parse)


def draft_protocol(context: str, questions: list[str]) -> ProtocolDraft:
    """Proposed criteria and one search per question, for questions the authors have fixed."""
    expected = [f"RQ{i}" for i in range(1, len(questions) + 1)]

    def parse(data: dict) -> ProtocolDraft:
        draft = ProtocolDraft.model_validate(data)
        if not 2 <= len(draft.criteria) <= 8 or not any(c.kind == "include" for c in draft.criteria):
            raise ValueError("between 2 and 8 criteria, at least one of inclusion, are needed")
        ids = [c.id for c in draft.criteria]
        if len(set(ids)) != len(ids) or not all(re.fullmatch(r"(IC|EC)\d+", i) for i in ids):
            raise ValueError("criterion ids must be IC1, IC2… / EC1, EC2… without repeats")
        for criterion in draft.criteria:
            if not _CODE.match(criterion.reason_code):
                raise ValueError(f"reason_code is not valid: {criterion.reason_code}")
        if [s.rq for s in draft.searches] != expected:
            raise ValueError(f"expected one search for each of {expected}")
        for search in draft.searches:
            if not 2 <= len(search.blocks) <= 5:
                raise ValueError(f"{search.rq}: a search needs 2 to 5 blocks")
            for name, terms in search.blocks.items():
                if not _BLOCK.match(name):
                    raise ValueError(f"{search.rq}: block name is not valid: {name}")
                search.blocks[name] = _clean_terms(terms)
                if not search.blocks[name]:
                    raise ValueError(f"{search.rq}: block '{name}' has no usable term")
        return draft

    return _ask("protocol_draft_system_v1.txt", _user_message(context, questions), parse)


def _clean_terms(terms: list) -> list[str]:
    cleaned = []
    for term in terms:
        text = re.sub(r'["“”()*\[\],|]', " ", str(term)).strip()
        text = " ".join(text.split())
        if text and not re.search(r"\b(AND|OR|NOT)\b", text) and text.lower() not in [t.lower() for t in cleaned]:
            cleaned.append(text)
    return cleaned[:20]


def protocol_data(draft: ProtocolDraft, questions: list[str], originals: list[str]) -> dict:
    """The protocol as a dictionary, in the order it is written to the file."""
    rqs = {f"RQ{i}": text for i, text in enumerate(questions, 1)}
    changed = {f"RQ{i}": original for i, (text, original) in enumerate(zip(questions, originals), 1)
               if original and original != text}
    criteria = [c.model_dump() for c in draft.criteria]
    criteria.append({"id": f"IC{sum(c.kind == 'include' for c in draft.criteria) + 1}", "kind": "include",
                     "dimension": "study_type", "rule": "Peer-reviewed journal article or review.",
                     "reason_code": "WRONG_DOC_TYPE"})
    data: dict = {"version": 1, "status": "draft", "title": draft.title, "research_questions": rqs}
    if changed:
        data["research_questions_original"] = changed
    data.update({"assignment_mode": "multi", "criteria": criteria})
    if draft.year_from:
        data["year_from"] = draft.year_from
    if draft.year_to:
        data["year_to"] = draft.year_to
    data.update({"languages": ["en"], "document_types": ["article", "review"], "sources": [
        {"id": f"openalex_{search.rq.lower()}", "type": "openalex", "field": "title_and_abstract",
         "languages": ["en"], "applies_to_rqs": [search.rq], "status": "proposed", "blocks": search.blocks}
        for search in draft.searches]})
    return data


def write_protocol(path: Path, data: dict, context: str) -> None:
    """Write a draft protocol. Refuses to replace a file; the result must load as a valid protocol."""
    path = Path(path)
    if path.exists():
        raise PaletError(f"A protocol named {path.name} already exists")
    header = ["# Draft protocol written by the PALET protocol assistant on " + date.today().isoformat() + ".",
              "# Criteria and searches are PROPOSALS of an AI model. Edit this file as needed and approve it",
              "# (python -m palet approve-protocol) only when the authors agree with every line.",
              "#", "# Context given by the authors:"]
    header += ["#   " + line for line in context.strip().splitlines()[:40]]
    text = "\n".join(header) + "\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=110)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    try:
        load_protocol(path)
    except PaletConfigError:
        path.unlink()
        raise


def approve_protocol(path: Path, approved_by: str) -> None:
    """Mark a draft protocol as approved by the authors (who, when). Only that changes in the file."""
    path = Path(path)
    protocol = load_protocol(path)
    if protocol.status == "approved":
        raise PaletError(f"{path.name} is already approved")
    who = " ".join(str(approved_by).split())
    if len(who) < 2 or '"' in who or "\\" in who:
        raise PaletError("Say who approves the protocol (names or initials)")
    text = path.read_text(encoding="utf-8")
    if len(re.findall(r"^status: draft[ \t]*$", text, flags=re.M)) != 1:
        raise PaletError(f"Cannot find a single top-level 'status: draft' line in {path.name}")
    stamp = f'status: approved\napproved_by: "{who}"\napproved_at: {date.today().isoformat()}'
    updated = re.sub(r"^status: draft[ \t]*$", stamp, text, count=1, flags=re.M)
    path.write_text(updated, encoding="utf-8")
    try:
        load_protocol(path)
    except PaletConfigError:
        path.write_text(text, encoding="utf-8")       # leave the file as it was
        raise


def slug(name: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFD", str(name)).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:60]
    if not _SLUG.match(text):
        raise PaletError("The name needs at least two letters or digits")
    return text
