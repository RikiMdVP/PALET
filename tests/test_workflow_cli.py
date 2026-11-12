"""End-to-end workflow on a run directory: init, screen, adjudicate, replay."""

import csv
import json
import re
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
        self.assign_calls = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        user = kwargs["messages"][0]["content"]
        if "You chart records" in kwargs["system"]:
            self.assign_calls += 1
            quote = "coal mine closures in Silesia, Poland" if "10.1/include" in user else "Digital skills matter for growth"
            core = "RQ1" if "10.1/include" in user else "RQ2"
            items = [{"rq": f"RQ{i}", "relevance": "core" if f"RQ{i}" == core else ("partial" if i == 6 else "none"),
                      "evidence_quote": quote if f"RQ{i}" == core else ("an invented passage about welders" if i == 6 else None),
                      "rationale": "r"} for i in range(1, 8)]
            text = json.dumps({"assignments": items, "contribution": "It studies jobs.", "contribution_quote": quote,
                               "evidence_type": "empirical", "geography": ["Poland"]})
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)],
                                   usage=SimpleNamespace(input_tokens=1500, output_tokens=700), stop_reason="end_turn")
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
    # The workflow is tested with two different models, whatever palet.toml says today.
    monkeypatch.setattr(cli.config, "get_screening_settings", lambda: {
        "screeners": [{"name": "A", "model": "claude-opus-5-5"}, {"name": "B", "model": "claude-sonnet-5-5"}],
        "workers": 2})
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

    # Charting of the two included records.
    assert cli.main(["assign", "--run", "t1", "--estimate"]) == 0
    assert w.model.assign_calls == 0
    assert cli.main(["assign", "--run", "t1"]) == 0
    assert w.model.assign_calls == 2
    from palet.assign import RecordAssignment
    assignments = {a.record_id: a for a in run.read_models("assignments.jsonl", RecordAssignment)}
    assert assignments["10.1/include"].rqs("core") == ["RQ1"]
    assert assignments["10.1/disagree"].rqs("core") == ["RQ2"]
    # RQ6 was claimed with an invented quote: not counted, and flagged.
    assert assignments["10.1/include"].assigned_rqs == ["RQ1"]
    assert "quote not found for RQ6" in assignments["10.1/include"].needs_review[0]

    # Reporting.
    capsys.readouterr()
    assert cli.main(["report", "--run", "t1", "--partial-year", "2021"]) == 0
    out = capsys.readouterr().out
    assert "Identificados: 5 | Duplicados: 0 | Cribados: 5 | Excluidos: 3 | Incluidos: 2 | Pendientes: 0" in out
    report_dir = w.run_dir / "report"
    for name in ("prisma_flow.pdf", "prisma_flow.png", "prisma_counts.json", "prisma_scr_checklist.md",
                 "prisma_scr_checklist.csv", "methods_appendix.md", "excluded_records.csv",
                 "table_included_by_rq.md", "evidence_table.csv", "citations_by_rq.csv",
                 "fig_included_by_rq.pdf", "fig_included_by_rq.png", "fig_included_by_year.pdf"):
        assert (report_dir / name).stat().st_size > 0, name
    counts = json.loads((report_dir / "prisma_counts.json").read_text(encoding="utf-8"))
    assert counts["identified"] == 5 and counts["screened"] == 5
    assert counts["included"] + counts["excluded"] + counts["pending"] == counts["screened"]
    assert counts["exclusion_reasons"] == {"WRONG_LANGUAGE": 1, "WRONG_CONTEXT": 1, "NO_ABSTRACT": 1}
    assert counts["decided_by_authors"] == 2 and counts["included_by_agreement"] == 1
    appendix = (report_dir / "methods_appendix.md").read_text(encoding="utf-8")
    assert "claude-opus-5-5" in appendix and "claude-sonnet-5-5" in appendix
    assert "was not archived" in appendix and "not validated against independent human screening" in appendix
    assert "| RQ1 | 1 | 0 |" in appendix
    checklist = (report_dir / "prisma_scr_checklist.md").read_text(encoding="utf-8")
    assert checklist.count("\n| ") == 23 and "| 22 | Funding | Funding |" in checklist
    table = (report_dir / "table_included_by_rq.md").read_text(encoding="utf-8")
    assert "| RQ1 | 1 | 0 | Kowalski (2021) |" in table and "| RQ2 | 1 | 0 | Smith (2019) |" in table
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

    assert cli.main(["search", "--run", "t1", "--source", "oa_rq4", "--count-only", "--show-filter"]) == 0
    out = capsys.readouterr().out
    assert "Resultados totales en OpenAlex (con filtros): 1" in out
    assert "from_publication_date:2013-01-01" in out and "type:article|review" in out and "language:en|es" in out

    seen = {}

    def fake_sample(query, **kwargs):
        seen.update(kwargs)
        return [{"id": "https://openalex.org/W1", "title": "A sampled\n title", "publication_year": 2020,
                 "type": "article", "language": "en",
                 "primary_location": {"source": {"display_name": "Journal S"}}}], 77, "filter"

    monkeypatch.setattr(cli, "sample_openalex", fake_sample)
    assert cli.main(["search", "--run", "t1", "--source", "oa_rq4", "--sample", "30", "--seed", "7"]) == 0
    out = capsys.readouterr().out
    assert " 1. [2020] A sampled title — Journal S" in out and "Resultados totales (con filtros): 77" in out
    assert seen["n"] == 30 and seen["seed"] == 7 and seen["year_from"] == 2013 and seen["languages"] == ["en", "es"]

    # A source can narrow the languages of the protocol, but not widen them.
    data["sources"][-1]["languages"] = ["en"]
    w.protocol.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert cli.main(["search", "--run", "t1", "--source", "oa_rq4", "--sample", "5"]) == 0
    assert seen["languages"] == ["en"] and "idiomas en;" in capsys.readouterr().out
    data["sources"][-1]["languages"] = ["en", "fr"]
    w.protocol.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert cli.main(["search", "--run", "t1", "--source", "oa_rq4", "--count-only"]) == 1
    assert "no admite" in capsys.readouterr().err
    del data["sources"][-1]["languages"]
    w.protocol.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert (w.run_dir / "previews" / "oa_rq4_sample_n30_seed7.csv").is_file()
    assert not (w.run_dir / "sources" / "oa_rq4.jsonl").exists()          # a sample records nothing
    assert len(Run.open(w.run_dir).manifest["searches"]) == 1
    assert cli.main(["search", "--run", "t1", "--source", "oa_rq4"]) == 1          # not approved yet
    assert "aún no está aprobada" in capsys.readouterr().err

    data["sources"][-1]["status"] = "approved"
    w.protocol.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert cli.main(["search", "--run", "t1", "--source", "oa_rq4"]) == 0
    run = Run.open(w.run_dir)
    records = run.read_models("records.jsonl", Record)
    assert len(records) == 6 and any(r.record_id == "10.1/new" for r in records)
    assert [s["query_id"] for s in run.manifest["searches"]] == ["scopus_test", "oa_rq4"]


