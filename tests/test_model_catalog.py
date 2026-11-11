"""Model catalogue, per-run model choice and the endpoints the dashboard uses."""

import pytest
from fastapi.testclient import TestClient

import app as app_module
from palet import config
from palet.errors import PaletConfigError

CURRENT = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-2"}


@pytest.fixture(autouse=True)
def clean_override():
    config.clear_model_override()
    yield
    config.clear_model_override()


@pytest.fixture
def client():
    return TestClient(app_module.app)


# ── Catalogue ───────────────────────────────────────────────────────────────

def test_catalogue_lists_current_models_with_label_and_price():
    models = {m["id"]: m for m in config.list_models()}
    assert CURRENT <= set(models)
    for model in models.values():
        assert model["label"]
        assert model["input_per_mtok"] > 0 and model["output_per_mtok"] > 0
        assert model["status"] in {"current", "legacy"}


def test_catalogue_puts_current_models_before_legacy_ones():
    statuses = [m["status"] for m in config.list_models()]
    assert statuses == sorted(statuses, key=lambda s: s != "current")


def test_default_model_is_in_the_catalogue():
    ids = {m["id"] for m in config.list_models()}
    assert config.get_default_model() in ids


# ── Per-run override ────────────────────────────────────────────────────────

def test_override_applies_to_every_phase_and_can_be_cleared():
    config.set_model_override("claude-haiku-5-5")
    assert {config.get_model(phase) for phase in config.PHASES} == {"claude-haiku-5-5"}
    assert config.cost_usd("map", 1_000_000, 0) == pytest.approx(config.get_price("claude-haiku-5-5")[0])

    config.clear_model_override()
    assert config.get_model("map") == config.get_default_model()


def test_override_with_none_or_empty_keeps_the_default():
    config.set_model_override(None)
    assert config.get_model("map") == config.get_default_model()
    config.set_model_override("")
    assert config.get_model("map") == config.get_default_model()


def test_override_rejects_models_outside_the_catalogue():
    with pytest.raises(PaletConfigError, match="not-a-model"):
        config.set_model_override("not-a-model")


def test_llm_request_uses_the_overridden_model(monkeypatch):
    from types import SimpleNamespace

    from palet import llm

    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            stop_reason="end_turn",
        )

    monkeypatch.setattr(llm, "get_client", lambda: SimpleNamespace(messages=SimpleNamespace(create=create)))
    config.set_model_override("claude-sonnet-5-5")
    response = llm.complete("map", "map_max_tokens", system="S", user="U")
    assert seen["model"] == "claude-sonnet-5-5"
    assert response.model == "claude-sonnet-5-5"


# ── Endpoints ───────────────────────────────────────────────────────────────

def test_api_models_returns_catalogue_and_default(client):
    data = client.get("/api/models").json()
    assert data["default"] == config.get_default_model()
    assert CURRENT <= {m["id"] for m in data["models"]}


def test_api_run_rejects_unknown_model(client):
    response = client.post("/api/run", json={"seed_prompt": "x" * 60, "model": "not-a-model"})
    assert response.status_code == 400
    assert app_module.pipeline_state["running"] is False


def test_estimate_follows_the_selected_model(client):
    body = {"seed_prompt": "x" * 400, "max_results": 10}
    default = client.post("/api/estimate-cost", json=body).json()
    cheap = client.post("/api/estimate-cost", json=body | {"model": "claude-haiku-5-5"}).json()
    assert cheap["total_cost_usd"] < default["total_cost_usd"]
    assert cheap["model"] == "claude-haiku-5-5"
    assert default["model"] == config.get_default_model()


def test_gui_thread_applies_and_then_clears_the_model(monkeypatch, tmp_path):
    import arq_module

    seen = {}

    def fake_extract(*args, **kwargs):
        seen["model"] = config.get_model("arq")
        raise RuntimeError("stop here")

    monkeypatch.setattr(arq_module, "extract_keywords", fake_extract)
    monkeypatch.setattr(app_module, "RESULTS_DIR", tmp_path / "results")
    saved = []
    monkeypatch.setattr(app_module, "add_run_to_history", saved.append)

    app_module.run_pipeline_thread("a seed prompt", {"model": "claude-haiku-5-5"})

    assert seen["model"] == "claude-haiku-5-5"
    assert saved[0]["model"] == "claude-haiku-5-5"
    assert config.get_model("arq") == config.get_default_model()  # cleared afterwards
