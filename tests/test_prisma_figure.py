"""The identification box of the PRISMA diagram groups the sources and names no database."""

from palet.report import identification_lines, rq_figure_label, source_limitation


def _counts():
    return {
        "identified": 2419,
        "sources": [
            {"query_id": "scopus_2025", "type": "manual_import", "label": "Scopus (web export, 2025-05)",
             "downloaded": 235, "executed_at": "2025-05-20"},
            {"query_id": "rq1", "type": "openalex", "label": "OpenAlex, search for RQ1",
             "downloaded": 480, "executed_at": "2026-11-13 10:00"},
            {"query_id": "rq2", "type": "openalex", "label": "OpenAlex, search for RQ2",
             "downloaded": 1704, "executed_at": "2026-11-13 10:05"},
        ],
    }


def test_identification_lines_group_sources_without_naming_databases():
    lines = identification_lines(_counts())
    assert lines == ["Records identified (n = 2419)",
                     "Database export, 2025 (n = 235)",
                     "Supplementary searches, 2026 (n = 2184)"]
    assert not any("OpenAlex" in line or "Scopus" in line for line in lines)


def test_identification_lines_with_searches_only():
    counts = _counts()
    counts["sources"] = counts["sources"][1:]
    counts["identified"] = 2184
    assert identification_lines(counts) == ["Records identified (n = 2184)",
                                            "Database searches, 2026 (n = 2184)"]


def test_identification_lines_single_search_is_singular_and_undated_when_unknown():
    counts = {"identified": 7, "sources": [{"query_id": "q", "type": "openalex", "label": "x",
                                            "downloaded": 7, "executed_at": None}]}
    assert identification_lines(counts) == ["Records identified (n = 7)", "Database search (n = 7)"]


def test_source_limitation_mentions_the_export_only_when_there_is_one():
    with_export = source_limitation(_counts())
    assert "export was not archived" in with_export and "Supplementary searches" in with_export
    counts = _counts()
    counts["sources"] = counts["sources"][1:]
    searches_only = source_limitation(counts)
    assert "Scopus" not in searches_only and "export" not in searches_only
    assert searches_only.startswith("- Searches were run in one database (OpenAlex)")


def test_rq_figure_is_labelled_after_the_studies_it_counts():
    assert rq_figure_label("core_only") == "Studies synthesised"
    assert rq_figure_label("all_included").startswith("Included studies")
