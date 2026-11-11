"""Characterisation tests: how search results are parsed today.

They pin down the current behaviour before the search and deduplication
modules are rewritten (WP3, WP4). Known weaknesses are recorded as strict
``xfail`` tests: they start failing loudly the day the weakness is fixed.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

import se_module

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def works():
    return json.loads((FIXTURES / "openalex_works.json").read_text(encoding="utf-8"))["results"]


@pytest.fixture
def parsed(works):
    return se_module.parse_openalex_results(works)


# ── OpenAlex ────────────────────────────────────────────────────────────────

def test_openalex_one_row_per_work_with_the_normalised_columns(parsed):
    assert len(parsed) == 4
    assert list(parsed.columns) == [
        "title", "authors", "year", "doi", "source", "cited_by_count",
        "abstract", "concepts", "open_access", "openalex_id", "url", "database",
    ]
    assert set(parsed["database"]) == {"OpenAlex"}


def test_openalex_complete_record(parsed):
    row = parsed.iloc[0]
    assert row["title"] == "Green jobs & regional labour markets in the EU"
    assert row["authors"] == "Ana Example; Bruno Sample"
    assert row["year"] == 2021
    assert row["doi"] == "10.1234/EXAMPLE.2021.001"          # resolver prefix removed
    assert row["source"] == "Journal of Regional Examples"
    assert row["cited_by_count"] == 42
    assert row["open_access"] is True or row["open_access"] == True  # noqa: E712
    assert row["openalex_id"] == "https://openalex.org/W1000000001"
    assert row["url"] == "https://doi.org/10.1234/EXAMPLE.2021.001"


def test_openalex_abstract_is_rebuilt_from_the_inverted_index(parsed):
    assert parsed.iloc[0]["abstract"] == "Green jobs create new regional jobs"


def test_openalex_only_the_first_five_concepts_are_kept(parsed):
    assert parsed.iloc[0]["concepts"] == (
        "Employment; Green economy; Economics; European union; Labour economics"
    )


def test_openalex_record_with_missing_fields(parsed):
    row = parsed.iloc[1]
    assert row["authors"] == "Unknown"
    assert row["doi"] is None
    assert row["source"] is None
    assert row["abstract"] is None
    assert row["concepts"] == ""
    assert row["url"] == "https://openalex.org/W1000000002"   # falls back to the OpenAlex ID


def test_openalex_tolerates_null_nested_objects(parsed):
    row = parsed.iloc[2]
    assert row["authors"] == "Carla Specimen"      # authorship without author is skipped
    assert row["source"] is None
    assert row["abstract"] is None                 # empty inverted index
    assert row["concepts"] == "Coal"


def test_openalex_null_title_and_year_are_kept_as_missing(parsed):
    row = parsed.iloc[3]
    assert row["title"] is None
    assert pd.isna(row["year"])
    assert row["abstract"] == "Only abstract"


# ── PubMed ──────────────────────────────────────────────────────────────────

PUBMED_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <Article>
        <Journal><Title>Example Health Journal</Title>
          <JournalIssue><PubDate><Year>2022</Year></PubDate></JournalIssue>
        </Journal>
        <ArticleTitle>Occupational health in the energy transition</ArticleTitle>
        <Abstract><AbstractText>Workers face new risks.</AbstractText></Abstract>
        <AuthorList>
          <Author><LastName>Example</LastName><ForeName>Ana</ForeName></Author>
        </AuthorList>
      </Article>
      <MeshHeadingList>
        <MeshHeading><DescriptorName>Occupational Health</DescriptorName></MeshHeading>
      </MeshHeadingList>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">12345678</ArticleId>
        <ArticleId IdType="doi">10.1234/example.2022.555</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""


def test_pubmed_xml_is_parsed_into_the_same_schema():
    articles = se_module._parse_pubmed_xml(PUBMED_XML)
    assert len(articles) == 1
    article = articles[0]
    assert article["title"] == "Occupational health in the energy transition"
    assert article["year"] == 2022
    assert article["doi"] == "10.1234/example.2022.555"
    assert article["pmid"] == "12345678"
    assert article["source"] == "Example Health Journal"
    assert article["abstract"] == "Workers face new risks."
    assert article["cited_by_count"] is None       # PubMed gives no citation counts
    assert article["database"] == "PubMed"
    assert article["url"] == "https://pubmed.ncbi.nlm.nih.gov/12345678/"


def test_pubmed_invalid_xml_returns_no_articles():
    assert se_module._parse_pubmed_xml("<not-closed>") == []


# ── Deduplication ───────────────────────────────────────────────────────────

def _records(rows):
    return pd.DataFrame(rows, columns=["doi", "title", "database"])


def test_dedup_doi_match_ignores_case_and_spaces():
    df = _records([
        ["10.1234/ABC", "Title one", "OpenAlex"],
        ["10.1234/abc ", "Title one (PubMed spelling)", "PubMed"],
        ["10.1234/xyz", "Another", "OpenAlex"],
    ])
    clean, stats = se_module.remove_duplicates(df, verbose=False)
    assert len(clean) == 2
    assert clean.iloc[0]["title"] == "Title one"   # first occurrence wins
    assert stats == {
        "identified_by_database": {"OpenAlex": 2, "PubMed": 1},
        "total_identified": 3,
        "duplicates_removed": 1,
        "total_after_dedup": 2,
    }


def test_dedup_exact_title_match_among_records_without_doi():
    df = _records([
        [None, "Same title", "OpenAlex"],
        [None, "Same title", "PubMed"],
        [None, "Different title", "PubMed"],
    ])
    clean, stats = se_module.remove_duplicates(df, verbose=False)
    assert len(clean) == 2 and stats["duplicates_removed"] == 1


def test_dedup_does_not_match_a_doi_record_with_a_title_only_record():
    # Current rule: titles are only compared among records that lack a DOI.
    df = _records([
        ["10.1234/abc", "Same title", "OpenAlex"],
        [None, "Same title", "PubMed"],
    ])
    clean, _ = se_module.remove_duplicates(df, verbose=False)
    assert len(clean) == 2


def test_dedup_empty_input():
    clean, stats = se_module.remove_duplicates(pd.DataFrame(), verbose=False)
    assert clean.empty and stats == {}


@pytest.mark.xfail(strict=True, reason="legacy se_module dedup (palet.dedup fixes it): titles are compared literally (case, punctuation)")
def test_dedup_matches_titles_that_differ_only_in_case_and_punctuation():
    df = _records([
        [None, "Green Jobs in Europe: A Review", "OpenAlex"],
        [None, "green jobs in europe - a review", "PubMed"],
    ])
    clean, _ = se_module.remove_duplicates(df, verbose=False)
    assert len(clean) == 1


@pytest.mark.xfail(strict=True, reason="legacy se_module dedup (palet.dedup fixes it): a DOI given as a resolver URL is not normalised")
def test_dedup_matches_doi_written_as_url():
    df = _records([
        ["10.1234/abc", "Title", "OpenAlex"],
        ["https://doi.org/10.1234/abc", "Title", "Scopus"],
    ])
    clean, _ = se_module.remove_duplicates(df, verbose=False)
    assert len(clean) == 1


@pytest.mark.xfail(strict=True, reason="legacy se_module dedup (palet.dedup fixes it): records without DOI and without title collapse into one")
def test_dedup_keeps_distinct_records_that_lack_doi_and_title():
    df = _records([
        [None, None, "OpenAlex"],
        [None, None, "OpenAlex"],
    ])
    clean, _ = se_module.remove_duplicates(df, verbose=False)
    assert len(clean) == 2


@pytest.mark.xfail(strict=True, reason="legacy se_module dedup (palet.dedup fixes it): same study, bilingual title, one record without DOI "
                                       "(Coaquira 2022 / Velásquez 2023 in the chapter corpus)")
def test_dedup_detects_the_same_study_published_under_two_titles():
    df = pd.DataFrame({
        "doi": [None, "10.13043/DYS.94.4"],
        "title": [
            "Efectos de la transición energética sobre el empleo en el Perú",
            "Effects of the energy transition on employment in Peru",
        ],
        "authors": ["Coaquira, A.; Velásquez, B.", "Velásquez, B.; Coaquira, A."],
        "year": [2022, 2023],
        "database": ["Scopus", "Scopus"],
    })
    clean, _ = se_module.remove_duplicates(df, verbose=False)
    assert len(clean) == 1
