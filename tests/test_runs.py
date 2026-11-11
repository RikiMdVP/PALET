"""Run directories and manifests."""

import json

import pytest

from palet import llm
from palet.errors import PaletError
from palet.models import Record
from palet.protocol import load_protocol
from palet.runs import ROOT, Run, sha256_file

PROTOCOL = ROOT / "config" / "protocol_isabel_chapter_v1.yaml"


@pytest.fixture
def run(tmp_path):
    return Run.create("Chapter re-screening", base_dir=tmp_path, run_id="test_run")


def test_new_run_has_a_complete_manifest(run):
    manifest = run.manifest
    for key in ("run_id", "created_at", "palet_version", "git_commit", "python",
                "settings", "protocol", "prompts", "searches", "steps", "llm_usage"):
        assert key in manifest
    assert manifest["run_id"] == "test_run"
    assert manifest["settings"]["models"]["map"]
    assert manifest["created_at"].endswith("+00:00")            # UTC


def test_run_id_is_derived_from_the_label(tmp_path):
    run = Run.create("Chapter: re-screening!", base_dir=tmp_path)
    assert run.path.name.endswith("_chapter-re-screening")


def test_existing_run_is_never_overwritten(tmp_path, run):
    with pytest.raises(PaletError, match="already exists"):
        Run.create("again", base_dir=tmp_path, run_id="test_run")


def test_open_requires_a_manifest(tmp_path, run):
    assert Run.open(run.path).manifest["run_id"] == "test_run"
    with pytest.raises(PaletError):
        Run.open(tmp_path)


def test_models_round_trip_as_jsonl_byte_for_byte(run):
    records = [Record.build(title="Título A", doi="10.1/a", authors=["Smith J."], year=2020),
               Record.build(title="Title B")]
    path = run.write_models("records.jsonl", records)
    assert run.read_models("records.jsonl", Record) == records
    first = path.read_bytes()
    run.write_models("records.jsonl", records)
    assert path.read_bytes() == first                            # deterministic output
    assert "Título" in path.read_text(encoding="utf-8")          # not escaped


def test_missing_artefact_raises(run):
    with pytest.raises(PaletError, match="Missing artefact"):
        run.read_models("nope.jsonl", Record)


def test_manifest_records_protocol_prompts_searches_steps_and_usage(run):
    protocol = load_protocol(PROTOCOL)
    run.record_protocol(PROTOCOL, protocol)
    run.record_prompt("screen_system", "prompt text")
    run.record_search({"query_id": "Q1", "total_hits": 10})
    run.log_step("dedup", input=235, unique=234)
    llm._record_usage("screen", "claude-opus-5-5", 1000, 500, cached=False)
    run.record_llm_usage("screen")

    manifest = json.loads(run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["protocol"]["sha256"] == sha256_file(PROTOCOL)
    assert len(manifest["prompts"]["screen_system"]) == 64
    assert manifest["searches"] == [{"query_id": "Q1", "total_hits": 10}]
    assert manifest["steps"][0]["step"] == "dedup" and manifest["steps"][0]["unique"] == 234
    assert manifest["llm_usage"]["screen"]["screen"]["input_tokens"] == 1000
