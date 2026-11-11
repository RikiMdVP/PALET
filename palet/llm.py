"""Shared, lazily created Anthropic client.

The client is built on the first real call, not at import time, so importing
a PALET module never requires an API key and can never terminate the program.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from palet import config
from palet.errors import PaletConfigError, PaletError

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
_client = None


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

        _client = Anthropic(api_key=api_key)
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


def complete(phase: str, max_tokens_limit: str, system: str, user: str) -> LLMResponse:
    """Send one system + user message for ``phase`` and return the reply text.

    The model, its token limit and its optional request parameters come from
    palet.toml, so switching models never requires touching the callers.

    The reply text is taken from the ``text`` blocks of the response, wherever
    they are: recent models may open the response with ``thinking`` blocks.
    """
    model = config.get_model(phase)
    request = {
        "model": model,
        "max_tokens": config.get_limit(max_tokens_limit),
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    # Only sent when configured for this model: recent models reject sampling
    # parameters such as temperature with an HTTP 400.
    request.update(config.get_model_options(model))

    response = get_client().messages.create(**request)

    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()
    stop_reason = getattr(response, "stop_reason", None)

    if not text:
        raise PaletError(
            f"The model returned no text for phase '{phase}' (stop_reason={stop_reason}). "
            f"If it stopped at the token limit, raise '{max_tokens_limit}' in palet.toml."
        )

    return LLMResponse(text=text, usage=response.usage, model=model, stop_reason=stop_reason)
