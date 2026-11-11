"""PRISMA counts: a paper assigned to several RQs is included only once."""

import pandas as pd

from prisma_validator import build_prisma_data, count_included

DEDUP_STATS = {
    "identified_by_database": {"OpenAlex": 6},
    "total_identified": 6,
    "duplicates_removed": 1,
    "total_after_dedup": 5,
}


def _summary():
    # Paper 1 answers both RQ1 and RQ2.
    return {
        "RQ1": [0, 1],
        "RQ2": [1, 2],
        "RQ3": [],
        "unmatched_not_relevant": [3],
        "unmatched_no_abstract": [4],
    }


def test_count_included_deduplicates_across_rqs():
    assert count_included(_summary()) == 3


def test_count_included_ignores_non_rq_keys_and_handles_empty():
    assert count_included({"unmatched_not_relevant": [1, 2]}) == 0
    assert count_included({}) == 0


def test_count_included_treats_int_and_str_ids_as_same_paper():
    # IDs are ints in memory but may come back as strings from JSON.
    assert count_included({"RQ1": [1], "RQ2": ["1"]}) == 1


def test_build_prisma_data_included_is_unique_papers():
    data = build_prisma_data({}, DEDUP_STATS, pd.DataFrame(), _summary())
    assert data["included"] == 3


def test_prisma_flow_adds_up():
    data = build_prisma_data({}, DEDUP_STATS, pd.DataFrame(), _summary())
    assert data["screened"] - data["excluded_no_abstract"] == data["assessed_eligibility"]
    assert data["included"] + data["excluded_not_relevant"] == data["assessed_eligibility"]
