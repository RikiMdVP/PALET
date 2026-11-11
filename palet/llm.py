"""Shared, lazily created Anthropic client.

The client is built on the first real call, not at import time, so importing
a PALET module never requires an API key and can never terminate the program.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from palet.errors import PaletConfigError

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
