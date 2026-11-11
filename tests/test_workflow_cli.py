"""End-to-end workflow on a run directory: init, screen, adjudicate, replay."""

import csv
import json
import shutil
from types import SimpleNamespace

import pytest
import yaml
from openpyxl import load_workbook

from palet import cli, llm, runs
from palet.models import Record
from palet.screening import FinalDecision
from palet.runs import ROOT, Run

CHAPTER_PROTOCOL = ROOT / "config" / "protocol_isabel_chapter_v1.yaml"
COLUMNS = ["Authors", "Title", "Year", "Source title", "DOI", "Abstract", "Author Keywords",
           "Language of Original Document", "Document Type", "EID"]
ROWS = [
    ("Kowalski P.", "Coal phase-out and employment in Silesia", "2021", "10.1/include",
     "We study employment after coal mine closures in Silesia, Poland, under the Just Transition Fund.", "English"),
    ("Li W.", "Urban air quality in Chinese cities", "2020", "10.1/exclude",
     "We measure particulate matter in forty cities of China.", "English"),
    ("Smith J.", "Digital skills and regional growth", "2019", "10.1/disagree",
     "Digital skills matter for growth.", "English"),
    ("Dupont A.", "Transition juste et emploi", "2022", "10.1/french",
     "Une étude sur l'emploi.", "French"),
    ("Nobody N.", "A paper without abstract", "2018", "10.1/noabstract", "[No abstract available]", "English"),
]
LLM_IDS = ["IC1", "IC2", "IC3", "EC1", "EC2", "EC3"]


def _reply(pattern, quote):
    base = {"IC1": "yes", "IC2": "yes", "IC3": "yes", "EC1": "no", "EC2": "no", "EC3": "no"}
    base.update(pattern)
    return json.dumps({"judgements": [
        {"criterion_id": c, "met": base[c], "evidence_quote": quote if base[c] == "yes" else None, "rationale": "r"}
        for c in LLM_IDS]})


