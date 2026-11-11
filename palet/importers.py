"""Importers that turn database exports into PALET records."""

from pathlib import Path

import pandas as pd

from palet.errors import PaletError
from palet.models import Record, _is_missing

SCOPUS_REQUIRED_COLUMNS = ("Title", "Authors", "Year", "DOI", "Abstract")
_LANGUAGE_CODES = {"english": "en", "spanish": "es", "french": "fr", "german": "de",
                   "italian": "it", "portuguese": "pt"}
_NO_ABSTRACT_MARKERS = {"[no abstract available]", "no abstract available"}


def _text(value):
    return None if _is_missing(value) else str(value).strip()


def _split(value, separator=";"):
    if _is_missing(value):
        return []
    return [part.strip() for part in str(value).split(separator) if part.strip()]


def _countries(affiliations) -> list[str]:
    """Country of each affiliation (last comma-separated element), deduplicated."""
    countries = []
    for affiliation in _split(affiliations):
        country = affiliation.split(",")[-1].strip()
        if country and country not in countries:
            countries.append(country)
    return countries


def import_scopus_csv(path, query_id: str) -> list[Record]:
    """Read a CSV exported from the Scopus web interface.

    ``query_id`` names the search (or manual import) these records come from
    and is stored in ``found_by_queries``. The input file is only read.
    """
    path = Path(path)
    if not path.is_file():
        raise PaletError(f"Scopus export not found: {path}")

    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    missing = [column for column in SCOPUS_REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise PaletError(f"Not a Scopus export ({path.name}): missing columns {missing}")

    records = []
    for _, row in df.iterrows():
        abstract = _text(row.get("Abstract"))
        if abstract and abstract.lower() in _NO_ABSTRACT_MARKERS:
            abstract = None
        language = _text(row.get("Language of Original Document"))
        doc_type = _text(row.get("Document Type"))
        cited_by = _text(row.get("Cited by"))

        records.append(Record.build(
            title=row.get("Title"),
            doi=row.get("DOI"),
            authors=_split(row.get("Authors")),
            year=row.get("Year"),
            abstract=abstract,
            source_title=_text(row.get("Source title")),
            language=_LANGUAGE_CODES.get(language.lower(), language.lower()) if language else None,
            doc_type=doc_type.lower() if doc_type else None,
            keywords=_split(row.get("Author Keywords")),
            affiliation_countries=_countries(row.get("Affiliations")),
            cited_by_count=int(float(cited_by)) if cited_by else None,
            url=_text(row.get("Link")),
            source_record_id=_text(row.get("EID")),
            found_by_queries=[query_id],
        ))
    return records
