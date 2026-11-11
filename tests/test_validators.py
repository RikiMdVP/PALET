"""Characterisation tests for the output validators of ARQ and MAP."""

import pytest

import arq_module
import map_module_v2

LONG_REASONING = "The abstract directly studies job creation linked to the green transition."


def _map_reply(**overrides):
    reply = {
        "paper_id": 1,
        "title": "A paper",
        "assignments": ["RQ1"],
        "reasoning": LONG_REASONING,
        "confidence": "high",
    }
    reply.update(overrides)
    return reply


# ── MAP ─────────────────────────────────────────────────────────────────────

def test_map_valid_reply():
    assert map_module_v2.validate_map_output(_map_reply(), num_rqs=3) == (True, "")


def test_map_accepts_several_rqs_and_no_rq():
    assert map_module_v2.validate_map_output(_map_reply(assignments=["RQ1", "RQ3"]), 3)[0]
    assert map_module_v2.validate_map_output(_map_reply(assignments=[], reasoning=""), 3)[0]


@pytest.mark.parametrize("field", ["paper_id", "title", "assignments", "reasoning", "confidence"])
def test_map_rejects_missing_field(field):
    reply = _map_reply()
    del reply[field]
    valid, message = map_module_v2.validate_map_output(reply, 3)
    assert not valid and field in message


def test_map_rejects_rq_out_of_range_and_unknown_labels():
    assert not map_module_v2.validate_map_output(_map_reply(assignments=["RQ4"]), 3)[0]
    assert not map_module_v2.validate_map_output(_map_reply(assignments=["unmatched"]), 3)[0]


def test_map_rejects_unknown_confidence():
    assert not map_module_v2.validate_map_output(_map_reply(confidence="very high"), 3)[0]


def test_map_requires_reasoning_when_a_paper_is_assigned():
    valid, message = map_module_v2.validate_map_output(_map_reply(reasoning="Too short."), 3)
    assert not valid and "Reasoning" in message


def test_map_prompt_gets_the_research_questions_injected():
    prompt = map_module_v2.generate_map_prompt(["First question?", "Second question?"])
    assert "- First question?\n- Second question?" in prompt
    assert "{{RESEARCH_QUESTIONS_WILL_BE_INSERTED_HERE}}" not in prompt


# ── ARQ ─────────────────────────────────────────────────────────────────────

def _arq_output(n_rqs=3, n_keywords=8):
    return {
        "research_questions": [f"Question {i}?" for i in range(n_rqs)],
        "keywords": [f"keyword {i}" for i in range(n_keywords)],
        "reasoning": "Because.",
    }


def test_arq_valid_output_and_default_criteria():
    output = _arq_output()
    assert arq_module.validate_arq_output(output) == (True, [])
    assert output["inclusion_criteria"] == [] and output["exclusion_criteria"] == []


@pytest.mark.parametrize("key", ["research_questions", "keywords", "reasoning"])
def test_arq_rejects_missing_key(key):
    output = _arq_output()
    del output[key]
    valid, errors = arq_module.validate_arq_output(output)
    assert not valid and key in errors[0]


def test_arq_rejects_wrong_types():
    output = _arq_output()
    output["keywords"] = "a, b, c"
    assert not arq_module.validate_arq_output(output)[0]


def test_arq_keyword_count_limits():
    assert not arq_module.validate_arq_output(_arq_output(n_keywords=4))[0]
    assert not arq_module.validate_arq_output(_arq_output(n_keywords=21))[0]


@pytest.mark.xfail(strict=True, reason="WP2: ARQ limits a review to 1-5 research questions; "
                                       "the ISABEL chapter has 7")
def test_arq_accepts_the_seven_research_questions_of_the_chapter():
    assert arq_module.validate_arq_output(_arq_output(n_rqs=7))[0]
