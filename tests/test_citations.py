"""Citation checker: author–year citations against the reference list."""

from pathlib import Path

import pytest

from palet.citations import (check_citations, extract_citations, format_report, parse_references,
                             read_paragraphs, split_manuscript)
from palet.errors import PaletError

MANUSCRIPT = (Path(__file__).resolve().parent.parent / "data" / "raw" / "isabel_chapter_2025"
              / "manuscript" / "ISABELCHAPTER REV.docx")

REFERENCES = [
    "Benner, M., Trippl, M. and Hassink, R. (2024) ‘Sustainable and inclusive development’, Regional Studies.",
    "Kapetaki, Z. and Alves Dias, P. (2021) Recent trends in EU coal regions. Luxembourg.",
    "Galgóczi, B. (2019) Towards a just transition. Brussels: ETUI.",
    "European Commission (2022) ‘The COVID-19 pandemic’, in Sustainable development in the EU.",
    "Caldecott, B., Sartor, O. and Spencer, T. (2017) Lessons from previous coal transitions.",
    "Caldecott, B., Bouveret, G., Dericks, G. and Liao, X. (2017) Stranded assets.",
    "Webber, D. (2017) European disintegration? London: Palgrave.",
    "McCann, P. (2018) The regional and urban policy of the EU. Edward Elgar.",
    "Cedefop (2021a) The green employment and skills transformation.",
    "Cedefop (2021b) Digital, greener and more resilient.",
    "Crespo Cuaresma, J. and Uljas Lutz, S. (2021) ‘Digital divides’, Empirica.",
    "Frondel, M., Ritter, N. et al. (2010) ‘Economic impacts’, Energy Policy.",
    "Not a reference at all, just a stray paragraph.",
]
BODY = [
    "While Benner et al. (2024) stress inclusion, others disagree (Webber, 2017; European Commission, 2022).",
    "Coal jobs are at risk (Kapetaki et al., 2021), as Galgóczi and Pochet (2019) and Green et al. (1997) noted.",
    "Skills matter (Frondel et al., 2010; Cedefop, 2021a and 2021b; Caldecott et al., 2017).",
    "In July 2022 the Commission published COM(2019) 640; see Table 3 and Figure 2 (2020 data).",
    "For example, Crespo and Uljas (2021) model it econometrically.",
]


@pytest.fixture
def result():
    return check_citations(BODY, REFERENCES)


def test_references_are_parsed():
    references = parse_references(REFERENCES)
    assert len(references) == 12                                  # the stray paragraph is ignored
    benner = references[0]
    assert benner.surnames == ["benner", "trippl", "hassink"] and benner.year == "2024"
    commission = references[3]
    assert commission.is_organisation and commission.surnames == ["european commission"]
    assert references[1].surnames == ["kapetaki", "alves dias"]
    assert references[11].abbreviated


def test_citations_are_extracted_in_both_forms():
    labels = {c.label for c in extract_citations(BODY)}
    assert {"Benner et al. (2024)", "Webber (2017)", "European Commission (2022)", "Kapetaki et al. (2021)",
            "Galgóczi and Pochet (2019)", "Green et al. (1997)", "Cedefop (2021a)", "Cedefop (2021b)"} <= labels


def test_dates_and_document_numbers_are_not_citations():
    labels = {c.label for c in extract_citations(BODY)}
    assert not any("July" in label or "COM" in label or "Figure" in label or "Table" in label for label in labels)


def test_cited_but_not_listed(result):
    assert [item["citation"] for item in result["cited_not_listed"]] == ["Green et al. (1997)"]


def test_listed_but_not_cited(result):
    assert result["listed_not_cited"] == ["McCann, P. (2018)"]


def test_author_mismatches(result):
    problems = {m["citation"]: m["problem"] for m in result["author_mismatches"]}
    assert "et al." in problems["Kapetaki et al. (2021)"] and "2 author" in problems["Kapetaki et al. (2021)"]
    assert "2 author(s) but the reference has 1" in problems["Galgóczi and Pochet (2019)"]
    assert "Benner et al. (2024)" not in problems and "Frondel et al. (2010)" not in problems


def test_same_citation_form_and_year_needs_suffix(result):
    assert len(result["same_authors_and_year"]) == 1
    assert all("Caldecott" in label for label in result["same_authors_and_year"][0])


def test_spelling_variants_are_paired_instead_of_reported_twice(result):
    assert result["probable_spelling_variants"] == [
        {"citation": "Crespo and Uljas (2021)", "reference": "Crespo Cuaresma, J. and Uljas Lutz, S. (2021)"}]


def test_incomplete_references_are_listed(result):
    assert result["incomplete_references"] == ["Frondel, M., Ritter, N. et al. (2010)"]


def test_report_is_readable(result):
    report = format_report(result)
    assert "## Cited in the text but not in the reference list (1)" in report and "Green et al. (1997)" in report


def test_manuscript_is_split_ignoring_a_cover_letter(tmp_path):
    text = "\n".join(["Dear editor, as Smith (2001) said…", "Abstract", "Body citing Webber (2017).",
                      "References", "Webber, D. (2017) European disintegration?"])
    path = tmp_path / "manuscript.txt"
    path.write_text(text, encoding="utf-8")
    body, references = split_manuscript(read_paragraphs(path))
    assert body[0] == "Abstract" and not any("Smith" in p for p in body)
    assert references == ["Webber, D. (2017) European disintegration?"]
    with pytest.raises(PaletError, match="Heading not found"):
        split_manuscript(["no headings here"])


@pytest.mark.skipif(not MANUSCRIPT.is_file(), reason="chapter manuscript is not versioned")
def test_chapter_manuscript_reproduces_the_cases_found_by_the_referee():
    body, references = split_manuscript(read_paragraphs(MANUSCRIPT))
    result = check_citations(body, references)
    missing = {item["citation"] for item in result["cited_not_listed"]}
    assert {"Green et al. (1997)", "Dijkstra et al. (2018)", "Sweeney (2017)"} <= missing
    mismatched = {m["citation"] for m in result["author_mismatches"]}
    assert {"Galgóczi and Pochet (2019)", "Kapetaki et al. (2021)"} <= mismatched
    uncited = " ".join(result["listed_not_cited"])
    for name in ("Betcherman", "Bluedorn", "Broughton", "Bürgisser", "Caliendo", "Cedefop (2019)",
                 "McCann, P. (2018)", "Turnheim", "Vermeulen"):
        assert name in uncited
    assert any("Caldecott" in label for group in result["same_authors_and_year"] for label in group)
