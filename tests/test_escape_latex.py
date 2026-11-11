"""escape_latex must escape every LaTeX special character exactly once."""

import pytest

from report_generator_v2 import escape_latex

EXPECTED = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\^{}",
    "$": r"\$",
    "#": r"\#",
}


@pytest.mark.parametrize("char,escaped", EXPECTED.items())
def test_single_special_character(char, escaped):
    assert escape_latex(f"a{char}b") == f"a{escaped}b"


def test_all_special_characters_together():
    text = "".join(EXPECTED)
    assert escape_latex(text) == "".join(EXPECTED.values())


def test_escapes_are_not_escaped_again():
    # Regression: the backslash used to be replaced last, which turned
    # "R&D" into "R\textbackslash{}&D" and left a raw "&" in the document.
    assert escape_latex("R&D at 50% (a_b)") == r"R\&D at 50\% (a\_b)"


def test_literal_backslash_followed_by_special():
    assert escape_latex("\\&") == r"\textbackslash{}\&"


def test_plain_and_non_latin_text_untouched():
    assert escape_latex("Regional growth in Asturias") == "Regional growth in Asturias"
    assert escape_latex("Иванов и Петров") == "Иванов и Петров"
    assert escape_latex("Martínez-Güell, Ñ.") == "Martínez-Güell, Ñ."


def test_missing_and_non_string_values():
    assert escape_latex(None) == ""
    assert escape_latex(float("nan")) == ""
    assert escape_latex(2024) == "2024"
