"""Response cache, replay mode and usage ledger of palet.llm."""

from types import SimpleNamespace

import pytest

from palet import llm
from palet.errors import PaletError


class CountingClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            content=[SimpleNamespace(type="thinking", thinking=""),
                     SimpleNamespace(type="text", text=self.replies.pop(0))],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=500),
            stop_reason="end_turn",
        )


@pytest.fixture
def client(monkeypatch, tmp_path):
    client = CountingClient(["first", "second", "third"])
    monkeypatch.setattr(llm, "get_client", lambda: client)
    llm.configure(cache_dir=tmp_path / "cache")
    return client


def _ask(user="U", attempt=0, **kwargs):
    return llm.complete("map", "map_max_tokens", system="S", user=user, attempt=attempt, **kwargs)


def test_identical_request_is_answered_from_the_cache(client):
    first, second = _ask(), _ask()
    assert client.calls == 1
    assert (first.text, first.cached) == ("first", False)
    assert (second.text, second.cached) == ("first", True)
    assert second.usage.input_tokens == 1000 and second.cache_key == first.cache_key


def test_different_input_model_or_attempt_is_a_different_request(client):
    _ask(user="A")
    _ask(user="B")
    _ask(user="A", attempt=1)          # a retry must not get the same unusable reply back
    assert client.calls == 3
    key = llm.request_key({"model": "m", "system": "S"})
    assert key != llm.request_key({"model": "other", "system": "S"})
    assert key != llm.request_key({"model": "m", "system": "S"}, attempt=1)
    assert len(key) == 64


def test_model_can_be_overridden_per_call(client):
    response = _ask(model="claude-sonnet-5-5")
    assert response.model == "claude-sonnet-5-5"


def test_replay_never_calls_the_api(client):
    _ask(user="recorded")
    llm.configure(replay=True)
    assert _ask(user="recorded").text == "first"
    with pytest.raises(PaletError, match="Replay mode"):
        _ask(user="never recorded")
    assert client.calls == 1


def test_cache_can_be_disabled(client):
    llm.configure(cache_dir=None)
    _ask(), _ask()
    assert client.calls == 2


def test_usage_ledger_counts_tokens_and_does_not_charge_cached_calls(client):
    _ask(), _ask()
    summary = llm.usage_summary()["map"]
    assert summary["calls"] == 2 and summary["cached_calls"] == 1
    assert summary["input_tokens"] == 2000 and summary["output_tokens"] == 1000
    one_call = (1000 * 4.0 + 500 * 20.0) / 1_000_000          # Opus 5.5 prices
    assert summary["cost_usd"] == pytest.approx(one_call)
    assert summary["models"] == ["claude-opus-5-5"]
    assert [call["cached"] for call in llm.usage_log()] == [False, True]
