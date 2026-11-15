"""Dashboard API of the 2.0 workflow: validation, cost gate, one job at a time."""

import json
import sys

import pytest
from fastapi.testclient import TestClient

import app as app_module
from palet import webflow


@pytest.fixture
def client(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    run = runs / "demo"
    (run / "report").mkdir(parents=True)
    manifest = {
        "run_id": "demo", "label": "Demo", "created_at": "2026-11-12T10:00:00+00:00",
        "updated_at": "2026-11-12T11:00:00+00:00",
        "protocol": {"path": "/somewhere/protocol_v1.yaml", "version": 1, "status": "approved"},
        "searches": [{"query_id": "scopus", "total_hits": 3, "downloaded": 3}],
        "steps": [{"step": "dedup", "at": "t1"},
                  {"step": "screen", "at": "t2", "limit": None,
                   "screeners": [{"name": "A", "model": "claude-opus-5-5"}, {"name": "B", "model": "claude-sonnet-5-5"}]}],
        "llm_usage": {"screen": {"screen_A": {"cost_usd": 1.25}, "screen_B": {"cost_usd": 0.5}}},
    }
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run / "records.jsonl").write_text('{"a":1}\n{"a":2}\n{"a":3}\n', encoding="utf-8")
    (run / "duplicates.jsonl").write_text("", encoding="utf-8")
    finals = [{"record_id": "1", "decision": "include"}, {"record_id": "2", "decision": "exclude", "reason_code": "WRONG_CONTEXT"},
              {"record_id": "3", "decision": "pending"}]
    (run / "final_decisions.jsonl").write_text("\n".join(json.dumps(f) for f in finals), encoding="utf-8")
    (run / "adjudication.xlsx").write_bytes(b"PK-fake")
    (runs / "not_a_run").mkdir()
    (runs / "_figure_preview").mkdir()

    monkeypatch.setattr(webflow, "RUNS_DIR", runs)
    monkeypatch.setattr(webflow, "_estimates", set())
    monkeypatch.setattr(webflow, "_job", {"running": False, "run_id": None, "step": None, "started_at": None,
                                          "finished_at": None, "returncode": None, "log": []})
    commands = []
    monkeypatch.setattr(webflow, "_run_and_capture", lambda command, timeout=180: (commands.append(command) or 0, "≈ 3.00 $"))

    def fake_stream(command, on_line):
        commands.append(command)
        on_line("hecho")
        return 0

    monkeypatch.setattr(webflow, "_stream", fake_stream)
    test_client = TestClient(app_module.app)
    test_client.commands = commands
    test_client.run_dir = run
    return test_client


def _wait_for_job():
    import time
    for _ in range(200):
        if not webflow.job_state()["running"]:
            return webflow.job_state()
        time.sleep(0.01)
    raise AssertionError("the job did not finish")


def test_page_and_run_listing(client):
    assert client.get("/workflow").status_code == 200
    assert [r["run_id"] for r in client.get("/api/v2/runs").json()] == ["demo"]     # folders without manifest are skipped


def test_overview_counts_and_next_step(client):
    data = client.get("/api/v2/runs/demo").json()
    assert data["records"] == 3 and data["duplicates_removed"] == 0
    assert data["screening"] == {"records": 3, "include": 1, "exclude": 1, "pending": 1,
                                 "exclusion_reasons": {"WRONG_CONTEXT": 1}}
    assert data["spent_usd"] == 1.75 and data["has_adjudication_file"] is True
    assert data["protocol"]["file"] == "protocol_v1.yaml"
    assert "pendientes de vuestra decisión" in data["hint"]


@pytest.mark.parametrize("run_id", ["nope", "..", ".hidden", "a b", "not_a_run"])
def test_unknown_or_unsafe_run_ids_are_rejected(client, run_id):
    assert client.get(f"/api/v2/runs/{run_id}").status_code in (400, 404)
    assert client.post(f"/api/v2/runs/{run_id}/run", json={"step": "dedup"}).status_code in (400, 404)
    assert client.commands == []


