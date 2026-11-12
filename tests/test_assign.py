"""Charting of included records: assignments need a quote found in the record."""

import json

import pytest

from palet.assign import (RecordAssignment, RQRelevance, build_system_prompt, display_surname, parse_reply,
                          short_citation, summarize)
from palet.models import Record
from palet.protocol import load_protocol
from palet.runs import ROOT

PROTOCOL = load_protocol(ROOT / "config" / "protocol_isabel_chapter_v1.yaml")
RQS = list(PROTOCOL.research_questions)


def reply(**relevance):
    items = [{"rq": rq, "relevance": relevance.get(rq, "none"),
              "evidence_quote": "a passage" if relevance.get(rq, "none") != "none" else None, "rationale": "r"}
             for rq in RQS]
    return json.dumps({"assignments": items, "contribution": "It finds X.", "contribution_quote": "a passage",
                       "evidence_type": "empirical", "geography": ["Spain", " "]})


def test_prompt_contains_every_research_question():
    prompt = build_system_prompt(PROTOCOL)
    assert "{{" not in prompt
    for key, text in PROTOCOL.research_questions.items():
        assert f"- {key}: {text}" in prompt


def test_reply_is_parsed_in_protocol_order():
    parsed = parse_reply("```json\n" + reply(RQ3="core", RQ1="partial") + "\n```", PROTOCOL)
    assert [i.rq for i in parsed["items"]] == RQS
    assert parsed["evidence_type"] == "empirical" and parsed["geography"] == ["Spain"]


@pytest.mark.parametrize("mutate", [
    lambda d: d["assignments"].pop(),
    lambda d: d["assignments"][0].update(rq="RQ9"),
    lambda d: d["assignments"][0].update(relevance="high"),
    lambda d: d.update(evidence_type="opinion"),
    lambda d: d.update(geography="Spain"),
])
def test_invalid_replies_are_rejected(mutate):
    data = json.loads(reply(RQ1="core"))
    mutate(data)
    with pytest.raises(Exception):
        parse_reply(json.dumps(data), PROTOCOL)


def _assignment(**kwargs):
    items = [RQRelevance(rq="RQ1", relevance="core", evidence_quote="q", quote_verified=True),
             RQRelevance(rq="RQ2", relevance="partial", evidence_quote="q", quote_verified=True),
             RQRelevance(rq="RQ3", relevance="core", evidence_quote="invented", quote_verified=False),
             RQRelevance(rq="RQ4", relevance="none")]
    defaults = dict(record_id="r1", model="m", items=items, contribution="c",
                    contribution_quote="q", contribution_quote_verified=True, evidence_type="empirical")
    defaults.update(kwargs)
    return RecordAssignment(**defaults)


def test_only_assignments_with_a_verified_quote_count():
    assignment = _assignment()
    assert assignment.rqs("core") == ["RQ1"] and assignment.rqs("partial") == ["RQ2"]
    assert assignment.assigned_rqs == ["RQ1", "RQ2"]
    assert assignment.needs_review == ["quote not found for RQ3"]


def test_records_without_any_question_or_with_errors_are_flagged():
    none = _assignment(items=[RQRelevance(rq="RQ1", relevance="none")])
    assert "not assigned to any research question" in none.needs_review[0]
    assert _assignment(status="error", items=[]).needs_review == ["charting failed"]


def test_summary_counts_per_question():
    summary = summarize(PROTOCOL, [_assignment(), _assignment(record_id="r2")])
    assert summary["per_rq"]["RQ1"] == {"core": 2, "partial": 0}
    assert summary["per_rq"]["RQ2"] == {"core": 0, "partial": 2}
    assert summary["per_rq"]["RQ3"] == {"core": 0, "partial": 0}          # unverified quotes
    assert summary["assigned_to_several_rqs"] == 2 and summary["needs_review"] == 2


@pytest.mark.parametrize("author,expected", [
    ("Sotarauta M.", "Sotarauta"), ("Rodríguez-Pose A.", "Rodríguez-Pose"), ("De La Fuente A.B.", "De La Fuente"),
    ("Sotarauta, Markku", "Sotarauta"), ("Maria Denisa Vasilescu", "Vasilescu"), ("", ""),
])
def test_display_surname(author, expected):
    assert display_surname(author) == expected


def test_short_citation():
    make = lambda authors: Record.build(title="A long title about regional policy and jobs", authors=authors, year=2020)  # noqa: E731
    assert short_citation(make(["Smith J."])) == "Smith (2020)"
    assert short_citation(make(["Smith J.", "Jones K."])) == "Smith and Jones (2020)"
    assert short_citation(make(["Smith J.", "Jones K.", "Lee W."])) == "Smith et al. (2020)"
    assert short_citation(make([])).endswith("(2020)")
