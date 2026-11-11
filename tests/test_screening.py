"""Screening: the model judges criteria, the code decides and checks quotes."""

import json
from types import SimpleNamespace

import pytest

from palet import llm
from palet.models import Record
from palet.protocol import load_protocol
from palet.runs import ROOT
from palet.screening import (
    CriterionJudgement, ScreeningDecision, agreement, build_system_prompt, build_user_message,
    cohen_kappa, combine, decide, llm_criteria, metadata_decision, parse_judgements,
    quote_is_in_text, screen_record, screen_records, summarize,
)

PROTOCOL = load_protocol(ROOT / "config" / "protocol_isabel_chapter_v1.yaml")
LLM_IDS = ["IC1", "IC2", "IC3", "EC1", "EC2", "EC3"]

ABSTRACT = ("We study the employment effects of coal mine closures in Silesia, Poland, between 2010 and "
            "2020. Retraining programmes funded by the Just Transition Fund reduced long-term unemployment.")
RECORD = Record.build(title="Coal phase-out and regional employment in Poland", doi="10.1/coal",
                      authors=["Kowalski P."], year=2021, abstract=ABSTRACT, language="en",
                      doc_type="article", keywords=["just transition", "employment"])

QUOTES = {"IC1": "coal mine closures in Silesia, Poland", "IC2": "employment effects of coal mine closures",
          "IC3": "Just Transition Fund"}


def judgements(verified=True, **overrides):
    """A clean 'include' pattern, with per-criterion overrides: IC2="no", EC1=("yes", "quote")…"""
    base = {"IC1": "yes", "IC2": "yes", "IC3": "yes", "EC1": "no", "EC2": "no", "EC3": "no"}
    result = []
    for criterion_id in LLM_IDS:
        value = overrides.get(criterion_id, base[criterion_id])
        met, quote = value if isinstance(value, tuple) else (value, QUOTES.get(criterion_id))
        if met != "yes" and not isinstance(value, tuple):
            quote = None
        result.append(CriterionJudgement(criterion_id=criterion_id, met=met, evidence_quote=quote,
                                         quote_verified=bool(quote) and verified, rationale="r"))
    return result


def reply(**overrides):
    return json.dumps({"judgements": [
        {"criterion_id": j.criterion_id, "met": j.met, "evidence_quote": j.evidence_quote, "rationale": "r"}
        for j in judgements(**overrides)
    ]})


# ── Prompt ──────────────────────────────────────────────────────────────────

def test_only_non_metadata_criteria_go_to_the_model():
    assert [c.id for c in llm_criteria(PROTOCOL)] == LLM_IDS        # IC4 (study type) is metadata


def test_system_prompt_contains_protocol_and_no_placeholders():
    prompt = build_system_prompt(PROTOCOL)
    assert "{{" not in prompt
    assert PROTOCOL.title in prompt
    for criterion in llm_criteria(PROTOCOL):
        assert criterion.rule in prompt
    assert "- IC1 | INCLUSION | context |" in prompt and "- EC2 | EXCLUSION | concept |" in prompt
    assert "IC4" not in prompt
    for text in PROTOCOL.research_questions.values():
        assert text in prompt


def test_user_message_has_only_what_the_screener_may_use():
    message = build_user_message(RECORD)
    assert RECORD.title in message and ABSTRACT in message and "just transition; employment" in message
    assert "Kowalski" not in message and "2021" not in message       # no authors, no year


# ── Quote verification ──────────────────────────────────────────────────────

def test_quote_verification():
    text = RECORD.title + " " + ABSTRACT
    assert quote_is_in_text("coal mine closures in Silesia, Poland", text)
    assert quote_is_in_text("Coal mine closures in Silesia  Poland", text)          # case, punctuation
    assert quote_is_in_text("retraining programs funded by the Just Transition Fund", text)   # tiny variation
    assert not quote_is_in_text("job losses in the automotive industry of Bavaria", text)     # invented
    assert not quote_is_in_text(None, text) and not quote_is_in_text("Poland", text)          # too short


# ── Decision rule ───────────────────────────────────────────────────────────

def test_all_inclusions_met_and_no_exclusion_applies_is_include():
    assert decide(PROTOCOL, judgements()) == ("include", None, "")


