"""Supplementary searches: query building, OpenAlex paging and provenance."""

import pytest
import requests

from palet import search
from palet.errors import PaletConfigError, SearchError
from palet.protocol import load_protocol
from palet.runs import ROOT

FAKE_KEY = "fake-openalex-key-123"


def test_query_joins_terms_with_or_and_blocks_with_and():
    query = search.build_query({"a": ["reskilling", "lifelong learning"], "b": ["Europe", "EU"]})
    assert query == '(reskilling OR "lifelong learning") AND (Europe OR EU)'


@pytest.mark.parametrize("blocks", [{}, {"a": []}, {"a": ["ok", "bad, term"]}, {"a": ["a|b"]}, {"a": [" "]}])
def test_invalid_blocks_are_rejected(blocks):
    with pytest.raises(PaletConfigError):
        search.build_query(blocks)


def test_filter_restricts_to_title_and_abstract_with_protocol_limits():
    value = search.openalex_filter("(a OR b)", 2013, 2025, ["article", "review"], ["en", "es"])
    assert value == ("title_and_abstract.search:(a OR b),from_publication_date:2013-01-01,"
                     "to_publication_date:2025-12-31,type:article|review,language:en|es")


def test_chapter_protocol_searches_build_and_cover_the_32_countries():
    protocol = load_protocol(ROOT / "config" / "protocol_isabel_chapter_v1.yaml")
    for source_id in ("openalex_supplementary_rq4", "openalex_supplementary_rq5"):
        blocks = protocol.source(source_id).model_extra["blocks"]
        query = search.build_query(blocks)
        assert query.count(") AND (") == 3
        for country in ("Austria", "Sweden", '"United Kingdom"', "Norway", "Switzerland", "Liechtenstein"):
            assert country in query
        assert len(query) < 2500                      # well within OpenAlex's URL limit


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self._payload, self.status_code, self.text = payload or {}, status_code, text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"error for url ...api_key={FAKE_KEY}", response=self)


@pytest.fixture
def openalex(monkeypatch):
    """Fake API holding 250 works, served by cursor in pages."""
    monkeypatch.setenv("OPENALEX_API_KEY", FAKE_KEY)
    monkeypatch.setattr(search.time, "sleep", lambda s: None)
    calls = []
    works = [{"id": f"https://openalex.org/W{i}", "title": f"Work {i}"} for i in range(250)]

    def get(url, params=None, timeout=None):
        calls.append(dict(params))
        start = 0 if params["cursor"] == "*" else int(params["cursor"])
        page = works[start:start + params["per_page"]]
        nxt = start + len(page)
        return FakeResponse({"meta": {"count": len(works), "next_cursor": str(nxt) if nxt < len(works) else None},
                             "results": page})

    monkeypatch.setattr(search.requests, "get", get)
    return calls


def test_count_only_downloads_nothing(openalex):
    works, execution = search.search_openalex("Q", "(a)", count_only=True)
    assert works == [] and execution["total_hits"] == 250 and execution["downloaded"] == 0
    assert len(openalex) == 1 and openalex[0]["per_page"] == 1


def test_full_download_pages_through_all_results_and_records_provenance(openalex):
    works, execution = search.search_openalex("Q_RQ4", "(a)", year_from=2013, year_to=2025,
                                              document_types=["article"], languages=["en"], max_records=500)
    assert len(works) == 250 and len({w["id"] for w in works}) == 250
    assert len(openalex) == 3
    assert openalex[0]["api_key"] == FAKE_KEY and "title_and_abstract.search:(a)" in openalex[0]["filter"]
    assert execution["query_id"] == "Q_RQ4" and execution["query_string"] == "(a)"
    assert execution["total_hits"] == 250 and execution["downloaded"] == 250 and execution["truncated"] is False
    assert execution["executed_at"].endswith("+00:00")
    assert execution["filters"]["year_from"] == 2013


def test_more_hits_than_the_limit_stops_unless_truncation_is_allowed(openalex):
    with pytest.raises(SearchError, match="250 hits"):
        search.search_openalex("Q", "(a)", max_records=100)
    works, execution = search.search_openalex("Q", "(a)", max_records=100, allow_truncation=True)
    assert len(works) == 100 and execution["truncated"] is True and execution["total_hits"] == 250


