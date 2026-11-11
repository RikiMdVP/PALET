"""The report must use the real MAP summary keys for unmatched papers."""

import pandas as pd
import pytest

import map_module_v2
from report_generator_v2 import format_share, generate_latex_report


@pytest.fixture
def papers_df():
    return pd.DataFrame(
        {
            "title": ["Assigned paper", "Offtopic paper", "Abstractless paper"],
            "authors": ["Ana A.", "Bea B.", "Carl C."],
            "year": [2020, 2021, 2022],
            "doi": ["10.1/a", "10.1/b", None],
            "source": ["Journal A", "Journal B", "Journal C"],
            "cited_by_count": [10, 5, 0],
            "abstract": ["Jobs and the green transition.", "Phosphorus losses.", None],
            "concepts": ["Employment; Policy", "Soil; Policy", ""],
            "open_access": [True, False, False],
            "database": ["OpenAlex", "OpenAlex", "OpenAlex"],
        }
    )


@pytest.fixture
def report_tex(tmp_path, papers_df):
    summary = {
        "RQ1": [0],
        "unmatched_not_relevant": [1],
        "unmatched_no_abstract": [2],
    }
    map_results = [
        {"paper_id": 0, "assignments": ["RQ1"], "reasoning": "Relevant.", "confidence": "high"},
        {"paper_id": 1, "assignments": [], "reasoning": "Off topic.", "confidence": "high"},
        {"paper_id": 2, "assignments": ["unmatched_no_abstract"], "reasoning": "", "confidence": "n/a"},
    ]
    output_path = tmp_path / "report_test.tex"
    generate_latex_report(
        summary_data={"timestamp": "20260101_000000", "assignments": summary},
        arq_data={"research_questions": ["Does X create jobs?"], "keywords": ["jobs"]},
        papers_df=papers_df,
        map_results=map_results,
        output_path=str(output_path),
        seed_prompt="seed",
        prisma_diagram=False,
    )
    return output_path.read_text(encoding="utf-8")


def test_overview_table_reports_both_unmatched_categories(report_tex):
    assert r"Not relevant to any RQ & 1 (33.3\%)" in report_tex
    assert r"No abstract available & 1 (33.3\%)" in report_tex
    assert "Unmatched papers &" not in report_tex


def test_unmatched_section_lists_papers_by_reason(report_tex):
    assert r"\section{Unmatched Papers}" in report_tex
    section = report_tex.split(r"\section{Unmatched Papers}")[1].split(r"\section{")[0]
    assert "Offtopic paper" in section
    assert "Abstractless paper" in section
    assert "Assigned paper" not in section
    assert section.index("Not relevant to any research question") < section.index("Offtopic paper")
    assert section.index("No abstract available") < section.index("Abstractless paper")


def test_format_share_handles_empty_corpus():
    assert format_share(0, 0) == r"0 (0.0\%)"
    assert format_share(1, 4) == r"1 (25.0\%)"


def test_map_print_summary_uses_real_keys(capsys):
    summary = {"RQ1": [0], "unmatched_not_relevant": [1, 2], "unmatched_no_abstract": [3]}
    map_module_v2.print_summary(summary, ["Does X create jobs?"])
    out = capsys.readouterr().out
    assert "Unmatched (no relevante): 2 papers" in out
    assert "Unmatched (sin abstract): 1 papers" in out


def test_no_phantom_unmatched_key_left_in_active_code():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    phantom = re.compile(r"""\.get\(\s*['"]unmatched['"]""")
    active = [root / "palet.py", root / "app.py", root / "prisma_validator.py"]
    active += sorted((root / "scripts").glob("*.py"))
    offenders = [p.name for p in active if phantom.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
