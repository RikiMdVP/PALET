"""Errors are not exclusions: a failed MAP analysis must never count as 'not relevant'."""

import json
from types import SimpleNamespace

import pandas as pd
import pytest

import map_module_v2
from palet import llm
from prisma_validator import build_prisma_data, generate_prisma_checklist

RQS = ["Does X create jobs?", "Does Y destroy jobs?"]
LONG_REASONING = "The abstract directly studies job creation linked to the green transition."


class FakeClient:
    """Stands in for the Anthropic client; replies with a fixed text or raises."""

    def __init__(self, reply=None, error=None):
        self.reply = reply
        self.error = error
        self.calls = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.reply)],
            usage=SimpleNamespace(input_tokens=100, output_tokens=50),
            stop_reason="end_turn",
        )


def _analyze(monkeypatch, client, abstract="An abstract about jobs."):
    monkeypatch.setattr(llm, "get_client", lambda: client)
    return map_module_v2.analyze_paper(
        paper_id=7, title="A paper", abstract=abstract, rqs=RQS, system_prompt="system"
    )


def _valid_reply(assignments):
    return json.dumps(
        {
            "paper_id": 7,
            "title": "A paper",
            "assignments": assignments,
            "reasoning": LONG_REASONING,
            "confidence": "high",
        }
    )


def test_api_failure_is_reported_as_error(monkeypatch):
    client = FakeClient(error=RuntimeError("529 overloaded"))
    result = _analyze(monkeypatch, client)
    assert result["status"] == "error"
    assert result["assignments"] == []
    assert "529 overloaded" in result["reasoning"]
    assert client.calls == 3  # retried before giving up


def test_invalid_json_is_reported_as_error(monkeypatch):
    result = _analyze(monkeypatch, FakeClient(reply="Sorry, I cannot answer in JSON."))
    assert result["status"] == "error"


def test_failed_validation_is_reported_as_error(monkeypatch):
    result = _analyze(monkeypatch, FakeClient(reply=_valid_reply(["RQ9"])))
    assert result["status"] == "error"


def test_successful_analysis_has_status_ok(monkeypatch):
    assigned = _analyze(monkeypatch, FakeClient(reply=_valid_reply(["RQ1"])))
    assert assigned["status"] == "ok"
    assert assigned["assignments"] == ["RQ1"]

    not_relevant = _analyze(monkeypatch, FakeClient(reply=_valid_reply([])))
    assert not_relevant["status"] == "ok"
    assert not_relevant["assignments"] == []


@pytest.mark.parametrize("abstract", [None, "", float("nan")])
def test_missing_abstract_is_not_sent_to_the_model(monkeypatch, abstract):
    client = FakeClient(reply=_valid_reply(["RQ1"]))
    result = _analyze(monkeypatch, client, abstract=abstract)
    assert result["status"] == "no_abstract"
    assert client.calls == 0


def _results():
    return [
        {"paper_id": 0, "assignments": ["RQ1", "RQ2"], "status": "ok"},
        {"paper_id": 1, "assignments": [], "status": "ok"},
        {"paper_id": 2, "assignments": [], "status": "error", "reasoning": "Error: timeout"},
        {"paper_id": 3, "assignments": ["unmatched_no_abstract"], "status": "no_abstract"},
    ]


def test_summary_keeps_errors_apart_from_not_relevant():
    summary = map_module_v2.generate_assignment_summary(_results(), RQS)
    assert summary["errors"] == [2]
    assert summary["unmatched_not_relevant"] == [1]
    assert summary["unmatched_no_abstract"] == [3]
    assert summary["RQ1"] == [0] and summary["RQ2"] == [0]


def test_summary_accepts_results_without_status():
    # Results saved by earlier versions carry no 'status' field.
    legacy = [{"paper_id": 0, "assignments": ["RQ1"]}, {"paper_id": 1, "assignments": []}]
    summary = map_module_v2.generate_assignment_summary(legacy, RQS)
    assert summary["RQ1"] == [0]
    assert summary["unmatched_not_relevant"] == [1]
    assert summary["errors"] == []


def test_prisma_does_not_count_errors_as_assessed_or_excluded():
    summary = map_module_v2.generate_assignment_summary(_results(), RQS)
    dedup = {"total_identified": 4, "duplicates_removed": 0, "total_after_dedup": 4}
    data = build_prisma_data({}, dedup, pd.DataFrame(), summary)
    assert data["analysis_errors"] == 1
    assert data["excluded_not_relevant"] == 1
    assert data["assessed_eligibility"] == 2
    assert data["included"] + data["excluded_not_relevant"] == data["assessed_eligibility"]


def test_prisma_checklist_flags_analysis_errors():
    base = {
        "databases": {"OpenAlex": 4},
        "duplicates_removed": 0,
        "excluded_no_abstract": 0,
        "excluded_not_relevant": 1,
        "included": 2,
    }
    clean = dict(generate_prisma_item(base | {"analysis_errors": 0}))
    failed = dict(generate_prisma_item(base | {"analysis_errors": 1}))
    assert clean["Todos los registros evaluados sin errores"] is True
    assert failed["Todos los registros evaluados sin errores"] is False


def generate_prisma_item(prisma_data):
    return [(item, passes) for item, passes, _ in generate_prisma_checklist(prisma_data)]