def test_http_error_raises_without_leaking_the_key(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", FAKE_KEY)
    monkeypatch.setattr(search.requests, "get", lambda *a, **k: FakeResponse(status_code=403, text="Invalid filter"))
    with pytest.raises(SearchError) as excinfo:
        search.search_openalex("Q", "(a)")
    assert "403" in str(excinfo.value) and "Invalid filter" in str(excinfo.value)
    assert FAKE_KEY not in str(excinfo.value)


def test_missing_api_key_is_a_configuration_error(monkeypatch):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.setattr(search, "load_dotenv", lambda **kwargs: False)
    with pytest.raises(PaletConfigError, match="OPENALEX_API_KEY"):
        search.search_openalex("Q", "(a)")


def test_work_becomes_a_record():
    work = {
        "id": "https://openalex.org/W1", "doi": "https://doi.org/10.1234/ABC", "title": "Green skills in Poland",
        "publication_year": 2022, "type": "article", "language": "en", "cited_by_count": 5,
        "authorships": [{"author": {"display_name": "Ana Example"}, "countries": ["PL", "DE"]},
                        {"author": None, "countries": ["PL"]}],
        "primary_location": {"source": {"display_name": "Journal A"}},
        "keywords": [{"display_name": "Green skills"}],
        "abstract_inverted_index": {"Green": [0], "skills": [1], "matter": [2]},
    }
    record = search.openalex_work_to_record(work, "Q_RQ4")
    assert record.record_id == "10.1234/abc" and record.abstract == "Green skills matter"
    assert record.authors == ["Ana Example"] and record.affiliation_countries == ["PL", "DE"]
    assert (record.year, record.language, record.doc_type, record.source_title) == (2022, "en", "article", "Journal A")
    assert record.found_by_queries == ["Q_RQ4"] and record.source_record_id == "https://openalex.org/W1"

    bare = search.openalex_work_to_record({"id": "https://openalex.org/W2", "title": None}, "Q")
    assert bare.title == "" and bare.abstract is None and bare.doi is None


def test_count_only_sends_the_same_filters_as_a_download(openalex):
    limits = dict(year_from=2013, year_to=2025, document_types=["article", "review"], languages=["en", "es"])
    search.search_openalex("Q", "(a)", count_only=True, **limits)
    search.search_openalex("Q", "(a)", max_records=500, **limits)
    count_call, download_call = openalex[0], openalex[1]
    assert count_call["filter"] == download_call["filter"]
    for part in ("from_publication_date:2013-01-01", "to_publication_date:2025-12-31",
                 "type:article|review", "language:en|es", "title_and_abstract.search:(a)"):
        assert part in count_call["filter"]


def test_sample_is_seeded_filtered_and_records_nothing(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", FAKE_KEY)
    calls = []

    def get(url, params=None, timeout=None):
        calls.append(dict(params))
        if "sample" in params:
            return FakeResponse({"results": [{"id": f"W{i}", "title": f"T{i}"} for i in range(params["sample"])]})
        return FakeResponse({"meta": {"count": 321}, "results": []})

    monkeypatch.setattr(search.requests, "get", get)
    works, total, filter_value = search.sample_openalex("(a)", year_from=2013, year_to=2025,
                                                        document_types=["article"], languages=["en"], n=30, seed=42)
    assert len(works) == 30 and total == 321
    assert calls[0]["sample"] == 30 and calls[0]["seed"] == 42
    assert calls[0]["filter"] == calls[1]["filter"] == filter_value
    assert "language:en" in filter_value and "type:article" in filter_value


def test_rq4_variant_d_has_three_blocks_and_no_labour_block():
    protocol = load_protocol(ROOT / "config" / "protocol_isabel_chapter_v1.yaml")
    blocks = protocol.source("openalex_supplementary_rq4_d").model_extra["blocks"]
    assert list(blocks) == ["education", "skills", "geography"]
    assert "skills development" not in blocks["education"]
    assert blocks["skills"] == ["green skills", "digital skills", "green competences", "digital competences",
                                "green jobs", "skills for the green transition", "twin transition"]
    assert blocks["geography"] == protocol.source("openalex_supplementary_rq4").model_extra["blocks"]["geography"]


def test_chapter_supplementary_searches_are_english_only():
    protocol = load_protocol(ROOT / "config" / "protocol_isabel_chapter_v1.yaml")
    openalex_sources = [s for s in protocol.sources if s.type == "openalex"]
    assert len(openalex_sources) == 5
    assert all(s.model_extra["languages"] == ["en"] for s in openalex_sources)
    assert protocol.languages == ["en", "es"]          # eligibility of the Scopus corpus is unchanged
