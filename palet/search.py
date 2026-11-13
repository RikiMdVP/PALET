"""Documented database searches (WP3, first part): OpenAlex on title and abstract.

A search is defined in the protocol as concept blocks. Terms inside a block
are joined with OR and blocks with AND. Every execution records the exact
query, its filters, the date and the total number of hits, so that
"records identified" can be reported truthfully.
"""

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from palet import config
from palet.errors import PaletConfigError, SearchError
from palet.journals import normalize_issn
from palet.models import Record

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
_FORBIDDEN_IN_TERMS = (",", "|", '"', "(", ")")


def build_query(blocks: dict[str, list[str]]) -> str:
    """Boolean query from concept blocks: (a OR "b c") AND (d OR e)."""
    if not blocks:
        raise PaletConfigError("A search needs at least one concept block")
    groups = []
    for name, terms in blocks.items():
        if not terms:
            raise PaletConfigError(f"Concept block '{name}' is empty")
        formatted = []
        for term in terms:
            term = str(term).strip()
            if not term or any(char in term for char in _FORBIDDEN_IN_TERMS):
                raise PaletConfigError(
                    f"Invalid search term in block '{name}': {term!r} "
                    f"(terms may not be empty or contain any of {' '.join(_FORBIDDEN_IN_TERMS)})"
                )
            formatted.append(f'"{term}"' if " " in term or "-" in term else term)
        groups.append("(" + " OR ".join(formatted) + ")")
    return " AND ".join(groups)


def openalex_filter(query: str, year_from=None, year_to=None, document_types=None, languages=None) -> str:
    parts = [f"title_and_abstract.search:{query}"]
    if year_from:
        parts.append(f"from_publication_date:{year_from}-01-01")
    if year_to:
        parts.append(f"to_publication_date:{year_to}-12-31")
    if document_types:
        parts.append("type:" + "|".join(document_types))
    if languages:
        parts.append("language:" + "|".join(languages))
    return ",".join(parts)


def _describe(error: Exception) -> str:
    """Describe a failed request without its URL (which carries the API key)."""
    response = getattr(error, "response", None)
    if response is not None:
        detail = (getattr(response, "text", "") or "").strip().replace("\n", " ")[:300]
        return f"HTTP {response.status_code}" + (f" — {detail}" if detail else "")
    return type(error).__name__


def _api_key() -> str:
    load_dotenv(dotenv_path=_ENV_FILE)
    key = os.getenv("OPENALEX_API_KEY")
    if not key:
        raise PaletConfigError("OPENALEX_API_KEY is not set in .env (required by OpenAlex since 2026)")
    return key


