"""The protocol is written by humans; PALET only reads and validates it."""

import copy

import pytest
import yaml

from palet.errors import PaletConfigError
from palet.protocol import load_protocol, require_approved
from palet.runs import ROOT

CHAPTER_PROTOCOL = ROOT / "config" / "protocol_isabel_chapter_v1.yaml"

MINIMAL = {
    "version": 1,
    "title": "A review",
    "research_questions": {"RQ1": "Does X create jobs?"},
    "criteria": [
        {"id": "IC1", "kind": "include", "dimension": "context", "rule": "Focus on EU member states."},
        {"id": "EC1", "kind": "exclude", "dimension": "concept", "rule": "No labour-market dimension."},
    ],
}


def _write(tmp_path, data):
    path = tmp_path / "protocol.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def _load(tmp_path, **changes):
    data = copy.deepcopy(MINIMAL)
    data.update(changes)
    return load_protocol(_write(tmp_path, data))


def test_chapter_protocol_keeps_the_seven_research_questions_verbatim():
    protocol = load_protocol(CHAPTER_PROTOCOL)
    raw = yaml.safe_load(CHAPTER_PROTOCOL.read_text(encoding="utf-8"))
    assert list(protocol.research_questions) == [f"RQ{i}" for i in range(1, 8)]
    assert protocol.research_questions == raw["research_questions"]      # not a word changed
    assert protocol.research_questions_original["RQ3"] != protocol.research_questions["RQ3"]


def test_chapter_protocol_criteria_and_scope():
    protocol = load_protocol(CHAPTER_PROTOCOL)
    assert [c.id for c in protocol.inclusion_criteria] == ["IC1", "IC2", "IC3", "IC4"]
    assert [c.id for c in protocol.exclusion_criteria] == ["EC1", "EC2", "EC3"]
    assert (protocol.year_from, protocol.year_to) == (2013, 2025)
    assert protocol.languages == ["en", "es"] and protocol.assignment_mode == "multi"
    assert protocol.source("scopus_2025_export").type == "manual_import"


def test_minimal_protocol_gets_defaults(tmp_path):
    protocol = _load(tmp_path)
    assert protocol.status == "draft" and protocol.languages == ["en"]


@pytest.mark.parametrize("changes,message", [
    ({"research_questions": {}}, "at least one research question"),
    ({"research_questions": {"Q1": "text"}}, "RQ1, RQ2"),
    ({"research_questions": {"RQ1": "  "}}, "empty"),
    ({"criteria": MINIMAL["criteria"] + [MINIMAL["criteria"][0]]}, "duplicated criterion ids"),
    ({"criteria": [MINIMAL["criteria"][1]]}, "at least one inclusion criterion"),
    ({"year_from": 2025, "year_to": 2013}, "year_from is later"),
    ({"research_questions_original": {"RQ9": "old"}}, "unknown questions"),
    ({"status": "approved"}, "approved_by and approved_at"),
    ({"unexpected_key": 1}, "unexpected_key"),
])
def test_invalid_protocols_are_rejected_with_a_clear_message(tmp_path, changes, message):
    with pytest.raises(PaletConfigError, match=message):
        _load(tmp_path, **changes)


def test_missing_and_malformed_files(tmp_path):
    with pytest.raises(PaletConfigError, match="not found"):
        load_protocol(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: [1\n", encoding="utf-8")
    with pytest.raises(PaletConfigError, match="not valid YAML"):
        load_protocol(bad)


def test_screening_requires_an_approved_protocol(tmp_path):
    with pytest.raises(PaletConfigError, match="still a draft"):
        require_approved(_load(tmp_path))
    require_approved(_load(tmp_path, status="approved", approved_by="RMVP", approved_at="2026-11-11"))
