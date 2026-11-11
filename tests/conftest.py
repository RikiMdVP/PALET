"""Shared pytest configuration for PALET.

Forces a dummy Anthropic key so that no test can ever reach the real API,
even when a real key is exported in the shell or present in .env
(python-dotenv does not override variables that are already set).
"""

import os

os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"
os.environ.setdefault("MPLBACKEND", "Agg")


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_llm_state():
    """No test reads or writes the real response cache or usage ledger."""
    from palet import llm

    llm.configure(cache_dir=None, replay=False)
    llm.reset_usage()
    yield
    llm.configure(cache_dir=None, replay=False)
    llm.reset_usage()
