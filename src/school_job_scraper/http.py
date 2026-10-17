"""The one place network policy lives: headers, timeouts and retries."""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol

from .models import JsonFetcher

logger = logging.getLogger(__name__)

# SchoolSpring sits behind an edge that serves bot-blocking pages to clients
# with no recognisable user agent, so send a normal one.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


class FetchError(RuntimeError):
    """A URL could not be fetched after all retries."""


class _Session(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


def build_fetcher(
    session: _Session,
    timeout: float = 30.0,
    retries: int = 3,
    backoff: float = 1.5,
) -> JsonFetcher:
    """Return a ``url -> decoded JSON`` callable.

    Retries are linear rather than exponential: these are small public boards
    and a failure is almost always a transient blip, not congestion we need to
    back away from.
    """

    def fetch(url: str) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                response = session.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_error = exc
                logger.debug("attempt %d/%d failed for %s: %s", attempt, retries, url, exc)
                if attempt < retries and backoff:
                    time.sleep(backoff * attempt)
        raise FetchError(f"could not fetch {url}: {last_error}") from last_error

    return fetch


def default_session() -> Any:
    """A plain ``requests`` session. Imported lazily so tests need no network stack."""
    import requests

    return requests.Session()
