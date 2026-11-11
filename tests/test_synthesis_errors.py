"""A failed synthesis must be flagged as an error, never rendered as content."""

import json
from types import SimpleNamespace

import pandas as pd
import pytest

import synthesis_module
from report_generator_v2 import generate_latex_report

RQ = "Does X create jobs?"


class FakeClient:
    def __init__(self, reply=None, error=None):
        self.reply = reply
        self.error = error
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            content=[SimpleNamespace(text=self.reply)],
            usage=SimpleNamespace(input_tokens=100, output_tokens=50),
        )


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(synthesis_module.time, "sleep", lambda seconds: None)


@pytest.fixture
def papers_df():
    return pd.DataFrame(
        {
            "title": ["Paper A", "Paper B"],
            "authors": ["Ana A.", "Bea B."],
            "year": [2020, 2021],
            "doi": ["10.1/a", "10.1/b"],
            "source": ["Journal A", "Journal B"],
            "cited_by_count": [10, 5],
            "abstract": ["Jobs and the green transition.", "Skills and automation."],
            "concepts": ["Employment; Policy", "Skills; Policy"],
            "open_access": [True, False],
            "database": ["OpenAlex", "OpenAlex"],
        }
    )


def _synthesize(monkeypatch, client, papers_df, paper_ids=(0, 1)):
    monkeypatch.setattr(synthesis_module, "get_client", lambda: client)
    return synthesis_module.generate_narrative_synthesis(
        rq_index=1, rq_text=RQ, paper_ids=list(paper_ids),
        papers_df=papers_df, reasoning_map={}, verbose=False,
    )


def test_failed_synthesis_has_status_error(monkeypatch, papers_df):
    result = _synthesize(monkeypatch, FakeClient(error=RuntimeError("529 overloaded")), papers_df)
    assert result["status"] == "error"
    assert "529 overloaded" in result["error"]
    assert result["rq_index"] == 1


def test_successful_synthesis_has_status_ok(monkeypatch, papers_df):
    reply = json.dumps({"rq": RQ, "synthesis": {"overview": "Fine."}, "confidence": "high"})
    result = _synthesize(monkeypatch, FakeClient(reply=reply), papers_df)
    assert result["status"] == "ok"
    assert result["synthesis"]["overview"] == "Fine."


def test_rq_without_papers_is_flagged_and_keeps_its_index(monkeypatch, papers_df):
    result = _synthesize(monkeypatch, FakeClient(error=AssertionError("must not be called")),
                         papers_df, paper_ids=())
    assert result["status"] == "no_papers"
    assert result["rq_index"] == 1


def test_failed_gap_detection_has_status_error(monkeypatch, papers_df):
    monkeypatch.setattr(synthesis_module, "get_client", lambda: FakeClient(reply="not json"))
    gaps = synthesis_module.detect_literature_gaps(
        rqs=[RQ], assignments={"RQ1": [0, 1]}, papers_df=papers_df, syntheses=[], verbose=False,
    )
    assert gaps["status"] == "error"
    assert gaps["error"]


def _report(tmp_path, papers_df, syntheses, gaps):
    output_path = tmp_path / "report_test.tex"
    generate_latex_report(
        summary_data={"timestamp": "20260101_000000", "assignments": {"RQ1": [0, 1]}},
        arq_data={"research_questions": [RQ], "keywords": ["jobs"]},
        papers_df=papers_df,
        map_results=[],
        output_path=str(output_path),
        seed_prompt="seed",
        prisma_diagram=False,
        syntheses=syntheses,
        gaps=gaps,
    )
    return output_path.read_text(encoding="utf-8")


def test_report_shows_a_notice_instead_of_failed_synthesis(monkeypatch, tmp_path, papers_df):
    failed = _synthesize(monkeypatch, FakeClient(error=RuntimeError("529 overloaded")), papers_df)
    monkeypatch.setattr(synthesis_module, "get_client", lambda: FakeClient(reply="not json"))
    gaps = synthesis_module.detect_literature_gaps(
        rqs=[RQ], assignments={"RQ1": [0, 1]}, papers_df=papers_df, syntheses=[failed], verbose=False,
    )
    tex = _report(tmp_path, papers_df, [failed], gaps)

    assert "Synthesis could not be generated" in tex
    assert "Gap analysis could not be generated" in tex
    # The placeholder text must not be presented as findings.
    assert "Synthesis generation failed after" not in tex
    assert "Gap detection failed" not in tex
    assert "Confidence: low" not in tex


def test_report_renders_successful_synthesis_as_before(tmp_path, papers_df):
    ok = {
        "rq": RQ, "rq_index": 1, "status": "ok", "confidence": "high",
        "paper_count_used": 2, "paper_count_assigned": 2,
        "synthesis": {"overview": "Evidence is consistent."},
    }
    tex = _report(tmp_path, papers_df, [ok], None)
    assert "Evidence is consistent." in tex
    assert "Synthesis could not be generated" not in tex
