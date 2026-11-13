"""Journal lists as an eligibility filter, and the agreement_or_exclude decision rule."""

import openpyxl
import pytest

from palet import journals
from palet.journals import load_journal_lists, normalize_issn, normalize_journal_title, split_issns
from palet.models import Record
from palet.protocol import load_protocol
from palet.runs import ROOT
from palet.screening import ScreeningDecision, combine, metadata_decision

V1 = load_protocol(ROOT / "config" / "protocol_isabel_chapter_v1.yaml")


@pytest.fixture
def index(tmp_path):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Journal title", "ISSN", "eISSN", "Publisher name"])
    sheet.append(["REGIONAL STUDIES", "0034-3404", "1360-0591", "X"])
    sheet.append(["ENERGY POLICY", "0301-4215", None, "Y"])
    sheet.append(["JOURNAL OF ECONOMIC GEOGRAPHY & POLICY", None, "1468-270X", "Z"])
    workbook.save(tmp_path / "list.xlsx")
    return load_journal_lists([{"id": "test", "file": "list.xlsx"}], tmp_path)


def record(**fields):
    defaults = dict(title="A study of jobs in Spain", authors=["Smith J."], year=2020, abstract="An abstract.",
                    doc_type="article", language="en")
    return Record.build(**{**defaults, **fields})


def test_issn_normalisation():
    assert normalize_issn("0034-3404") == "00343404" and normalize_issn("1468-270x") == "1468270X"
    assert normalize_issn("") is None and normalize_issn("12345") is None and normalize_issn(None) is None
    assert split_issns("00343404; 1360-0591") == ["00343404", "13600591"]
    assert split_issns("") == []


def test_title_normalisation():
    assert normalize_journal_title("The Journal of Économie & Policy") == "journal of economie and policy"


def test_list_is_read(index):
    assert index.files == [{"id": "test", "file": "list.xlsx", "journals": 3}]
    assert index.issns == {"00343404", "13600591", "03014215", "1468270X"}


@pytest.mark.parametrize("fields,expected", [
    (dict(issn=["13600591"], source_title="Whatever"), (True, "issn")),
    (dict(issn=["99999999", "0301-4215"]), (True, "issn")),
    (dict(source_title="Regional Studies"), (True, "title")),
    (dict(source_title="Journal of Economic Geography and Policy"), (True, "title")),
    (dict(issn=["99999999"], source_title="Energy Policy"), (True, "title")),
    (dict(issn=["99999999"], source_title="Unknown Journal"), (False, "issn not in the lists")),
    (dict(source_title="Unknown Journal"), (False, "journal title not in the lists (record has no ISSN)")),
    (dict(), (False, "record has no journal data")),
])
def test_check(index, fields, expected):
    assert index.check(record(**fields)) == expected


def test_a_list_without_the_expected_columns_is_rejected(tmp_path):
    workbook = openpyxl.Workbook()
    workbook.active.append(["Title", "Code"])
    workbook.save(tmp_path / "bad.xlsx")
    with pytest.raises(Exception, match="missing columns"):
        load_journal_lists([{"id": "bad", "file": "bad.xlsx"}], tmp_path)
    with pytest.raises(Exception, match="not found"):
        load_journal_lists([{"id": "none", "file": "none.xlsx"}], tmp_path)


def test_metadata_decision_applies_the_journal_filter(index, monkeypatch):
    protocol = V1.model_copy(update={"journal_lists": [{"id": "x", "file": "x"}], "decision_rule": "agreement_or_exclude"})
    monkeypatch.setattr(journals, "index_for", lambda protocol, root: index)
    inside = metadata_decision(protocol, record(issn=["00343404"]))
    assert inside is None                                            # goes on to the model
    outside = metadata_decision(protocol, record(issn=["99999999"], source_title="Obscure Review"))
    assert (outside.decision, outside.reason_code) == ("exclude", "NOT_IN_JOURNAL_LIST")
    assert "Obscure Review" in outside.notes
    # Under this rule a record without abstract is excluded, not sent to a person.
    no_abstract = metadata_decision(protocol, record(issn=["00343404"], abstract=None))
    assert (no_abstract.decision, no_abstract.reason_code) == ("exclude", "NO_ABSTRACT")


def test_version_1_of_the_protocol_has_no_journal_filter():
    assert metadata_decision(V1, record()) is None
    assert metadata_decision(V1, record(abstract=None)).decision == "unclear"


def _pair(a, b, reason_a=None, reason_b=None):
    return [ScreeningDecision(record_id="r", screener="A:m1", decision=a, reason_code=reason_a,
                              failed_reasons=[reason_a] if reason_a else []),
            ScreeningDecision(record_id="r", screener="B:m2", decision=b, reason_code=reason_b,
                              failed_reasons=[reason_b] if reason_b else [])]


@pytest.mark.parametrize("a,b,decision,reason,decided_by", [
    ("include", "include", "include", None, "agreement"),
    ("include", "unclear", "pending", None, "pending"),
    ("unclear", "include", "pending", None, "pending"),
    ("unclear", "unclear", "exclude", "NO_AGREEMENT", "no_agreement"),
    ("exclude", "unclear", "exclude", "NO_AGREEMENT", "no_agreement"),
    ("include", "exclude", "exclude", "NO_AGREEMENT", "no_agreement"),
    ("exclude", "exclude", "exclude", "WRONG_CONCEPT", "agreement"),
    ("error", "include", "pending", None, "pending"),          # a failed call never excludes a record
])
def test_agreement_or_exclude_rule(a, b, decision, reason, decided_by):
    reasons = {"exclude": "WRONG_CONCEPT"}
    final = combine("r", _pair(a, b, reasons.get(a), reasons.get(b)), "agreement_or_exclude")
    assert (final.decision, final.reason_code, final.decided_by) == (decision, reason, decided_by)
    if decision == "pending" and "error" not in (a, b):
        assert final.pending_reason == "one screener includes, the other is unsure"


def test_default_rule_still_sends_every_doubt_to_a_person():
    for a, b in [("unclear", "unclear"), ("exclude", "unclear"), ("include", "exclude"), ("include", "unclear")]:
        assert combine("r", _pair(a, b, "WRONG_CONCEPT" if a == "exclude" else None)).decision == "pending"


def test_version_2_of_the_chapter_protocol():
    v2 = load_protocol(ROOT / "config" / "protocol_isabel_chapter_v2.yaml")
    assert v2.version == 2 and v2.decision_rule == "agreement_or_exclude"
    assert [j.id for j in v2.journal_lists] == ["wos_scie_2026", "wos_ssci_2026"]
    # Questions and the criteria judged by the model are those of version 1: cached replies stay valid.
    from palet.screening import build_system_prompt
    assert build_system_prompt(v2) == build_system_prompt(V1)
    assert v2.research_questions == V1.research_questions
    new = [s for s in v2.sources if s.id not in {x.id for x in V1.sources}]
    assert {s.id for s in new} == {f"openalex_supplementary_{x}" for x in ("rq1", "rq1_b", "rq2", "rq2_b", "rq3", "rq6", "rq7")}
    assert all(s.model_extra["status"] == "proposed" and s.model_extra["languages"] == ["en"] for s in new)
