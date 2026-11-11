"""palet.llm.complete: one place that knows how to call a model."""

from types import SimpleNamespace

import pytest

from palet import config, llm
from palet.errors import PaletError


class RecordingClient:
    def __init__(self, blocks, stop_reason="end_turn"):
        self.blocks = blocks
        self.stop_reason = stop_reason
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(
            content=self.blocks,
            usage=SimpleNamespace(input_tokens=12, output_tokens=34),
            stop_reason=self.stop_reason,
        )


def _text(value):
    return SimpleNamespace(type="text", text=value)


def _thinking():
    return SimpleNamespace(type="thinking", thinking="")


def _use(monkeypatch, client):
    monkeypatch.setattr(llm, "get_client", lambda: client)
    return client


def test_request_is_built_from_the_settings_file(monkeypatch):
    client = _use(monkeypatch, RecordingClient([_text("hello")]))
    response = llm.complete("map", "map_max_tokens", system="SYS", user="USER")

    request = client.requests[0]
    assert request["model"] == config.get_model("map")
    assert request["max_tokens"] == config.get_limit("map_max_tokens")
    assert request["system"] == "SYS"
    assert request["messages"] == [{"role": "user", "content": "USER"}]
    assert response.text == "hello"
    assert response.usage.input_tokens == 12 and response.usage.output_tokens == 34


def test_no_sampling_parameters_are_sent_to_the_base_model(monkeypatch):
    client = _use(monkeypatch, RecordingClient([_text("hello")]))
    llm.complete("map", "map_max_tokens", system="SYS", user="USER")
    assert not {"temperature", "top_p", "top_k"} & set(client.requests[0])


def test_configured_model_options_are_sent(monkeypatch):
    monkeypatch.setattr(config, "get_model", lambda phase: "claude-sonnet-4-6")
    client = _use(monkeypatch, RecordingClient([_text("hello")]))
    llm.complete("map", "map_max_tokens", system="SYS", user="USER")
    assert client.requests[0]["temperature"] == 0


def test_text_is_found_after_thinking_blocks(monkeypatch):
    # Models that think first open the response with thinking blocks.
    _use(monkeypatch, RecordingClient([_thinking(), _text('{"a": 1}')]))
    assert llm.complete("map", "map_max_tokens", system="S", user="U").text == '{"a": 1}'


def test_reply_without_text_raises_a_clear_error(monkeypatch):
    _use(monkeypatch, RecordingClient([_thinking()], stop_reason="max_tokens"))
    with pytest.raises(PaletError, match="map_max_tokens"):
        llm.complete("map", "map_max_tokens", system="S", user="U")
