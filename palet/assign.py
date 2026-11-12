"""Charting of included records: research questions addressed and contribution.

Runs only on records included by the screening. Each record may address
several research questions (or none). Every assignment must be backed by a
passage quoted from the record, and the quote is checked in code: an
assignment whose quote cannot be found is not counted and is flagged.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from palet import llm
from palet.errors import PaletConfigError
from palet.models import _INITIALS_RE, Record
from palet.protocol import Protocol
from palet.screening import build_user_message, quote_is_in_text, screened_text

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "assign_system_v1.txt"
MAX_ATTEMPTS = 3

Relevance = Literal["core", "partial", "none"]
EvidenceType = Literal["empirical", "theoretical", "review", "policy_document"]


class RQRelevance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rq: str
    relevance: Relevance
    evidence_quote: Optional[str] = None
    quote_verified: bool = False
    rationale: str = ""

    @property
    def counts(self) -> bool:
        """An assignment counts only if its quote was found in the record."""
        return self.relevance != "none" and self.quote_verified


class RecordAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str
    model: str
    status: Literal["ok", "error"] = "ok"
    items: list[RQRelevance] = Field(default_factory=list)
    contribution: str = ""
    contribution_quote: Optional[str] = None
    contribution_quote_verified: bool = False
    evidence_type: Optional[EvidenceType] = None
    geography: list[str] = Field(default_factory=list)
    notes: str = ""
    prompt_sha256: Optional[str] = None
    decided_at: Optional[str] = None

    def rqs(self, relevance: str) -> list[str]:
        return [item.rq for item in self.items if item.relevance == relevance and item.counts]

    @property
    def assigned_rqs(self) -> list[str]:
        return [item.rq for item in self.items if item.counts]

    @property
    def needs_review(self) -> list[str]:
        """Reasons why a person should look at this record."""
        reasons = []
        if self.status == "error":
            reasons.append("charting failed")
            return reasons
        unverified = [i.rq for i in self.items if i.relevance != "none" and not i.quote_verified]
        if unverified:
            reasons.append("quote not found for " + ", ".join(unverified))
        if not self.assigned_rqs:
            reasons.append("included but not assigned to any research question")
        if self.contribution and not self.contribution_quote_verified:
            reasons.append("contribution quote not found")
        return reasons


def build_system_prompt(protocol: Protocol) -> str:
    questions = "\n".join(f"- {key}: {text}" for key, text in protocol.research_questions.items())
    return (PROMPT_PATH.read_text(encoding="utf-8")
            .replace("{{REVIEW_TITLE}}", protocol.title)
            .replace("{{RESEARCH_QUESTIONS}}", questions))


def parse_reply(reply: str, protocol: Protocol) -> dict:
    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in the reply")
    data = json.loads(reply[start:end + 1])
    raw = data.get("assignments")
    if not isinstance(raw, list):
        raise ValueError("'assignments' must be a list")
    items = []
    for entry in raw:
        if isinstance(entry, dict) and isinstance(entry.get("evidence_quote"), str):
            if entry["evidence_quote"].strip().lower() in {"", "null", "none", "n/a"}:
                entry["evidence_quote"] = None
        items.append(RQRelevance.model_validate(entry))
    expected = list(protocol.research_questions)
    if sorted(i.rq for i in items) != sorted(expected):
        raise ValueError(f"expected one assignment for each of {expected}, got {[i.rq for i in items]}")
    order = {rq: n for n, rq in enumerate(expected)}
    items.sort(key=lambda i: order[i.rq])
    evidence_type = data.get("evidence_type")
    if evidence_type not in ("empirical", "theoretical", "review", "policy_document"):
        raise ValueError(f"invalid evidence_type: {evidence_type!r}")
    geography = data.get("geography") or []
    if not isinstance(geography, list):
        raise ValueError("'geography' must be a list")
    return {"items": items, "contribution": str(data.get("contribution") or "").strip(),
            "contribution_quote": data.get("contribution_quote") or None,
            "evidence_type": evidence_type, "geography": [str(g).strip() for g in geography if str(g).strip()]}


def assign_record(protocol: Protocol, record: Record, model: str, system_prompt: str,
                  prompt_sha256: str) -> RecordAssignment:
    text = screened_text(record)
    last_error = ""
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = llm.complete("assign", "assign_max_tokens", system=system_prompt,
                                    user=build_user_message(record), attempt=attempt, model=model)
            parsed = parse_reply(response.text, protocol)
        except (ValueError, ValidationError) as e:
            last_error = f"unusable reply: {str(e)[:200]}"
            continue
        except PaletConfigError:
            raise
        except Exception as e:
            last_error = f"{type(e).__name__}: {str(e)[:200]}"
            continue

        for item in parsed["items"]:
            item.quote_verified = quote_is_in_text(item.evidence_quote, text)
        return RecordAssignment(
            record_id=record.record_id, model=model, prompt_sha256=prompt_sha256,
            contribution_quote_verified=quote_is_in_text(parsed["contribution_quote"], text),
            decided_at=response.created_at, **parsed)

    return RecordAssignment(record_id=record.record_id, model=model, status="error", notes=last_error,
                            prompt_sha256=prompt_sha256)


def assign_records(protocol: Protocol, records: list[Record], model: str, workers: int = 4,
                   progress=None) -> tuple[list[RecordAssignment], str]:
    from palet.runs import sha256_text

    system_prompt = build_system_prompt(protocol)
    prompt_sha = sha256_text(system_prompt)
    if not llm._settings["replay"]:
        llm.get_client()

    results, done = [], 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for result in pool.map(lambda r: assign_record(protocol, r, model, system_prompt, prompt_sha), records):
            results.append(result)
            done += 1
            if progress and (done % 10 == 0 or done == len(records)):
                progress(done, len(records))
    return results, prompt_sha


# ── Labels and tables ───────────────────────────────────────────────────────

def display_surname(author: str) -> str:
    """Surname as written in the source ("Rodríguez-Pose A." -> "Rodríguez-Pose")."""
    author = (author or "").strip()
    if not author:
        return ""
    if "," in author:
        return author.split(",")[0].strip()
    tokens = author.split()
    kept = list(tokens)
    while len(kept) > 1 and _INITIALS_RE.match(kept[-1]):
        kept.pop()                            # Scopus style: surname first, then initials
    if len(kept) < len(tokens):
        return " ".join(kept)
    return tokens[-1]                         # "Name Surname" (OpenAlex, PubMed)


def short_citation(record: Record) -> str:
    """Author–year label: "Smith (2020)", "Smith and Jones (2020)", "Smith et al. (2020)"."""
    surnames = [s for s in (display_surname(a) for a in record.authors) if s]
    year = record.year if record.year else "n.d."
    if not surnames:
        return f"{record.title[:40]}… ({year})"
    if len(surnames) == 1:
        return f"{surnames[0]} ({year})"
    if len(surnames) == 2:
        return f"{surnames[0]} and {surnames[1]} ({year})"
    return f"{surnames[0]} et al. ({year})"


def summarize(protocol: Protocol, assignments: list[RecordAssignment]) -> dict:
    per_rq = {rq: {"core": 0, "partial": 0} for rq in protocol.research_questions}
    for assignment in assignments:
        for item in assignment.items:
            if item.counts:
                per_rq[item.rq][item.relevance] += 1
    multi = sum(1 for a in assignments if len(a.assigned_rqs) > 1)
    return {
        "records": len(assignments),
        "per_rq": per_rq,
        "assigned_to_several_rqs": multi,
        "not_assigned_to_any_rq": sum(1 for a in assignments if a.status == "ok" and not a.assigned_rqs),
        "errors": sum(1 for a in assignments if a.status == "error"),
        "needs_review": sum(1 for a in assignments if a.needs_review),
        "evidence_types": {t: sum(1 for a in assignments if a.evidence_type == t)
                           for t in ("empirical", "theoretical", "review", "policy_document")},
    }