@pytest.mark.parametrize("overrides,reason", [
    ({"IC2": "no"}, "WRONG_CONCEPT"),
    ({"IC3": "no"}, "WRONG_PHENOMENON"),
    ({"EC1": ("yes", "coal mine closures in Silesia, Poland")}, "WRONG_CONTEXT"),
    ({"IC2": "no", "IC3": "no"}, "WRONG_CONCEPT"),                       # precedence
    ({"IC3": "no", "EC1": ("yes", "coal mine closures in Silesia, Poland")}, "WRONG_CONTEXT"),
])
def test_exclusion_takes_the_first_reason_by_precedence(overrides, reason):
    decision, code, _ = decide(PROTOCOL, judgements(**overrides))
    assert (decision, code) == ("exclude", reason)


def test_any_doubt_makes_the_record_unclear_never_excluded():
    decision, code, notes = decide(PROTOCOL, judgements(IC1="unclear"))
    assert (decision, code) == ("unclear", None) and "IC1: unclear" in notes


def test_a_yes_without_a_verified_quote_does_not_count():
    decision, _, notes = decide(PROTOCOL, judgements(verified=False))
    assert decision == "unclear" and "quote not found" in notes
    # An exclusion criterion answered "yes" with an invented quote cannot exclude.
    invented = judgements(EC1=("yes", "the study covers only China"))
    invented[3].quote_verified = False
    assert decide(PROTOCOL, invented)[0] == "unclear"


def test_a_firm_exclusion_wins_over_a_doubt_elsewhere():
    assert decide(PROTOCOL, judgements(IC1="unclear", IC2="no"))[:2] == ("exclude", "WRONG_CONCEPT")


# ── Metadata ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("changes,expected", [
    ({"doc_type": "editorial"}, ("exclude", "WRONG_DOC_TYPE")),
    ({"language": "fr"}, ("exclude", "WRONG_LANGUAGE")),
    ({"year": 2010}, ("exclude", "OUT_OF_PERIOD")),
    ({"abstract": None}, ("unclear", "NO_ABSTRACT")),
    ({"abstract": "   "}, ("unclear", "NO_ABSTRACT")),
])
def test_metadata_decisions(changes, expected):
    decision = metadata_decision(PROTOCOL, RECORD.model_copy(update=changes))
    assert (decision.decision, decision.reason_code) == expected and decision.screener == "metadata"


def test_records_with_unknown_metadata_go_to_the_model():
    assert metadata_decision(PROTOCOL, RECORD) is None
    assert metadata_decision(PROTOCOL, RECORD.model_copy(update={"language": None, "doc_type": None, "year": None})) is None


# ── Parsing model replies ───────────────────────────────────────────────────

def test_reply_is_parsed_even_with_text_around_the_json():
    parsed = parse_judgements("Here it is:\n```json\n" + reply() + "\n```", PROTOCOL)
    assert [j.criterion_id for j in parsed] == LLM_IDS


def test_null_written_as_text_becomes_none():
    data = json.loads(reply())
    data["judgements"][3]["evidence_quote"] = "null"
    assert parse_judgements(json.dumps(data), PROTOCOL)[3].evidence_quote is None


@pytest.mark.parametrize("mutate", [
    lambda d: d["judgements"].pop(),                                       # a criterion is missing
    lambda d: d["judgements"].append(dict(d["judgements"][0])),            # one twice
    lambda d: d["judgements"][0].update(criterion_id="IC9"),               # unknown criterion
    lambda d: d["judgements"][0].update(met="maybe"),                      # invalid value
    lambda d: d.pop("judgements"),
])
def test_incomplete_or_invalid_replies_are_rejected(mutate):
    data = json.loads(reply())
    mutate(data)
    with pytest.raises(Exception):
        parse_judgements(json.dumps(data), PROTOCOL)


# ── One screener ────────────────────────────────────────────────────────────

