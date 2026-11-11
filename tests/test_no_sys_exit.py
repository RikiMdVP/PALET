"""Library code raises exceptions; only command-line entry points may exit."""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

import palet
from palet import llm
from palet.errors import NoResultsError, PaletConfigError, PaletError

ROOT = Path(__file__).resolve().parent.parent
LIBRARY_FILES = sorted((ROOT / "scripts").glob("*.py")) + sorted((ROOT / "palet").glob("*.py")) + [
    ROOT / "prisma_validator.py",
    ROOT / "app.py",
]


def _is_main_guard(node):
    return (
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
    )


def _exit_calls_outside_main(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    library_nodes = [node for node in tree.body if not _is_main_guard(node)]
    lines = []
    for top in library_nodes:
        for node in ast.walk(top):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name in {"exit", "quit", "_exit"}:
                    lines.append(node.lineno)
    return lines


@pytest.mark.parametrize("path", LIBRARY_FILES, ids=lambda p: p.name)
def test_no_exit_call_in_library_code(path):
    assert _exit_calls_outside_main(path) == []


def test_palet_is_the_package_not_the_cli_script():
    assert hasattr(palet, "__path__")
    assert Path(palet.__file__).name == "__init__.py"


def test_modules_import_without_api_key(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "scripts")])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    code = "import arq_module, qsp_module, map_module_v2, synthesis_module, se_module"
    # Run from an empty directory so that no .env file is picked up.
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.fixture
def no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm, "load_dotenv", lambda *args, **kwargs: False)
    llm.reset_client()
    yield
    llm.reset_client()


def test_get_client_without_key_raises_config_error(no_api_key):
    with pytest.raises(PaletConfigError, match="ANTHROPIC_API_KEY"):
        llm.get_client()


def test_first_llm_call_without_key_raises_config_error(no_api_key):
    import arq_module

    with pytest.raises(PaletConfigError):
        arq_module.extract_keywords("a seed prompt", verbose=False)


def test_get_client_is_created_once(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    llm.reset_client()
    try:
        assert llm.get_client() is llm.get_client()
    finally:
        llm.reset_client()


def test_search_without_results_raises(monkeypatch):
    import se_module

    monkeypatch.setattr(se_module, "search_openalex", lambda *args, **kwargs: [])
    with pytest.raises(NoResultsError):
        se_module.execute_se(query="nothing matches this", database="openalex", verbose=False)


def test_missing_input_files_raise(tmp_path):
    import map_module_v2
    import qsp_module
    import se_module

    missing = str(tmp_path / "missing.json")
    with pytest.raises(PaletError):
        map_module_v2.load_research_questions(missing)
    with pytest.raises(PaletError):
        map_module_v2.load_papers(str(tmp_path / "missing.csv"))
    with pytest.raises(PaletError):
        qsp_module.load_arq_output(missing)
    with pytest.raises(PaletError):
        se_module.load_qsp_output(missing)


def test_compile_pdf_without_pdflatex_raises(monkeypatch, tmp_path):
    import report_generator_v2

    def missing_binary(*args, **kwargs):
        raise FileNotFoundError("pdflatex")

    monkeypatch.setattr(report_generator_v2.subprocess, "run", missing_binary)
    with pytest.raises(PaletError, match="pdflatex"):
        report_generator_v2.compile_pdf(str(tmp_path / "report.tex"))


@pytest.mark.parametrize(
    "failure",
    [PaletConfigError("ANTHROPIC_API_KEY missing"), SystemExit(1)],
    ids=["exception", "system-exit"],
)
def test_gui_thread_reports_the_failure_and_stops(monkeypatch, tmp_path, failure):
    import app as app_module
    import arq_module

    def boom(*args, **kwargs):
        raise failure

    saved = []
    monkeypatch.setattr(arq_module, "extract_keywords", boom)
    monkeypatch.setattr(app_module, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(app_module, "add_run_to_history", saved.append)
    app_module.pipeline_state.update({"running": True, "error": None, "completed_phases": []})

    app_module.run_pipeline_thread("a seed prompt", {})

    assert app_module.pipeline_state["running"] is False
    assert app_module.pipeline_state["error"]
    assert saved[0]["status"] == "error"


def test_dataframe_helpers_still_work():
    # Guard against accidental breakage while editing module headers.
    import se_module

    df, stats = se_module.remove_duplicates(
        pd.DataFrame({"doi": ["10.1/a", "10.1/A"], "title": ["x", "y"], "database": ["OpenAlex"] * 2}),
        verbose=False,
    )
    assert len(df) == 1 and stats["duplicates_removed"] == 1
