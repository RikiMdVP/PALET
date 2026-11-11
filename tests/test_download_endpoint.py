"""/api/download must only serve results, runs and seed prompts."""

from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

import app as app_module


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A fake project tree: allowed folders plus files that must stay private."""
    base = tmp_path / "project"
    (base / "results").mkdir(parents=True)
    (base / "runs" / "run1").mkdir(parents=True)
    (base / "prompts").mkdir()
    (base / "scripts").mkdir()

    (base / "results" / "report.pdf").write_bytes(b"%PDF-fake")
    (base / "runs" / "run1" / "decisions.jsonl").write_text("{}", encoding="utf-8")
    (base / "prompts" / "seed_demo.txt").write_text("seed text", encoding="utf-8")
    (base / "prompts" / "arq_system_v3.txt").write_text("system prompt", encoding="utf-8")
    (base / ".env").write_text("ANTHROPIC_API_KEY=secret", encoding="utf-8")
    (base / "scripts" / "se_module.py").write_text("code", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")

    monkeypatch.setattr(app_module, "BASE_DIR", base)
    monkeypatch.setattr(app_module, "RESULTS_DIR", base / "results")
    monkeypatch.setattr(app_module, "RUNS_DIR", base / "runs")
    monkeypatch.setattr(app_module, "PROMPTS_DIR", base / "prompts")
    return base


@pytest.fixture
def client(sandbox):
    return TestClient(app_module.app)


def _get(client, filename):
    # Encode everything so the HTTP client cannot normalise "../" away.
    return client.get("/api/download/" + quote(str(filename), safe=""))


def test_serves_result_by_absolute_path(client, sandbox):
    # The GUI requests the PDF by the absolute path stored in the run result.
    response = _get(client, sandbox / "results" / "report.pdf")
    assert response.status_code == 200
    assert response.content == b"%PDF-fake"


def test_serves_result_by_relative_path_and_bare_name(client):
    assert _get(client, "results/report.pdf").status_code == 200
    assert _get(client, "report.pdf").status_code == 200


def test_serves_files_under_runs(client):
    assert _get(client, "runs/run1/decisions.jsonl").status_code == 200


def test_serves_seed_prompts_for_the_gui(client):
    # static/js/app.js loads seeds through /api/download/prompts/<file>.
    response = client.get("/api/download/prompts/seed_demo.txt")
    assert response.status_code == 200
    assert response.text == "seed text"


@pytest.mark.parametrize(
    "filename",
    [
        ".env",
        "../.env",
        "results/../.env",
        "results/../../outside.txt",
        "runs/run1/../../.env",
        "scripts/se_module.py",
        "prompts/arq_system_v3.txt",
        "prompts/../.env",
        "/etc/passwd",
    ],
)
def test_rejects_anything_else(client, filename):
    assert _get(client, filename).status_code == 404


def test_rejects_absolute_paths_outside_the_project(client, sandbox):
    assert _get(client, sandbox / ".env").status_code == 404
    assert _get(client, sandbox.parent / "outside.txt").status_code == 404


def test_rejects_symlink_escaping_results(client, sandbox):
    link = sandbox / "results" / "leak.txt"
    try:
        link.symlink_to(sandbox / ".env")
    except OSError:
        pytest.skip("symlinks not supported on this filesystem")
    assert _get(client, "results/leak.txt").status_code == 404


def test_missing_file_and_directory_return_404(client):
    assert _get(client, "results/nope.pdf").status_code == 404
    assert _get(client, "results").status_code == 404
