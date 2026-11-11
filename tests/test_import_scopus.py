"""Import of Scopus web exports."""

import csv
from pathlib import Path

import pytest

from palet.errors import PaletError
from palet.importers import import_scopus_csv

ROOT = Path(__file__).resolve().parent.parent
CHAPTER_EXPORT = ROOT / "data" / "raw" / "isabel_chapter_2025" / "Final_Fernando_3.1.csv"

COLUMNS = ["Authors", "Title", "Year", "Source title", "Cited by", "DOI", "Link", "Affiliations",
           "Abstract", "Author Keywords", "Language of Original Document", "Document Type", "EID"]


def _write_export(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:   # Scopus writes a BOM
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in COLUMNS})
    return path


@pytest.fixture
def export(tmp_path):
    return _write_export(tmp_path / "scopus.csv", [
        {"Authors": "Sotarauta M.; Beer A.", "Title": "Smart specialization and place leadership",
         "Year": "2018", "Source title": "Regional Studies, Regional Science", "Cited by": "64",
         "DOI": "10.1080/21681376.2018.1480902", "Link": "https://www.scopus.com/x",
         "Affiliations": "University of Tampere, Tampere, Finland; Flinders University, Adelaide, Australia",
         "Abstract": "The concept of smart specialization...", "Author Keywords": "Policy; Place leadership",
         "Language of Original Document": "English", "Document Type": "Article", "EID": "2-s2.0-1"},
        {"Authors": "", "Title": "Why levelling-up is unlikely to solve regional disparities", "Year": "2020",
         "Abstract": "[No abstract available]", "Language of Original Document": "Spanish",
         "Document Type": "Article", "EID": "2-s2.0-2"},
    ])


def test_fields_are_mapped(export):
    record = import_scopus_csv(export, query_id="scopus_test")[0]
    assert record.record_id == "10.1080/21681376.2018.1480902"
    assert record.authors == ["Sotarauta M.", "Beer A."]
    assert record.year == 2018 and record.cited_by_count == 64
    assert record.source_title == "Regional Studies, Regional Science"
    assert record.language == "en" and record.doc_type == "article"
    assert record.keywords == ["Policy", "Place leadership"]
    assert record.affiliation_countries == ["Finland", "Australia"]
    assert record.source_record_id == "2-s2.0-1"
    assert record.found_by_queries == ["scopus_test"]
    assert record.status == "identified"


def test_record_without_authors_doi_or_abstract_is_kept(export):
    record = import_scopus_csv(export, query_id="scopus_test")[1]
    assert record.doi is None and record.authors == [] and record.abstract is None
    assert record.language == "es"
    assert len(record.record_id) == 12


def test_missing_file_and_wrong_format_raise(tmp_path):
    with pytest.raises(PaletError, match="not found"):
        import_scopus_csv(tmp_path / "missing.csv", query_id="q")
    other = tmp_path / "other.csv"
    other.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(PaletError, match="missing columns"):
        import_scopus_csv(other, query_id="q")


@pytest.mark.skipif(not CHAPTER_EXPORT.is_file(), reason="chapter corpus is not versioned")
def test_chapter_export_imports_all_235_records_with_unique_ids():
    before = CHAPTER_EXPORT.stat().st_mtime_ns
    records = import_scopus_csv(CHAPTER_EXPORT, query_id="scopus_2025_export")
    assert len(records) == 235
    assert len({record.record_id for record in records}) == 235
    assert all(record.title for record in records)
    # The record lost in the 2025 spreadsheet is here.
    assert any(record.title.startswith("Why levelling-up is unlikely") for record in records)
    assert CHAPTER_EXPORT.stat().st_mtime_ns == before          # the source file is only read