def test_approve_search_edits_only_that_source(tmp_path, capsys):
    protocol = tmp_path / "protocol.yaml"
    # Start from a copy in which no supplementary search has been approved yet.
    before = re.sub(r"status: approved\n    approved_by: [^\n]*\n    approved_at: [^\n]*", "status: proposed",
                    CHAPTER_PROTOCOL.read_text(encoding="utf-8"))
    protocol.write_text(before, encoding="utf-8")
    assert cli.main(["approve-search", "--protocol", str(protocol), "--source", "openalex_supplementary_rq5",
                     "--by", "RMVP; FRM"]) == 0
    from palet.protocol import load_protocol
    loaded = load_protocol(protocol)
    assert loaded.source("openalex_supplementary_rq5").model_extra["status"] == "approved"
    assert loaded.source("openalex_supplementary_rq5").model_extra["approved_by"] == "RMVP; FRM"
    assert loaded.source("openalex_supplementary_rq4_d").model_extra["status"] == "proposed"
    after = protocol.read_text(encoding="utf-8")
    assert after.count("status: approved") == before.count("status: approved") + 1
    assert "# Supplementary searches (decision D1)" in after            # comments are kept
    assert cli.main(["approve-search", "--protocol", str(protocol), "--source", "openalex_supplementary_rq5",
                     "--by", "RMVP"]) == 0
    assert "ya estaba aprobada" in capsys.readouterr().out


def test_check_citations_command(tmp_path, capsys):
    manuscript = tmp_path / "chapter.txt"
    manuscript.write_text("\n".join([
        "Abstract", "As Webber (2017) and Green et al. (1997) argue.", "References",
        "Webber, D. (2017) European disintegration? London: Palgrave.",
        "McCann, P. (2018) The regional and urban policy of the EU."]), encoding="utf-8")
    assert cli.main(["check-citations", "--manuscript", str(manuscript), "--out", str(tmp_path / "out")]) == 0
    assert "Citadas y no listadas: 1 | Listadas y no citadas: 1" in capsys.readouterr().out
    report_text = (tmp_path / "out" / "citation_check.md").read_text(encoding="utf-8")
    assert "Green et al. (1997)" in report_text and "McCann, P. (2018)" in report_text


def test_workflow_with_a_single_screener(workspace, capsys):
    w = workspace
    assert cli.main(["init", "--protocol", str(w.protocol), "--label", "test", "--run-id", "t1"]) == 0
    assert cli.main(["screen", "--run", "t1", "--screeners", "claude-sonnet-5-5"]) == 0
    out = capsys.readouterr().out
    assert "AVISO: un solo cribador" in out
    assert w.model.calls == 3                                   # 3 records x 1 screener
    finals = _finals(w.run_dir)
    assert finals["10.1/include"].decided_by == "single_screener"
    assert finals["10.1/disagree"].decision == "exclude"        # nobody to disagree with: final, unchecked
    assert cli.main(["report", "--run", "t1"]) == 0
    appendix = (w.run_dir / "report" / "methods_appendix.md").read_text(encoding="utf-8")
    assert "once, by a single AI model (`claude-sonnet-5-5`)" in appendix
    assert "there was no second screener and no cross-check" in appendix
    assert "no inter-screener agreement can be reported" in appendix
    assert "agreement of the two models" not in appendix
    counts = json.loads((w.run_dir / "report" / "prisma_counts.json").read_text(encoding="utf-8"))
    assert counts["model_screeners"] == ["A:claude-sonnet-5-5"]


def test_screeners_option_rejects_unknown_models(workspace):
    w = workspace
    assert cli.main(["init", "--protocol", str(w.protocol), "--label", "test", "--run-id", "t1"]) == 0
    assert cli.main(["screen", "--run", "t1", "--screeners", "not-a-model"]) != 0
    assert w.model.calls == 0
