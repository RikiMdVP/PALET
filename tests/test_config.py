"""palet.toml is the only place where model IDs and prices may live."""

import re
from pathlib import Path

import pytest

from palet import config
from palet.errors import PaletConfigError

ROOT = Path(__file__).resolve().parent.parent
ACTIVE_CODE = (
    sorted((ROOT / "scripts").glob("*.py"))
    + sorted((ROOT / "palet").glob("*.py"))
    + [ROOT / "palet.py", ROOT / "app.py", ROOT / "prisma_validator.py"]
)


def test_every_phase_has_a_model_and_a_price():
    for phase in config.PHASES:
        model = config.get_model(phase)
        input_price, output_price = config.get_price(model)
        assert model and input_price > 0 and output_price > 0


def test_base_model_is_opus_5_5_with_its_published_price():
    assert {config.get_model(phase) for phase in config.PHASES} == {"claude-opus-5-5"}
    assert config.get_price("claude-opus-5-5") == (4.0, 20.0)


def test_sampling_parameters_only_for_models_that_accept_them():
    # Opus 5.5 answers HTTP 400 to temperature/top_p/top_k.
    assert config.get_model_options("claude-opus-5-5") == {}
    assert config.get_model_options("claude-sonnet-4-6") == {"temperature": 0}
    assert config.get_model_options("unknown-model") == {}


def test_cost_is_computed_from_configured_prices():
    input_price, output_price = config.get_price(config.get_model("map"))
    assert config.cost_usd("map", 1_000_000, 0) == pytest.approx(input_price)
    assert config.cost_usd("map", 0, 1_000_000) == pytest.approx(output_price)
    assert config.cost_usd("map", 0, 0) == 0


def test_limits_and_search_settings_are_available():
    assert config.get_limit("map_max_tokens") > 0
    assert 1 <= config.get_search_setting("openalex_per_page") <= 100


def test_unknown_names_raise_config_error():
    with pytest.raises(PaletConfigError):
        config.get_model("nonexistent-phase")
    with pytest.raises(PaletConfigError):
        config.get_limit("nonexistent_limit")
    with pytest.raises(PaletConfigError):
        config.get_price("nonexistent-model")


def test_missing_or_broken_settings_file_raises(tmp_path):
    with pytest.raises(PaletConfigError, match="not found"):
        config.load_config(tmp_path / "missing.toml")

    broken = tmp_path / "broken.toml"
    broken.write_text("[models\narq = ", encoding="utf-8")
    with pytest.raises(PaletConfigError, match="not valid TOML"):
        config.load_config(broken)

    incomplete = tmp_path / "incomplete.toml"
    incomplete.write_text(
        '[models]\narq = "m"\nqsp = "m"\nmap = "m"\nsynthesis = "m"\n'
        "[pricing]\n[limits]\n[search]\n",
        encoding="utf-8",
    )
    with pytest.raises(PaletConfigError, match="Missing price"):
        config.load_config(incomplete)


def test_modules_use_the_configured_values():
    import se_module
    import synthesis_module

    assert se_module.OPENALEX_PER_PAGE == config.get_search_setting("openalex_per_page")
    assert synthesis_module.MAX_PAPERS_PER_RQ == config.get_limit("synthesis_max_papers_per_rq")
    assert synthesis_module.MAX_TOKENS_SYNTH == config.get_limit("synthesis_max_tokens")


def test_gui_cost_estimate_uses_configured_prices():
    import app as app_module

    estimate = app_module.estimate_cost("x" * 4000, max_results=10)
    expected = sum(
        config.cost_usd(phase.lower(), tokens["input"], tokens["output"])
        for phase, tokens in estimate["breakdown"].items()
    )
    assert estimate["total_cost_usd"] == pytest.approx(expected, abs=1e-3)
    assert config.get_model("map") in estimate["note"]


MODEL_ID_RE = re.compile(r"""['"]claude-[a-z0-9.\-]+['"]""")
PRICE_RE = re.compile(r"0\.0000\d+|PRICE_PER_MTOK\s*=\s*\d")


@pytest.mark.parametrize("path", ACTIVE_CODE, ids=lambda p: p.name)
def test_no_model_id_or_price_hardcoded(path):
    source = path.read_text(encoding="utf-8")
    assert MODEL_ID_RE.findall(source) == []
    assert PRICE_RE.findall(source) == []
