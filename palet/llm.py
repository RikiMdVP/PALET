"""Shared, lazily created Anthropic client.

The client is built on the first real call, not at import time, so importing
a PALET module never requires an API key and can never terminate the program.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from dotenv import load_dotenv

from palet import config
from palet.errors import PaletConfigError, PaletError

_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _ROOT / ".env"
DEFAULT_CACHE_DIR = _ROOT / ".palet_cache" / "llm"

_client = None
# cache_dir=None disables the cache; replay=True forbids any real API call.
_settings = {"cache_dir": DEFAULT_CACHE_DIR, "replay": False}
_usage: list[dict] = []


def get_client():
    """Return the Anthropic client, creating it on first use."""
    global _client
    if _client is None:
        load_dotenv(dotenv_path=_ENV_FILE)
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise PaletConfigError(
                "ANTHROPIC_API_KEY is not set. Add it to the .env file "
                "(see .env.example)."
            )
        from anthropic import Anthropic

        # Generous retries: screening sends many calls and may hit rate limits.
        _client = Anthropic(api_key=api_key, max_retries=8)
    return _client


def reset_client():
    """Forget the cached client (used by tests)."""
    global _client
    _client = None


@dataclass
class LLMResponse:
    """What a pipeline phase needs from a model reply."""

    text: str
    usage: Any          # exposes .input_tokens and .output_tokens
    model: str
    stop_reason: str | None = None
    cached: bool = False
    cache_key: str | None = None
    created_at: str | None = None      # when the reply was first obtained (kept by the cache)


def configure(cache_dir="unchanged", replay=None) -> None:
    """Set where raw responses are cached and whether to run in replay mode.

    ``cache_dir=None`` turns the cache off. With ``replay=True`` a request
    that is not in the cache raises instead of calling the API, so a run can
    be reproduced exactly and at no cost.
    """
    if cache_dir != "unchanged":
        _settings["cache_dir"] = Path(cache_dir) if cache_dir else None
    if replay is not None:
        _settings["replay"] = bool(replay)


def reset_usage() -> None:
    _usage.clear()


def usage_log() -> list[dict]:
    """Every call made since the last reset (one dict per call)."""
    return list(_usage)


def usage_summary() -> dict:
    """Calls, tokens and cost per phase since the last reset."""
    summary: dict = {}
    for call in _usage:
        phase = summary.setdefault(call["phase"], {
            "calls": 0, "cached_calls": 0, "input_tokens": 0, "output_tokens": 0,
            "cost_usd": 0.0, "models": [],
        })
        phase["calls"] += 1
        phase["cached_calls"] += int(call["cached"])
        phase["input_tokens"] += call["input_tokens"]
        phase["output_tokens"] += call["output_tokens"]
        phase["cost_usd"] = round(phase["cost_usd"] + call["cost_usd"], 6)
        if call["model"] not in phase["models"]:
            phase["models"].append(call["model"])
    return summary


def request_key(request: dict, attempt: int = 0) -> str:
    """sha256 of everything that determines a response."""
    payload = json.dumps({"request": request, "attempt": attempt}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path | None:
    cache_dir = _settings["cache_dir"]
    return None if cache_dir is None else Path(cache_dir) / key[:2] / f"{key}.json"


def _record_usage(phase, model, input_tokens, output_tokens, cached) -> None:
    input_price, output_price = config.get_price(model)
    cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
    _usage.append({
        "phase": phase, "model": model, "cached": cached,
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        # A cached reply costs nothing now; its original cost is kept apart.
        "cost_usd": 0.0 if cached else round(cost, 6),
        "cost_usd_if_uncached": round(cost, 6),
    })


def complete(phase: str, max_tokens_limit: str, system: str, user: str,
             attempt: int = 0, model: str | None = None) -> LLMResponse:
    """Send one system + user message for ``phase`` and return the reply text.

    The model, its token limit and its optional request parameters come from
    palet.toml, so switching models never requires touching the callers
    (``model`` overrides the phase model for this call only).

    The reply text is taken from the ``text`` blocks of the response, wherever
    they are: recent models may open the response with ``thinking`` blocks.

    Raw replies are cached under the sha256 of the request. ``attempt``
    is part of that key, so a retry after an unusable reply is a new request.
    """
    model = model or config.get_model(phase)
    request = {
        "model": model,
        "max_tokens": config.get_limit(max_tokens_limit),
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    # Only sent when configured for this model: recent models reject sampling
    # parameters such as temperature with an HTTP 400.
    request.update(config.get_model_options(model))

    key = request_key(request, attempt)
    path = _cache_path(key)

    if path is not None and path.is_file():
        entry = json.loads(path.read_text(encoding="utf-8"))
        _record_usage(phase, model, entry["input_tokens"], entry["output_tokens"], cached=True)
        return LLMResponse(
            text=entry["text"],
            usage=SimpleNamespace(input_tokens=entry["input_tokens"], output_tokens=entry["output_tokens"]),
            model=model, stop_reason=entry.get("stop_reason"), cached=True, cache_key=key,
            created_at=entry.get("created_at"),
        )

    if _settings["replay"]:
        raise PaletError(
            f"Replay mode: no cached response for a '{phase}' request ({key[:12]}…). "
            "Run once without --replay to record it."
        )

    response = get_client().messages.create(**request)

    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()
    stop_reason = getattr(response, "stop_reason", None)
    input_tokens = getattr(response.usage, "input_tokens", 0)
    output_tokens = getattr(response.usage, "output_tokens", 0)
    _record_usage(phase, model, input_tokens, output_tokens, cached=False)

    if not text:
        raise PaletError(
            f"The model returned no text for phase '{phase}' (stop_reason={stop_reason}). "
            f"If it stopped at the token limit, raise '{max_tokens_limit}' in palet.toml."
        )

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "key": key, "phase": phase, "attempt": attempt, "request": request,
            "text": text, "stop_reason": stop_reason,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "created_at": created_at,
        }, ensure_ascii=False, indent=1), encoding="utf-8")

    return LLMResponse(text=text, usage=response.usage, model=model, stop_reason=stop_reason,
                       cached=False, cache_key=key, created_at=created_at)