def test_screeners_endpoint_offers_catalogue_and_defaults(client):
    data = client.get("/api/v2/screeners").json()
    assert data["default"] == ["claude-opus-5-5", "claude-sonnet-5-5"]
    assert {"claude-opus-5-5", "claude-sonnet-5-5"} <= {m["id"] for m in data["models"]}


def test_paid_step_needs_estimate_with_same_options_and_confirmation(client):
    two = {"step": "screen", "screeners": ["claude-opus-5-5", "claude-sonnet-5-5"]}
    one = {"step": "screen", "screeners": ["claude-sonnet-5-5"]}

    refused = client.post("/api/v2/runs/demo/run", json={**two, "confirm_cost": True})
    assert refused.status_code == 400 and "estimación" in refused.json()["error"]

    estimate = client.post("/api/v2/runs/demo/estimate", json=two)
    assert estimate.json() == {"output": "≈ 3.00 $"}
    assert client.commands[-1] == [sys.executable, "-m", "palet", "screen", "--run", "demo",
                                   "--screeners", "claude-opus-5-5,claude-sonnet-5-5", "--estimate"]

    assert client.post("/api/v2/runs/demo/run", json=two).status_code == 400                         # not confirmed
    assert client.post("/api/v2/runs/demo/run", json={**one, "confirm_cost": True}).status_code == 400  # other options
    assert len(client.commands) == 1

    started = client.post("/api/v2/runs/demo/run", json={**two, "confirm_cost": True})
    assert started.status_code == 200
    job = _wait_for_job()
    assert job["returncode"] == 0 and job["log"] == ["hecho"] and job["step"] == "screen"
    assert client.commands[-1] == [sys.executable, "-m", "palet", "screen", "--run", "demo",
                                   "--screeners", "claude-opus-5-5,claude-sonnet-5-5"]


def test_replay_and_free_steps_need_no_estimate(client):
    assert client.post("/api/v2/runs/demo/run", json={"step": "assign", "replay": True}).status_code == 200
    _wait_for_job()
    assert client.commands[-1][-1] == "--replay"
    assert client.post("/api/v2/runs/demo/run", json={"step": "report", "partial_year": 2026}).status_code == 200
    _wait_for_job()
    assert client.commands[-1][-2:] == ["--partial-year", "2026"]


@pytest.mark.parametrize("body", [
    {"step": "search"}, {"step": "screen", "screeners": ["not-a-model"]},
    {"step": "screen", "screeners": ["claude-opus-5-5"] * 3}, {"step": "screen", "screeners": "claude-opus-5-5"},
    {"step": "screen", "limit": "10; rm -rf"}, {"step": "report", "partial_year": "2026 --x"},
])
def test_invalid_options_never_reach_a_command(client, body):
    assert client.post("/api/v2/runs/demo/run", json={**body, "replay": True}).status_code == 400
    assert client.commands == []


def test_only_one_job_at_a_time(client, monkeypatch):
    monkeypatch.setitem(webflow._job, "running", True)
    assert client.post("/api/v2/runs/demo/run", json={"step": "dedup"}).status_code == 409
    monkeypatch.setitem(webflow._job, "running", False)
    monkeypatch.setattr(webflow, "other_job_running", lambda: True)
    assert client.post("/api/v2/runs/demo/run", json={"step": "dedup"}).status_code == 409
    assert client.commands == []


def test_adjudication_upload(client):
    url = "/api/v2/runs/demo/adjudicate"
    assert client.post(url + "?initials=R2", content=b"PK-data").status_code == 400
    assert client.post(url + "?initials=RMV", content=b"not a workbook").status_code == 400
    assert client.commands == [] and not (client.run_dir / "uploads").exists()

    done = client.post(url + "?initials=rmv", content=b"PK-data")
    assert done.status_code == 200
    _wait_for_job()
    saved = client.run_dir / "uploads" / done.json()["saved_as"]
    assert saved.read_bytes() == b"PK-data" and saved.name.endswith("_RMV.xlsx")
    assert client.commands[-1][3:] == ["adjudicate", "--run", "demo", "--file", str(saved), "--initials", "RMV"]