class ScriptedClient:
    """Replies in order; an Exception in the script is raised."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=item)],
                               usage=SimpleNamespace(input_tokens=2000, output_tokens=900),
                               stop_reason="end_turn")


def _screen(monkeypatch, script, record=RECORD):
    client = ScriptedClient(script)
    monkeypatch.setattr(llm, "get_client", lambda: client)
    decision = screen_record(PROTOCOL, record, "A", "claude-opus-5-5", build_system_prompt(PROTOCOL), "sha")
    return decision, client


def test_screener_includes_a_clean_record_and_verifies_its_quotes(monkeypatch):
    decision, client = _screen(monkeypatch, [reply()])
    assert decision.decision == "include" and decision.screener == "A:claude-opus-5-5"
    assert all(j.quote_verified for j in decision.judgements if j.met == "yes")
    assert client.requests[0]["model"] == "claude-opus-5-5"


def test_invented_quote_from_the_model_is_caught(monkeypatch):
    decision, _ = _screen(monkeypatch, [reply(IC1=("yes", "regions of northern Italy and Bavaria"))])
    assert decision.decision == "unclear" and "IC1: quote not found" in decision.notes


def test_unusable_reply_is_retried(monkeypatch):
    decision, client = _screen(monkeypatch, ["I cannot answer.", reply(IC2="no")])
    assert (decision.decision, decision.reason_code) == ("exclude", "WRONG_CONCEPT")
    assert len(client.requests) == 2


def test_persistent_failure_is_an_error_not_an_exclusion(monkeypatch):
    decision, client = _screen(monkeypatch, [RuntimeError("529 overloaded")])
    assert decision.decision == "error" and "529 overloaded" in decision.notes
    assert len(client.requests) == 3


# ── Combining two screeners ─────────────────────────────────────────────────

def sd(screener, decision, reason=None, notes=""):
    return ScreeningDecision(record_id="r1", screener=screener, decision=decision, reason_code=reason,
                             notes=notes, decided_at="2026-01-01T00:00:00+00:00")


@pytest.mark.parametrize("a,b,expected", [
    (("include", None), ("include", None), ("include", None, "agreement")),
    (("exclude", "WRONG_CONCEPT"), ("exclude", "WRONG_CONCEPT"), ("exclude", "WRONG_CONCEPT", "agreement")),
    (("exclude", "WRONG_PHENOMENON"), ("exclude", "WRONG_CONTEXT"), ("exclude", "WRONG_CONTEXT", "agreement")),
    (("include", None), ("exclude", "WRONG_CONCEPT"), ("pending", None, "pending")),
    (("include", None), ("unclear", None), ("pending", None, "pending")),
    (("exclude", "WRONG_CONCEPT"), ("unclear", None), ("pending", None, "pending")),
    (("exclude", "WRONG_CONCEPT"), ("error", None), ("pending", None, "pending")),
])
def test_only_agreement_is_final(a, b, expected):
    final = combine("r1", [sd("A:m1", *a), sd("B:m2", *b)])
    assert (final.decision, final.reason_code, final.decided_by) == expected


def test_metadata_exclusion_is_final_and_missing_abstract_goes_to_a_person():
    assert combine("r1", [sd("metadata", "exclude", "WRONG_LANGUAGE")]).decided_by == "metadata"
    pending = combine("r1", [sd("metadata", "unclear", "NO_ABSTRACT", "no abstract available")])
    assert pending.decision == "pending" and pending.reason_code == "NO_ABSTRACT"


# ── Whole batch ─────────────────────────────────────────────────────────────

def test_batch_screens_every_record_with_both_screeners(monkeypatch):
    def create(**kwargs):
        # Screener B (the other model) always sees no labour dimension.
        text = reply(IC2="no") if kwargs["model"] == "claude-sonnet-5-5" else reply()
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)],
                               usage=SimpleNamespace(input_tokens=2000, output_tokens=900), stop_reason="end_turn")

    monkeypatch.setattr(llm, "get_client", lambda: SimpleNamespace(messages=SimpleNamespace(create=create)))
    records = [RECORD,
               RECORD.model_copy(update={"record_id": "10.1/fr", "language": "fr"}),
               RECORD.model_copy(update={"record_id": "10.1/noabs", "abstract": None})]
    screeners = [{"name": "A", "model": "claude-opus-5-5"}, {"name": "B", "model": "claude-sonnet-5-5"}]

    decisions, finals, prompt_sha = screen_records(PROTOCOL, records, screeners, workers=2)

    assert len(prompt_sha) == 64
    assert [f.decision for f in finals] == ["pending", "exclude", "pending"]
    assert finals[0].pending_reason == "screeners disagree"
    assert len(decisions) == 4                                   # 2 model decisions + 2 metadata decisions
    assert set(llm.usage_summary()) == {"screen_A", "screen_B"}
    assert summarize(finals) == {"records": 3, "include": 0, "exclude": 1, "pending": 2,
                                 "exclusion_reasons": {"WRONG_LANGUAGE": 1},
                                 "decided_by": {"metadata": 1, "pending": 2}}
    stats = agreement(decisions)
    assert stats["records_compared"] == 1 and stats["same_decision"] == 0


def test_cohen_kappa():
    assert cohen_kappa(["i", "e", "i", "e"], ["i", "e", "i", "e"]) == 1.0
    assert cohen_kappa(["i", "i", "e", "e"], ["i", "e", "i", "e"]) == 0.0
    assert cohen_kappa(["i", "i"], ["i", "i"]) is None          # undefined: no variation
    assert cohen_kappa([], []) is None