class FakeModel:
    """Answers by record and by model, and counts real calls."""

    def __init__(self):
        self.calls = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        user = kwargs["messages"][0]["content"]
        if "10.1/include" in user:
            text = _reply({}, "coal mine closures in Silesia, Poland")
        elif "10.1/exclude" in user:
            text = _reply({"IC1": "no", "IC2": "no", "IC3": "no", "EC1": "yes"}, "forty cities of China")
        else:   # the two models disagree on this one
            text = _reply({} if kwargs["model"] == "claude-opus-5-5" else {"IC2": "no"}, "Digital skills matter for growth")
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)],
                               usage=SimpleNamespace(input_tokens=2000, output_tokens=900), stop_reason="end_turn")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    export = tmp_path / "scopus.csv"
    with open(export, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for authors, title, year, doi, abstract, language in ROWS:
            writer.writerow([authors, title, year, "Journal", doi, abstract, "kw", language, "Article", "eid"])

    data = yaml.safe_load(CHAPTER_PROTOCOL.read_text(encoding="utf-8"))
    data["sources"] = [{"id": "scopus_test", "type": "manual_import", "file": str(export),
                        "platform": "Scopus web export", "query_string": None}]
    protocol = tmp_path / "protocol.yaml"
    protocol.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    monkeypatch.setattr(runs, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(cli, "RUNS_DIR", tmp_path / "runs")
    model = FakeModel()
    monkeypatch.setattr(llm, "get_client", lambda: model)
    llm.configure(cache_dir=tmp_path / "cache")
    return SimpleNamespace(tmp=tmp_path, protocol=protocol, model=model, run_dir=tmp_path / "runs" / "t1")


def _finals(run_dir):
    return {f.record_id: f for f in Run.open(run_dir).read_models("final_decisions.jsonl", FinalDecision)}


def test_full_workflow(workspace, capsys):
    w = workspace
    assert cli.main(["init", "--protocol", str(w.protocol), "--label", "test", "--run-id", "t1"]) == 0
    run = Run.open(w.run_dir)
    assert len(run.read_models("records.jsonl", Record)) == 5
    assert run.manifest["searches"][0]["total_hits"] == 5

    # Estimate only: no call is made.
    assert cli.main(["screen", "--run", "t1", "--estimate"]) == 0
    assert w.model.calls == 0 and "Estimación total" in capsys.readouterr().out

    assert cli.main(["screen", "--run", "t1", "--workers", "2"]) == 0
    assert w.model.calls == 6                                   # 3 records x 2 screeners; 2 decided by metadata
    finals = _finals(w.run_dir)
    assert finals["10.1/include"].decision == "include" and finals["10.1/include"].decided_by == "agreement"
    assert (finals["10.1/exclude"].decision, finals["10.1/exclude"].reason_code) == ("exclude", "WRONG_CONTEXT")
    assert (finals["10.1/french"].decision, finals["10.1/french"].decided_by) == ("exclude", "metadata")
    assert finals["10.1/disagree"].decision == "pending" and finals["10.1/noabstract"].decision == "pending"

    statuses = {r.record_id: r.status for r in run.read_models("records.jsonl", Record)}
    assert statuses["10.1/include"] == "ta_included" and statuses["10.1/disagree"] == "ta_unclear"
    stats = json.loads((w.run_dir / "screening_stats.json").read_text(encoding="utf-8"))
    assert stats["pending_for_humans"] == 2 and stats["agreement"]["records_compared"] == 3
    manifest = run.manifest
    assert manifest["llm_usage"]["screen"]["screen_A"]["calls"] == 3
    assert len(manifest["prompts"]["screen_system_v1"]) == 64

    # Replay: identical decisions, byte for byte, without a single call.
    before = {name: (w.run_dir / name).read_bytes() for name in ("decisions.jsonl", "final_decisions.jsonl")}
    assert cli.main(["screen", "--run", "t1", "--replay"]) == 0
    assert w.model.calls == 6
    for name, content in before.items():
        assert (w.run_dir / name).read_bytes() == content

    # A person fills the workbook.
    workbook_path = w.run_dir / "adjudication.xlsx"
    workbook = load_workbook(workbook_path)
    sheet = workbook["adjudication"]
    header = [c.value for c in sheet[1]]
    assert sheet.max_row == 3
    for row in range(2, 4):
        record_id = sheet.cell(row=row, column=header.index("record_id") + 1).value
        include = record_id == "10.1/disagree"
        sheet.cell(row=row, column=header.index("human_decision") + 1).value = "include" if include else "exclude"
        if not include:
            sheet.cell(row=row, column=header.index("human_reason_code") + 1).value = "NO_ABSTRACT"
    filled = w.tmp / "filled.xlsx"
    workbook.save(filled)

    assert cli.main(["adjudicate", "--run", "t1", "--file", str(filled), "--initials", "rmvp"]) == 0
    finals = _finals(w.run_dir)
    assert finals["10.1/disagree"].decision == "include" and finals["10.1/disagree"].decided_by == "human:RMVP"
    assert (finals["10.1/noabstract"].decision, finals["10.1/noabstract"].reason_code) == ("exclude", "NO_ABSTRACT")
    assert not any(f.decision == "pending" for f in finals.values())

    # Re-screening later keeps the human decisions.
    assert cli.main(["screen", "--run", "t1", "--replay"]) == 0
    assert _finals(w.run_dir)["10.1/disagree"].decided_by == "human:RMVP"
    assert cli.main(["status", "--run", "t1"]) == 0


def test_incomplete_workbook_is_rejected_whole(workspace, capsys):
    w = workspace
    cli.main(["init", "--protocol", str(w.protocol), "--label", "test", "--run-id", "t1"])
    cli.main(["screen", "--run", "t1"])
    workbook = load_workbook(w.run_dir / "adjudication.xlsx")
    sheet = workbook["adjudication"]
    header = [c.value for c in sheet[1]]
    sheet.cell(row=2, column=header.index("human_decision") + 1).value = "exclude"      # no reason code
    filled = w.tmp / "filled.xlsx"
    workbook.save(filled)

    assert cli.main(["adjudicate", "--run", "t1", "--file", str(filled), "--initials", "RMVP"]) == 1
    assert "needs a valid human_reason_code" in capsys.readouterr().err
    assert sum(f.decision == "pending" for f in _finals(w.run_dir).values()) == 2


def test_screening_refuses_a_draft_protocol(workspace, capsys):
    w = workspace
    data = yaml.safe_load(w.protocol.read_text(encoding="utf-8"))
    data.update(status="draft", approved_by=None, approved_at=None)
    w.protocol.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    cli.main(["init", "--protocol", str(w.protocol), "--label", "test", "--run-id", "t1"])
    assert cli.main(["screen", "--run", "t1"]) == 1
    assert "still a draft" in capsys.readouterr().err and w.model.calls == 0


def test_search_needs_an_approved_string_but_count_only_does_not(workspace, monkeypatch, capsys):
    from palet import search as search_module

    w = workspace
    shutil.copy(w.protocol, w.tmp / "backup.yaml")
    data = yaml.safe_load(w.protocol.read_text(encoding="utf-8"))
    data["sources"].append({"id": "oa_rq4", "type": "openalex", "status": "proposed",
                            "blocks": {"a": ["reskilling"], "b": ["Europe"]}})
    w.protocol.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    cli.main(["init", "--protocol", str(w.protocol), "--label", "test", "--run-id", "t1"])

    work = {"id": "https://openalex.org/W9", "doi": "https://doi.org/10.1/new", "title": "Reskilling in Spain",
            "publication_year": 2023, "type": "article", "language": "en",
            "abstract_inverted_index": {"Reskilling": [0], "works": [1]}}
    execution = {"query_id": "oa_rq4", "source": "openalex", "platform": "p", "query_string": "q", "filters": {},
                 "executed_at": "2026-11-11T00:00:00+00:00", "total_hits": 1, "downloaded": 1, "truncated": False}

    def fake_search(query_id, query, **kwargs):
        if kwargs["count_only"]:
            return [], {**execution, "downloaded": 0}
        return [work], execution

    monkeypatch.setattr(cli, "search_openalex", fake_search)
    assert search_module is not None

    assert cli.main(["search", "--run", "t1", "--source", "oa_rq4", "--count-only"]) == 0
    assert "Resultados totales en OpenAlex: 1" in capsys.readouterr().out
    assert cli.main(["search", "--run", "t1", "--source", "oa_rq4"]) == 1          # not approved yet
    assert "aún no está aprobada" in capsys.readouterr().err

    data["sources"][-1]["status"] = "approved"
    w.protocol.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert cli.main(["search", "--run", "t1", "--source", "oa_rq4"]) == 0
    run = Run.open(w.run_dir)
    records = run.read_models("records.jsonl", Record)
    assert len(records) == 6 and any(r.record_id == "10.1/new" for r in records)
    assert [s["query_id"] for s in run.manifest["searches"]] == ["scopus_test", "oa_rq4"]
