"""Deduplication v2 (WP4)."""

from pathlib import Path

import pytest

from palet.dedup import deduplicate, title_similarity, title_variants
from palet.importers import import_scopus_csv
from palet.models import Record

CHAPTER_EXPORT = (Path(__file__).resolve().parent.parent
                  / "data" / "raw" / "isabel_chapter_2025" / "Final_Fernando_3.1.csv")


def rec(title, authors=("Smith J.",), year=2020, doi=None, **fields):
    return Record.build(title=title, authors=list(authors), year=year, doi=doi, **fields)


# The duplicate found in the chapter corpus: same study, bilingual title,
# one record without DOI, authors written differently, years 2022 and 2023.
PERU_EN = rec("Regional Comparative Evaluation: Synthetic Regional Development Index (RDI) for Peru",
              authors=["Coaquira M.", "Tudela J.", "Jiménez M."], year=2022)
PERU_ES = rec("Regional comparative evaluation: Synthetic regional development index (RDI) for Peru; "
              "[Evaluación comparativa regional: índice sintético de desarrollo regional (IDR) para Perú]",
              authors=["Velásquez M.A.C.", "Tudela Mamani J.W.", "Carrión M.J."], year=2023,
              doi="10.13043/dys.94.4", abstract="An abstract.")


def test_same_doi_is_merged_whatever_its_spelling():
    result = deduplicate([rec("Title one", doi="10.1/ABC"), rec("Title one again", doi="https://doi.org/10.1/abc")])
    assert len(result.records) == 1 and len(result.duplicates) == 1
    assert result.merges[0]["rule"] == "same_id"


def test_bilingual_duplicate_of_the_chapter_is_merged():
    result = deduplicate([PERU_EN, PERU_ES])
    assert len(result.records) == 1
    kept = result.records[0]
    assert kept.doi == "10.13043/dys.94.4"                 # the record with DOI survives
    assert kept.merged_from == [PERU_EN.record_id]
    assert result.duplicates[0].status == "duplicate"
    assert result.merges[0]["rule"] == "title_author_year"


def test_merge_does_not_depend_on_input_order():
    assert deduplicate([PERU_ES, PERU_EN]).records[0].doi == "10.13043/dys.94.4"


def test_titles_differing_in_case_and_punctuation_are_merged():
    result = deduplicate([rec("Green Jobs in Europe: A Review"), rec("green jobs in europe - a review")])
    assert len(result.records) == 1


def test_same_title_by_other_authors_is_not_merged_but_flagged():
    # Plausible false positive 1: generic title, unrelated authors.
    result = deduplicate([rec("Smart specialisation in European regions", authors=["Smith J."]),
                          rec("Smart specialisation in European regions", authors=["Kowalski P."])])
    assert len(result.records) == 2
    assert "no shared author surname" in result.doubtful[0].reason


def test_two_parts_of_a_series_are_not_merged_but_flagged():
    # Plausible false positive 2: same authors and year, consecutive parts.
    result = deduplicate([rec("The geography of the green transition in Europe: Part I"),
                          rec("The geography of the green transition in Europe: Part II")])
    assert len(result.records) == 2
    assert "number or part marker" in result.doubtful[0].reason


def test_short_title_contained_in_a_longer_one_is_not_merged():
    result = deduplicate([rec("Green jobs and regional policy"),
                          rec("Green jobs and regional policy in the coal regions of Poland after 2015")])
    assert len(result.records) == 2


def test_same_title_years_apart_is_not_merged():
    result = deduplicate([rec("Regional employment outlook", year=2015), rec("Regional employment outlook", year=2021)])
    assert len(result.records) == 2 and "years differ" in result.doubtful[0].reason


def test_different_dois_are_never_merged_automatically():
    result = deduplicate([rec("Green jobs in Europe: a review", doi="10.1/preprint"),
                          rec("Green jobs in Europe: a review", doi="10.1/article")])
    assert len(result.records) == 2 and "different DOIs" in result.doubtful[0].reason


def test_merge_keeps_provenance_and_fills_missing_fields():
    a = rec("Green jobs in Europe: a review", found_by_queries=["Q_scopus"])
    b = rec("Green jobs in Europe: a review", doi="10.1/x", abstract="Text.", found_by_queries=["Q_openalex"])
    kept = deduplicate([a, b]).records[0]
    assert kept.doi == "10.1/x" and kept.abstract == "Text."
    assert set(kept.found_by_queries) == {"Q_scopus", "Q_openalex"}


def test_stats_add_up():
    result = deduplicate([PERU_EN, PERU_ES, rec("Something else entirely about ports")])
    assert result.stats == {"input": 3, "unique": 2, "duplicates_removed": 1,
                            "merged_by_rule": {"title_author_year": 1}, "doubtful_pairs": 0}


def test_title_variants_split_bilingual_titles():
    variants = title_variants(PERU_ES.title)
    assert "regional comparative evaluation synthetic regional development index rdi for peru" in variants
    assert title_similarity(PERU_EN.title, PERU_ES.title) == 1.0


@pytest.mark.skipif(not CHAPTER_EXPORT.is_file(), reason="chapter corpus is not versioned")
def test_chapter_corpus_has_exactly_the_one_known_duplicate():
    records = import_scopus_csv(CHAPTER_EXPORT, query_id="scopus_2025_export")
    result = deduplicate(records)
    assert result.stats["input"] == 235 and result.stats["unique"] == 234
    assert result.duplicates[0].title.startswith("Regional Comparative Evaluation")
