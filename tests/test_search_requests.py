"""Search requests: credentials come from the environment and failures are explicit."""

import re
from pathlib import Path

import pytest
import requests

import se_module

ROOT = Path(__file__).resolve().parent.parent
FAKE_KEY = "fake-openalex-key-123"
FAKE_EMAIL = "someone@example.org"


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload or {}
        self.status_code = status_code
        self.text = text
        self.url = f"https://api.example.org/works?api_key={FAKE_KEY}&email={FAKE_EMAIL}"

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"{self.status_code} Client Error for url: {self.url}", response=self
            )


class FakeGet:
    """Records every request and replays the queued responses in order."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {})})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def env(monkeypatch):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.delenv("CONTACT_EMAIL", raising=False)
    monkeypatch.setattr(se_module.time, "sleep", lambda seconds: None)
    return monkeypatch


def _works(n):
    return {"results": [{"id": f"https://openalex.org/W{i}", "title": f"Work {i}"} for i in range(n)]}


# ── OpenAlex ────────────────────────────────────────────────────────────────

def test_openalex_sends_api_key_from_environment(env):
    env.setenv("OPENALEX_API_KEY", FAKE_KEY)
    fake_get = FakeGet(FakeResponse(_works(3)))
    env.setattr(se_module.requests, "get", fake_get)

    results = se_module.search_openalex("green jobs", max_results=10, verbose=False)

    assert len(results) == 3
    params = fake_get.calls[0]["params"]
    assert params["api_key"] == FAKE_KEY
    assert "mailto" not in params


def test_openalex_without_key_sends_no_credentials_and_warns(env, capsys):
    fake_get = FakeGet(FakeResponse(_works(1)))
    env.setattr(se_module.requests, "get", fake_get)

    se_module.search_openalex("green jobs", max_results=10, verbose=False)

    params = fake_get.calls[0]["params"]
    assert "api_key" not in params and "mailto" not in params
    assert "OPENALEX_API_KEY" in capsys.readouterr().out


def test_openalex_page_size_respects_api_maximum(env):
    fake_get = FakeGet(FakeResponse(_works(100)), FakeResponse(_works(100)), FakeResponse(_works(20)))
    env.setattr(se_module.requests, "get", fake_get)

    results = se_module.search_openalex("green jobs", max_results=500, verbose=False)

    assert fake_get.calls[0]["params"]["per_page"] == 100
    # A full page of 100 must trigger the next page (the old code stopped below 200).
    assert [call["params"]["page"] for call in fake_get.calls] == [1, 2, 3]
    assert len(results) == 220


def test_openalex_http_error_raises_instead_of_looking_like_no_results(env):
    env.setenv("OPENALEX_API_KEY", FAKE_KEY)
    env.setattr(se_module.requests, "get", FakeGet(FakeResponse(status_code=401, text="Invalid API key")))

    with pytest.raises(se_module.SearchError) as excinfo:
        se_module.search_openalex("green jobs", max_results=10, verbose=False)

    message = str(excinfo.value)
    assert "OpenAlex" in message and "401" in message
    assert FAKE_KEY not in message  # credentials must never reach logs or the GUI


def test_openalex_failure_on_a_later_page_raises_too(env):
    fake_get = FakeGet(FakeResponse(_works(100)), requests.exceptions.ConnectionError("boom"))
    env.setattr(se_module.requests, "get", fake_get)

    with pytest.raises(se_module.SearchError):
        se_module.search_openalex("green jobs", max_results=500, verbose=False)


# ── PubMed ──────────────────────────────────────────────────────────────────

def test_pubmed_sends_contact_email_only_when_configured(env):
    empty = {"esearchresult": {"idlist": [], "count": "0"}}

    fake_get = FakeGet(FakeResponse(empty))
    env.setattr(se_module.requests, "get", fake_get)
    se_module.search_pubmed("green jobs", max_results=10, verbose=False)
    assert "email" not in fake_get.calls[0]["params"]

    env.setenv("CONTACT_EMAIL", FAKE_EMAIL)
    fake_get = FakeGet(FakeResponse(empty))
    env.setattr(se_module.requests, "get", fake_get)
    se_module.search_pubmed("green jobs", max_results=10, verbose=False)
    assert fake_get.calls[0]["params"]["email"] == FAKE_EMAIL


def test_pubmed_http_error_raises_without_leaking_the_email(env):
    env.setenv("CONTACT_EMAIL", FAKE_EMAIL)
    env.setattr(se_module.requests, "get", FakeGet(FakeResponse(status_code=500)))

    with pytest.raises(se_module.SearchError) as excinfo:
        se_module.search_pubmed("green jobs", max_results=10, verbose=False)

    assert "PubMed" in str(excinfo.value)
    assert FAKE_EMAIL not in str(excinfo.value)


# ── Hygiene ─────────────────────────────────────────────────────────────────

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# Public institutional contact printed by a legacy smoke script.
ALLOWED_EMAILS = {"biblioteca@uniovi.es"}
SKIP_DIRS = {".venv", ".git", "__pycache__", "tests"}


def test_no_email_address_is_hardcoded_in_python_files():
    offenders = []
    for path in ROOT.rglob("*.py"):
        if SKIP_DIRS & set(path.relative_to(ROOT).parts):
            continue
        found = set(EMAIL_RE.findall(path.read_text(encoding="utf-8"))) - ALLOWED_EMAILS
        if found:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_env_example_lists_names_but_no_values():
    names = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip().lstrip("# ").strip()
        if "=" in line and re.match(r"^[A-Z_]+=", line):
            key, value = line.split("=", 1)
            names[key] = value
    for required in ("ANTHROPIC_API_KEY", "OPENALEX_API_KEY", "ELSEVIER_API_KEY", "CONTACT_EMAIL"):
        assert required in names
    assert all(value == "" for value in names.values())