def search_openalex(query_id: str, query: str, *, year_from=None, year_to=None, document_types=None,
                    languages=None, max_records: int = 500, count_only: bool = False,
                    allow_truncation: bool = False) -> tuple[list[dict], dict]:
    """Run a title-and-abstract search. Returns (works, execution record).

    With ``count_only`` nothing is downloaded. If the search has more hits
    than ``max_records`` it stops with an error unless truncation is
    explicitly allowed; a truncated search is recorded as such.
    """
    filter_value = openalex_filter(query, year_from, year_to, document_types, languages)
    per_page = config.get_search_setting("openalex_per_page")
    params = {"filter": filter_value, "per_page": 1 if count_only else per_page, "api_key": _api_key()}
    executed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def get(extra):
        try:
            response = requests.get(OPENALEX_WORKS_URL, params={**params, **extra}, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise SearchError(f"OpenAlex search '{query_id}' failed: {_describe(e)}") from None

    first = get({"cursor": "*"})
    total_hits = int(first.get("meta", {}).get("count", 0))

    execution = {
        "query_id": query_id,
        "source": "openalex",
        "platform": "OpenAlex API, filter title_and_abstract.search",
        "query_string": query,
        "filters": {"year_from": year_from, "year_to": year_to,
                    "document_types": document_types, "languages": languages},
        "executed_at": executed_at,
        "total_hits": total_hits,
        "downloaded": 0,
        "truncated": False,
    }
    if count_only:
        return [], execution

    if total_hits > max_records and not allow_truncation:
        raise SearchError(
            f"Search '{query_id}' has {total_hits} hits, more than the limit of {max_records}. "
            "Narrow the query, raise --max-records, or pass --allow-truncation "
            "(the truncation will be recorded and must be reported)."
        )

    works, page = [], first
    while True:
        results = page.get("results", [])
        works.extend(results)
        cursor = page.get("meta", {}).get("next_cursor")
        if not results or not cursor or len(works) >= min(total_hits, max_records):
            break
        time.sleep(0.1)
        page = get({"cursor": cursor})

    works = works[:max_records]
    execution["downloaded"] = len(works)
    execution["truncated"] = len(works) < total_hits
    return works, execution


def sample_openalex(query: str, *, year_from=None, year_to=None, document_types=None, languages=None,
                    n: int = 30, seed: int = 1) -> tuple[list[dict], int, str]:
    """Random sample of the works matching a search (fixed seed, reproducible).

    Used to judge a search string before approving it. Nothing is recorded.
    Returns (works, total hits, filter used).
    """
    filter_value = openalex_filter(query, year_from, year_to, document_types, languages)
    params = {"filter": filter_value, "sample": n, "seed": seed, "per_page": min(n, 100),
              "select": "id,doi,title,publication_year,type,language,primary_location",
              "api_key": _api_key()}
    try:
        response = requests.get(OPENALEX_WORKS_URL, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        raise SearchError(f"OpenAlex sample failed: {_describe(e)}") from None
    count_params = {"filter": filter_value, "per_page": 1, "api_key": params["api_key"]}
    try:
        count_response = requests.get(OPENALEX_WORKS_URL, params=count_params, timeout=60)
        count_response.raise_for_status()
        total = int(count_response.json().get("meta", {}).get("count", 0))
    except requests.exceptions.RequestException as e:
        raise SearchError(f"OpenAlex count failed: {_describe(e)}") from None
    return data.get("results", [])[:n], total, filter_value


def _abstract_from_inverted_index(index) -> str | None:
    if not index:
        return None
    try:
        size = max(max(positions) for positions in index.values()) + 1
        words = [""] * size
        for word, positions in index.items():
            for position in positions:
                words[position] = word
        text = " ".join(words).strip()
    except (ValueError, TypeError, AttributeError):
        return None
    return text or None


def openalex_work_to_record(work: dict, query_id: str) -> Record:
    authorships = work.get("authorships") or []
    authors = [a["author"]["display_name"] for a in authorships
               if a.get("author") and a["author"].get("display_name")]
    countries = []
    for authorship in authorships:
        for code in authorship.get("countries") or []:
            if code and code not in countries:
                countries.append(code)
    journal = (work.get("primary_location") or {}).get("source") or {}
    source = journal.get("display_name")
    issns = []
    for value in [journal.get("issn_l"), *(journal.get("issn") or [])]:
        issn = normalize_issn(value)
        if issn and issn not in issns:
            issns.append(issn)
    keywords = [k.get("display_name") for k in (work.get("keywords") or []) if k.get("display_name")]

    return Record.build(
        title=work.get("title") or work.get("display_name"),
        doi=work.get("doi"),
        authors=authors,
        year=work.get("publication_year"),
        abstract=_abstract_from_inverted_index(work.get("abstract_inverted_index")),
        source_title=source,
        issn=issns,
        language=work.get("language"),
        doc_type=work.get("type"),
        keywords=keywords,
        affiliation_countries=countries,
        cited_by_count=work.get("cited_by_count"),
        url=work.get("doi") or work.get("id"),
        source_record_id=work.get("id"),
        found_by_queries=[query_id],
    )