def test_overview_reports_the_stages_in_order(client):
    stages = client.get("/api/v2/runs/demo").json()["stages"]
    assert [s["id"] for s in stages] == ["protocol", "search", "dedup", "journals", "screen", "adjudicate",
                                         "assign", "report"]
    status = {s["id"]: s["status"] for s in stages}
    assert status["protocol"] == "done" and status["dedup"] == "done" and status["screen"] == "done"
    assert status["journals"] == "skipped"                     # the protocol of the fixture cannot be read: no lists
    assert status["adjudicate"] == "current"                   # one record is pending
    assert status["assign"] == "todo" and status["report"] == "todo"


def test_search_and_free_steps_build_the_right_commands(client):
    assert client.post("/api/v2/runs/demo/run", json={"step": "search", "source": "openalex_rq1",
                                                      "count_only": True}).status_code == 200
    _wait_for_job()
    assert client.commands[-1][3:] == ["search", "--run", "demo", "--source", "openalex_rq1",
                                       "--max-records", "2000", "--count-only"]
    for step in ("journals", "reparse"):
        assert client.post("/api/v2/runs/demo/run", json={"step": step}).status_code == 200
        _wait_for_job()
        assert client.commands[-1][3:] == [step, "--run", "demo"]
    bad = client.post("/api/v2/runs/demo/run", json={"step": "search", "source": "x; rm -rf ."})
    assert bad.status_code == 400


def test_protocols_are_listed_and_a_review_can_be_started(client, tmp_path, monkeypatch):
    listed = client.get("/api/v2/protocols").json()
    assert {"protocol_isabel_chapter_v1.yaml", "protocol_isabel_chapter_v2.yaml"} <= {p["file"] for p in listed}
    assert all(p.get("status") == "approved" for p in listed if p["file"].startswith("protocol_isabel"))

    ok = client.post("/api/v2/runs", json={"protocol": "protocol_isabel_chapter_v2.yaml", "label": "Mi revisión",
                                           "run_id": "nueva_1"})
    assert ok.status_code == 200 and ok.json()["run_id"] == "nueva_1"
    assert client.commands[-1][3:5] == ["init", "--protocol"] and client.commands[-1][-2:] == ["--run-id", "nueva_1"]

    for body in ({"protocol": "../.env", "label": "x", "run_id": "a"},
                 {"protocol": "protocol_isabel_chapter_v2.yaml", "label": "x", "run_id": "../a"},
                 {"protocol": "protocol_isabel_chapter_v2.yaml", "label": "x" * 200, "run_id": "a"},
                 {"protocol": "protocol_isabel_chapter_v2.yaml", "label": "x", "run_id": "demo"}):
        assert client.post("/api/v2/runs", json=body).status_code in (400, 409)
    assert len([c for c in client.commands if "init" in c]) == 1


