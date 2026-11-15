"""Protocol assistant: advice on questions, draft protocol, approval. The model is simulated."""

import json
from types import SimpleNamespace

import pytest

from palet import drafting, llm
from palet.errors import PaletError
from palet.protocol import load_protocol
from palet.search import build_query

CONTEXT = "A review of school-based programmes to prevent adolescent smoking in Latin America since 2010."
QUESTIONS = ["Which school programmes reduce smoking among adolescents?",
             "What explains differences in effectiveness and how much do programmes cost?"]

ANALYSIS = {
    "overall": "Two questions; the second asks two things.",
    "questions": [
        {"id": "RQ1", "issues": [], "suggested": "something the model should not have changed", "change": "none", "rationale": ""},
        {"id": "RQ2", "issues": ["Asks about explanations and about costs."],
         "suggested": "What explains differences in the effectiveness of school programmes against adolescent smoking?",
         "change": "major", "rationale": "Costs are a separate question."}],
    "gaps": ["Costs would need their own question."]}

DRAFT = {
    "title": "School programmes against adolescent smoking in Latin America",
    "year_from": 2010, "year_to": None,
    "criteria": [
        {"id": "IC1", "kind": "include", "dimension": "population", "rule": "Studies adolescents aged 10 to 19.", "reason_code": "WRONG_POPULATION"},
        {"id": "IC2", "kind": "include", "dimension": "concept", "rule": "Evaluates a school-based smoking prevention programme.", "reason_code": "NO_SCHOOL_PROGRAMME"},
        {"id": "EC1", "kind": "exclude", "dimension": "context", "rule": "Set only outside Latin America (e.g. USA, Spain).", "reason_code": "WRONG_CONTEXT"}],
    "searches": [
        {"rq": "RQ1", "blocks": {"programme": ['"school-based"', "school programme", "School Programme", "prevention AND control"],
                                  "smoking": ["smoking", "tobacco use"]}},
        {"rq": "RQ2", "blocks": {"programme": ["school-based", "school program"], "smoking": ["smoking", "tobacco"],
                                  "effect": ["effectiveness", "moderators"]}}],
    "notes": ["'smoking' alone is broad."]}


@pytest.fixture
def model(monkeypatch):
    replies, seen = [], []

    def create(**kwargs):
        seen.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=replies.pop(0))],
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=500), stop_reason="end_turn")

    monkeypatch.setattr(llm, "get_client", lambda: SimpleNamespace(messages=SimpleNamespace(create=create)))
    return SimpleNamespace(replies=replies, seen=seen)


def test_questions_are_cleaned():
    cleaned = drafting.clean_questions(["1. " + QUESTIONS[0], "", "RQ2:  " + QUESTIONS[1], "- " + QUESTIONS[0]])
    assert cleaned == [QUESTIONS[0], QUESTIONS[1], QUESTIONS[0]]
    for bad in ([], ["", " "], ["too short?"], [QUESTIONS[0]] * 13):
        with pytest.raises(PaletError):
            drafting.clean_questions(bad)


def test_analysis_keeps_unchanged_questions_exactly_as_written(model):
    model.replies.append("```json\n" + json.dumps(ANALYSIS) + "\n```")
    analysis = drafting.analyse_questions(CONTEXT, QUESTIONS)
    assert analysis.questions[0].suggested == QUESTIONS[0]            # change "none": the original, whatever the model wrote
    assert analysis.questions[1].change == "major" and analysis.gaps
    sent = model.seen[0]
    assert sent["model"] == "claude-opus-5-5" and "RQ2: " + QUESTIONS[1] in sent["messages"][0]["content"]
    assert CONTEXT in sent["messages"][0]["content"]


def test_unusable_replies_are_retried_once_then_reported(model):
    wrong_ids = json.dumps({**ANALYSIS, "questions": ANALYSIS["questions"][:1]})
    model.replies += ["no json here", wrong_ids]
    with pytest.raises(PaletError, match="usable reply"):
        drafting.analyse_questions(CONTEXT, QUESTIONS)
    assert len(model.seen) == 2


@pytest.mark.parametrize("mutate", [
    lambda d: d["criteria"][0].update(reason_code="bad code"),
    lambda d: d["criteria"][0].update(dimension="language"),
    lambda d: d["criteria"].__setitem__(slice(None), [c for c in d["criteria"] if c["kind"] == "exclude"]),
    lambda d: d["searches"].pop(),
    lambda d: d["searches"][0]["blocks"].pop("smoking"),
    lambda d: d["searches"][0]["blocks"].update({"Bad Name": ["x"]}),
])
def test_invalid_drafts_are_rejected(model, mutate):
    data = json.loads(json.dumps(DRAFT))
    mutate(data)
    model.replies += [json.dumps(data), json.dumps(data)]
    with pytest.raises(PaletError):
        drafting.draft_protocol(CONTEXT, QUESTIONS)


def test_draft_becomes_a_valid_protocol_file_and_can_be_approved(model, tmp_path):
    model.replies.append(json.dumps(DRAFT))
    draft = drafting.draft_protocol(CONTEXT, QUESTIONS)
    assert draft.searches[0].blocks["programme"] == ["school-based", "school programme"]   # quotes, repeats and operators removed
    final = [QUESTIONS[0], ANALYSIS["questions"][1]["suggested"]]
    path = tmp_path / "smoking.yaml"
    drafting.write_protocol(path, drafting.protocol_data(draft, final, QUESTIONS), CONTEXT)

    protocol = load_protocol(path)
    assert protocol.status == "draft" and protocol.version == 1 and protocol.year_from == 2010
    assert protocol.research_questions == {"RQ1": final[0], "RQ2": final[1]}
    assert protocol.research_questions_original == {"RQ2": QUESTIONS[1]}          # only the one that changed
    assert [c.id for c in protocol.criteria] == ["IC1", "IC2", "EC1", "IC3"]
    assert protocol.criteria[-1].dimension == "study_type"                         # added by the code, not the model
    assert [s.id for s in protocol.sources] == ["openalex_rq1", "openalex_rq2"]
    assert all(s.model_extra["status"] == "proposed" for s in protocol.sources)
    assert build_query(protocol.source("openalex_rq1").model_extra["blocks"]).startswith('("school-based" OR "school programme")')
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Draft protocol written by the PALET protocol assistant") and CONTEXT in text

    with pytest.raises(PaletError, match="already exists"):
        drafting.write_protocol(path, drafting.protocol_data(draft, final, QUESTIONS), CONTEXT)

    for bad in ("", "x", 'A "B"'):
        with pytest.raises(PaletError):
            drafting.approve_protocol(path, bad)
    assert load_protocol(path).status == "draft"
    drafting.approve_protocol(path, "Ana  Pérez; J. Ruiz")
    approved = load_protocol(path)
    assert approved.status == "approved" and approved.approved_by == "Ana Pérez; J. Ruiz" and approved.approved_at
    assert approved.research_questions == protocol.research_questions and approved.criteria == protocol.criteria
    with pytest.raises(PaletError, match="already approved"):
        drafting.approve_protocol(path, "Ana Pérez")


def test_slug():
    assert drafting.slug("Tabaco y Adolescentes — 2026") == "tabaco_y_adolescentes_2026"
    with pytest.raises(PaletError):
        drafting.slug("¿?")
