"""BibTeX export: current behaviour and tolerance to missing values."""

import pandas as pd

from export_bibtex import export_to_bibtex


def _export(tmp_path, rows):
    csv_path = tmp_path / "papers.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    bib_path = tmp_path / "references.bib"
    export_to_bibtex(str(csv_path), str(bib_path))
    return bib_path.read_text(encoding="utf-8")


def test_complete_record(tmp_path):
    bib = _export(tmp_path, [{
        "title": "Green {jobs} in Europe", "authors": "Ana Example; Bruno Sample", "year": 2021,
        "doi": "10.1234/abc", "source": "Journal A", "abstract": "An abstract.", "url": "https://doi.org/10.1234/abc",
    }])
    assert "@article{ana_example_2021_0," in bib
    assert "author = {Ana Example and Bruno Sample}" in bib
    assert "title = {Green jobs in Europe}" in bib          # braces removed
    assert "journal = {Journal A}" in bib
    assert "year = {2021}" in bib
    assert "doi = {10.1234/abc}" in bib
    assert "% Total entries: 1" in bib


def test_records_with_missing_values_do_not_break_the_export(tmp_path):
    bib = _export(tmp_path, [
        {"title": "Complete", "authors": "Ana Example", "year": 2021, "doi": "10.1234/abc",
         "source": "Journal A", "abstract": "Text.", "url": "https://x.org"},
        {"title": None, "authors": None, "year": None, "doi": None,
         "source": None, "abstract": None, "url": None},
    ])
    assert "% Total entries: 2" in bib
    assert "{nan}" not in bib                               # missing values are omitted
    assert "title = {Untitled}" in bib
    assert "author = {Unknown}" in bib
    assert "year = {n.d.}" in bib