def test_assistant_endpoints_from_questions_to_an_approved_protocol(client, tmp_path, monkeypatch):
    from palet import drafting
    from palet.protocol import load_protocol
    import tests.test_drafting as sample

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(webflow, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(drafting, "analyse_questions",
                        lambda context, questions, model=None: drafting.QuestionAnalysis.model_validate(sample.ANALYSIS))
    seen_models = []
    clean = json.loads(json.dumps(sample.DRAFT))
    for search in clean["searches"]:
        search["blocks"] = {name: drafting._clean_terms(terms) for name, terms in search["blocks"].items()}
    monkeypatch.setattr(drafting, "draft_protocol",
                        lambda context, questions, model=None: (seen_models.append(model), drafting.ProtocolDraft.model_validate(clean))[1])

    short = client.post("/api/v2/assistant/questions", json={"context": "too short", "questions": sample.QUESTIONS})
    assert short.status_code == 400
    none = client.post("/api/v2/assistant/questions", json={"context": sample.CONTEXT, "questions": []})
    assert none.status_code == 400

    advice = client.post("/api/v2/assistant/questions",
                         json={"context": sample.CONTEXT, "questions": ["1. " + q for q in sample.QUESTIONS]})
    assert advice.status_code == 200
    assert advice.json()["questions"] == sample.QUESTIONS and len(advice.json()["analysis"]["questions"]) == 2

    final = [sample.QUESTIONS[0], sample.ANALYSIS["questions"][1]["suggested"]]
    body = {"context": sample.CONTEXT, "questions": final, "originals": sample.QUESTIONS, "name": "Tabaco escolar",
            "model": "claude-sonnet-5-5"}
    assert client.post("/api/v2/assistant/protocol", json={**body, "model": "not-a-model"}).status_code == 400
    made = client.post("/api/v2/assistant/protocol", json=body)
    assert seen_models == ["claude-sonnet-5-5"]
    assert made.status_code == 200 and made.json()["file"] == "tabaco_escolar.yaml"
    assert made.json()["searches"][0]["rq"] == "RQ1" and " AND " in made.json()["searches"][0]["query"]
    protocol = load_protocol(config_dir / "tabaco_escolar.yaml")
    assert protocol.status == "draft" and protocol.research_questions_original == {"RQ2": sample.QUESTIONS[1]}
    assert client.post("/api/v2/assistant/protocol", json=body).status_code == 409           # never overwrites

    approve = {"file": "tabaco_escolar.yaml", "by": "Ana Pérez"}
    assert client.post("/api/v2/protocols/approve", json=approve).status_code == 400          # not confirmed
    assert client.post("/api/v2/protocols/approve", json={**approve, "file": "../x.yaml", "confirm": True}).status_code == 400
    assert load_protocol(config_dir / "tabaco_escolar.yaml").status == "draft"
    assert client.post("/api/v2/protocols/approve", json={**approve, "confirm": True}).status_code == 200
    assert load_protocol(config_dir / "tabaco_escolar.yaml").status == "approved"
    assert client.post("/api/v2/protocols/approve", json={**approve, "confirm": True}).status_code == 400   # already approved


def test_assistant_reports_model_failures_without_details(client, monkeypatch):
    from palet import drafting
    import tests.test_drafting as sample

    def boom(context, questions, model=None):
        raise RuntimeError("secret request body")

    monkeypatch.setattr(drafting, "analyse_questions", boom)
    failed = client.post("/api/v2/assistant/questions", json={"context": sample.CONTEXT, "questions": sample.QUESTIONS})
    assert failed.status_code == 502 and "secret" not in failed.json()["error"]
    assert webflow._assistant["busy"] is False


def test_approving_a_search_needs_who_and_confirmation(client):
    url = "/api/v2/runs/demo/approve-search"
    assert client.post(url, json={"source": "openalex_rq1", "by": "RMV"}).status_code == 400
    assert client.post(url, json={"source": "bad id!", "by": "RMV", "confirm": True}).status_code == 400
    assert client.post(url, json={"source": "openalex_rq1", "by": "", "confirm": True}).status_code == 400
    assert client.commands == []


def test_models_can_be_chosen_for_charting(client):
    catalogue = client.get("/api/v2/screeners").json()
    assert catalogue["assistant_default"] == "claude-opus-5-5" and catalogue["assignment_default"] == "claude-opus-5-5"
    assert client.post("/api/v2/runs/demo/run", json={"step": "assign", "model": "nope", "replay": True}).status_code == 400
    sonnet = {"step": "assign", "model": "claude-sonnet-5-5"}
    assert client.post("/api/v2/runs/demo/estimate", json={"step": "assign"}).status_code == 200
    # The estimate was for the default model: a different model needs its own estimate.
    assert client.post("/api/v2/runs/demo/run", json={**sonnet, "confirm_cost": True}).status_code == 400
    assert client.post("/api/v2/runs/demo/estimate", json=sonnet).status_code == 200
    assert client.commands[-1][-3:] == ["--model", "claude-sonnet-5-5", "--estimate"]
    assert client.post("/api/v2/runs/demo/run", json={**sonnet, "confirm_cost": True}).status_code == 200
    _wait_for_job()
    assert client.commands[-1][-2:] == ["--model", "claude-sonnet-5-5"]
