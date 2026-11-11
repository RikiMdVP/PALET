"""Data model of PALET 2.0: records and their stable identifiers.

A record is identified by its normalised DOI or, when it has none, by a hash
of its normalised title, first-author surname and year. Positional indices
(row numbers) are never used as identifiers.
"""

import hashlib
import math
import re
import unicodedata
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

RecordStatus = Literal[
    "identified", "duplicate", "ta_included", "ta_excluded",
    "ta_unclear", "ft_excluded", "included", "error",
]

_DOI_PREFIX_RE = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_INITIALS_RE = re.compile(r"^(?:[A-Z]\.?-?){1,4}$")


def _is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and value.strip().lower() in {"", "nan", "none"}


def normalize_doi(doi) -> Optional[str]:
    """Lower-case DOI without resolver prefix or spaces; None if absent."""
    if _is_missing(doi):
        return None
    doi = _DOI_PREFIX_RE.sub("", str(doi).strip())
    doi = re.sub(r"\s+", "", doi).lower()
    return doi or None


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_title(title) -> str:
    """Lower-case title without accents or punctuation, single-spaced."""
    if _is_missing(title):
        return ""
    text = strip_accents(str(title)).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def author_surname(author) -> str:
    """Surname of one author, lower-case and without accents.

    Handles "Surname, Name", "Surname N." (Scopus) and "Name Surname"
    (OpenAlex, PubMed).
    """
    if _is_missing(author):
        return ""
    author = str(author).strip()
    if "," in author:
        surname = author.split(",")[0]
    else:
        tokens = author.split()
        while len(tokens) > 1 and _INITIALS_RE.match(tokens[-1]):
            tokens.pop()                      # drop trailing initials: "Sotarauta M."
        surname = " ".join(tokens) if len(tokens) != len(author.split()) else tokens[-1]
    return normalize_title(surname)


def make_record_id(doi, title, first_author, year) -> str:
    """Stable identifier: normalised DOI, else a 12-character content hash."""
    normalized = normalize_doi(doi)
    if normalized:
        return normalized
    year_text = "" if _is_missing(year) else str(int(float(year)))
    key = "|".join([normalize_title(title), author_surname(first_author), year_text])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


class Record(BaseModel):
    """One bibliographic record, whatever database it came from."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    doi: Optional[str] = None
    title: str
    abstract: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    source_title: Optional[str] = None
    language: Optional[str] = None
    doc_type: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    affiliation_countries: list[str] = Field(default_factory=list)
    cited_by_count: Optional[int] = None
    url: Optional[str] = None
    source_record_id: Optional[str] = None     # ID in the source database (Scopus EID, OpenAlex ID)
    found_by_queries: list[str] = Field(default_factory=list)
    merged_from: list[str] = Field(default_factory=list)
    status: RecordStatus = "identified"

    @classmethod
    def build(cls, *, title, doi=None, authors=None, year=None, **fields) -> "Record":
        """Create a record computing its DOI normalisation and record_id."""
        authors = [a for a in (authors or []) if not _is_missing(a)]
        year_value = None if _is_missing(year) else int(float(year))
        clean_title = "" if _is_missing(title) else str(title).strip()
        return cls(
            record_id=make_record_id(doi, clean_title, authors[0] if authors else None, year_value),
            doi=normalize_doi(doi),
            title=clean_title,
            authors=authors,
            year=year_value,
            **fields,
        )
