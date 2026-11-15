"""Loader for ``palet.toml``: model IDs, prices and limits.

Nothing in the code may hardcode a model ID or a price; modules ask this
module instead. Secrets are not handled here (they live in ``.env``).
"""

import tomllib
from functools import lru_cache
from pathlib import Path

from palet.errors import PaletConfigError

CONFIG_PATH = Path(__file__).resolve().parent.parent / "palet.toml"

PHASES = ("arq", "qsp", "map", "synthesis")


@lru_cache(maxsize=None)
def load_config(path: str | Path = CONFIG_PATH) -> dict:
    """Read and validate the settings file (cached per path)."""
    path = Path(path)
    try:
        with open(path, "rb") as f:
            config = tomllib.load(f)
    except FileNotFoundError:
        raise PaletConfigError(f"Settings file not found: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise PaletConfigError(f"Settings file is not valid TOML: {path} ({e})") from e

    _validate(config, path)
    return config


def _validate(config: dict, path: Path) -> None:
    for section in ("models", "pricing", "limits", "search"):
        if section not in config:
            raise PaletConfigError(f"Missing [{section}] section in {path}")

    prices = config["pricing"].get("models", {})
    for phase in PHASES:
        model = config["models"].get(phase)
        if not model:
            raise PaletConfigError(f"Missing model for phase '{phase}' in {path}")
        price = prices.get(model, {})
        if "input_per_mtok" not in price or "output_per_mtok" not in price:
            raise PaletConfigError(
                f"Missing price for model '{model}' (phase '{phase}') in {path}"
            )


_model_override: str | None = None


def set_model_override(model: str | None) -> None:
    """Use ``model`` for every phase of the current run (None = defaults).

    One pipeline runs at a time, so a process-wide override is enough; the
    entry point that sets it is responsible for clearing it afterwards.
    """
    global _model_override
    if not model:
        _model_override = None
        return
    if model not in load_config()["pricing"].get("models", {}):
        raise PaletConfigError(
            f"Model '{model}' is not in the catalogue of palet.toml ([pricing.models])."
        )
    _model_override = model


def clear_model_override() -> None:
    """Go back to the per-phase models of palet.toml."""
    global _model_override
    _model_override = None


def get_default_model() -> str:
    """Model the dashboard preselects: the one configured for MAP."""
    return load_config()["models"]["map"]


def list_models() -> list[dict]:
    """Catalogue of selectable models, current ones first."""
    catalogue = []
    for model_id, entry in load_config()["pricing"].get("models", {}).items():
        catalogue.append({
            "id": model_id,
            "label": entry.get("label", model_id),
            "status": entry.get("status", "current"),
            "input_per_mtok": entry["input_per_mtok"],
            "output_per_mtok": entry["output_per_mtok"],
            "note": entry.get("note", ""),
        })
    catalogue.sort(key=lambda m: m["status"] != "current")
    return catalogue


def get_model(phase: str) -> str:
    """Exact model ID for a pipeline phase (the run override wins, if set)."""
    models = load_config()["models"]
    if phase not in models:
        raise PaletConfigError(f"No model configured for phase '{phase}'")
    return _model_override or models[phase]


def get_limit(name: str) -> int:
    """A value from the [limits] section."""
    limits = load_config()["limits"]
    if name not in limits:
        raise PaletConfigError(f"No limit named '{name}' in palet.toml")
    return limits[name]


def get_screening_settings() -> dict:
    """Screeners (name + model) and number of parallel workers."""
    screening = load_config().get("screening", {})
    screeners = screening.get("screeners", [])
    catalogue = load_config()["pricing"].get("models", {})
    for screener in screeners:
        if screener.get("model") not in catalogue:
            raise PaletConfigError(
                f"Screener '{screener.get('name')}' uses a model that is not in the catalogue: "
                f"{screener.get('model')}"
            )
    if not 1 <= len(screeners) <= 2:
        raise PaletConfigError(f"Screening needs one or two screeners; palet.toml defines {len(screeners)}")
    return {"screeners": [dict(s) for s in screeners], "workers": screening.get("workers", 4)}


def make_screeners(models: list[str]) -> list[dict]:
    """Screeners A (and B) for the given model ids, checked against the catalogue."""
    models = [m.strip() for m in models if m and m.strip()]
    if not 1 <= len(models) <= 2:
        raise PaletConfigError(f"Screening needs one or two screeners; {len(models)} given")
    catalogue = load_config()["pricing"].get("models", {})
    for model in models:
        if model not in catalogue:
            raise PaletConfigError(f"Model not in the catalogue of palet.toml: {model}")
    return [{"name": name, "model": model} for name, model in zip("AB", models)]


def get_assistant_model() -> str:
    """Model of the protocol assistant."""
    model = load_config().get("assistant", {}).get("model") or get_default_model()
    if model not in load_config()["pricing"].get("models", {}):
        raise PaletConfigError(f"The assistant model is not in the catalogue: {model}")
    return model


def get_assignment_model() -> str:
    """Model that charts included records."""
    model = load_config().get("assignment", {}).get("model") or get_default_model()
    if model not in load_config()["pricing"].get("models", {}):
        raise PaletConfigError(f"The assignment model is not in the catalogue: {model}")
    return model


def get_search_setting(name: str):
    """A value from the [search] section."""
    search = load_config()["search"]
    if name not in search:
        raise PaletConfigError(f"No search setting named '{name}' in palet.toml")
    return search[name]


def get_price(model: str) -> tuple[float, float]:
    """(input, output) price in USD per million tokens for a model."""
    prices = load_config()["pricing"].get("models", {})
    if model not in prices:
        raise PaletConfigError(f"No price configured for model '{model}'")
    return prices[model]["input_per_mtok"], prices[model]["output_per_mtok"]


def get_model_options(model: str) -> dict:
    """Extra request parameters configured for a model (e.g. temperature)."""
    return dict(load_config().get("model_options", {}).get(model, {}))


def cost_usd(phase: str, input_tokens: float, output_tokens: float) -> float:
    """Cost in USD of a call made by ``phase`` with the given token counts."""
    input_price, output_price = get_price(get_model(phase))
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def usd_to_eur() -> float:
    """Approximate USD→EUR rate used to display estimates."""
    return load_config()["pricing"].get("usd_to_eur", 1.0)
