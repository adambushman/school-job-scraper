"""The shared JSON fetcher: headers, timeouts and retries."""

from __future__ import annotations

from typing import Any

import pytest

from school_job_scraper.http import FetchError, build_fetcher


class FakeResponse:
    def __init__(self, payload: Any = None, status: int = 200) -> None:
        self._payload = payload if payload is not None else {"ok": True}
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise OSError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_fetcher_returns_decoded_json() -> None:
    session = FakeSession([FakeResponse({"value": 42})])
    fetch = build_fetcher(session=session, timeout=5.0, retries=1, backoff=0.0)
    assert fetch("https://example.test/a") == {"value": 42}


def test_fetcher_sends_a_browser_user_agent_and_json_accept() -> None:
    """The SchoolSpring edge rejects requests without a normal user agent."""
    session = FakeSession([FakeResponse()])
    build_fetcher(session=session, timeout=5.0, retries=1, backoff=0.0)("https://example.test/a")
    _, kwargs = session.calls[0]
    headers = kwargs["headers"]
    assert "Mozilla" in headers["User-Agent"]
    assert headers["Accept"] == "application/json"
    assert kwargs["timeout"] == 5.0


def test_fetcher_retries_then_succeeds() -> None:
    session = FakeSession([OSError("flaky"), FakeResponse({"value": 1})])
    fetch = build_fetcher(session=session, timeout=5.0, retries=3, backoff=0.0)
    assert fetch("https://example.test/a") == {"value": 1}
    assert len(session.calls) == 2


def test_fetcher_raises_after_exhausting_retries() -> None:
    session = FakeSession([OSError("down"), OSError("down"), OSError("down")])
    fetch = build_fetcher(session=session, timeout=5.0, retries=3, backoff=0.0)
    with pytest.raises(FetchError) as caught:
        fetch("https://example.test/a")
    assert "example.test" in str(caught.value)
    assert len(session.calls) == 3
