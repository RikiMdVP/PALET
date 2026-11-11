"""Record identifiers must be stable and independent of row order."""

import pytest
from pydantic import ValidationError

from palet.models import Record, author_surname, make_record_id, normalize_doi, normalize_title


@pytest.mark.parametrize("raw,expected", [
    ("10.1080/ABC.2018", "10.1080/abc.2018"),
    ("https://doi.org/10.1080/abc.2018", "10.1080/abc.2018"),
    ("http://dx.doi.org/10.1080/abc.2018", "10.1080/abc.2018"),
    ("doi: 10.1080/abc.2018 ", "10.1080/abc.2018"),
    ("", None), (None, None), (float("nan"), None), ("nan", None),
])
def test_normalize_doi(raw, expected):
    assert normalize_doi(raw) == expected


def test_normalize_title_ignores_case_accents_and_punctuation():
    assert normalize_title("Transición Energética: ¿Empleo?") == "transicion energetica empleo"
    assert normalize_title("Green Jobs in Europe: A Review") == normalize_title("green jobs in europe - a review")
    assert normalize_title(None) == ""


@pytest.mark.parametrize("author,expected", [
    ("Sotarauta M.", "sotarauta"),                 # Scopus
    ("Rodríguez-Pose A.", "rodriguez pose"),
    ("De La Fuente A.B.", "de la fuente"),
    ("Sotarauta, Markku", "sotarauta"),            # Surname, Name
    ("Maria Denisa Vasilescu", "vasilescu"),       # OpenAlex / PubMed
    ("Tibor Tóth", "toth"),
    (None, ""),
])
def test_author_surname(author, expected):
    assert author_surname(author) == expected


def test_record_id_is_the_normalised_doi_when_there_is_one():
    assert make_record_id("https://doi.org/10.1080/ABC", "Any title", "Any A.", 2020) == "10.1080/abc"


def test_record_id_without_doi_is_a_stable_hash_of_title_author_year():
    first = make_record_id(None, "Green Jobs in Europe: A Review", "Smith J.", 2020)
    same = make_record_id("", "green jobs in europe — a review", "Smith, John", "2020.0")
    assert first == same and len(first) == 12
    assert first != make_record_id(None, "Green Jobs in Europe: A Review", "Smith J.", 2021)
    assert first != make_record_id(None, "Green Jobs in Europe: A Review", "Jones K.", 2020)


def test_record_build_fills_id_and_normalises_fields():
    record = Record.build(title="  A title ", doi="HTTPS://DOI.ORG/10.1/X", authors=["Smith J.", None], year="2021")
    assert record.record_id == "10.1/x" and record.doi == "10.1/x"
    assert record.title == "A title" and record.authors == ["Smith J."] and record.year == 2021
    assert record.status == "identified"


def test_record_without_title_authors_or_year_still_gets_an_id():
    record = Record.build(title=None)
    assert record.title == "" and len(record.record_id) == 12


def test_record_rejects_unknown_fields_and_statuses():
    with pytest.raises(ValidationError):
        Record(record_id="x", title="t", paper_id=3)
    with pytest.raises(ValidationError):
        Record(record_id="x", title="t", status="maybe")
