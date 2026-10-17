"""The contract every board adapter implements."""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from typing import Any, Protocol

from ..models import District, JobPosting


# A board adapter never touches the network itself: it is handed something that
# turns a URL into decoded JSON. That keeps every parser testable against
# captured payloads, and keeps retry and timeout policy in one place.
class JsonFetcher(Protocol):
    def __call__(self, url: str) -> Any: ...


class JobSource(Protocol):
    """Lists postings cheaply, then fills in detail only where asked."""

    district: District

    def list_postings(self) -> list[JobPosting]:
        """Every currently open posting on the board, unfiltered."""
        ...

    def enrich(self, job: JobPosting) -> JobPosting:
        """Add detail that needs a second request. Returns ``job`` unchanged on failure."""
        ...


_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def strip_html(raw: str | None) -> str | None:
    """Flatten a board's HTML description into plain text for the email."""
    if not raw:
        return None
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text).replace("\xa0", " ")
    cleaned = _WHITESPACE_RE.sub(" ", text).strip()
    return cleaned or None


# Weber marks "open until filled" postings with a close date far in the
# future (2050-01-01). Printing that as a deadline is worse than printing none.
SENTINEL_HORIZON_YEARS = 5


def parse_close_date(raw: str | None) -> date | None:
    """Parse a closing date, discarding the far-future "open until filled" sentinel."""
    parsed = parse_date(raw)
    if parsed is None:
        return None
    if parsed.year - date.today().year >= SENTINEL_HORIZON_YEARS:
        return None
    return parsed


def parse_date(raw: str | None) -> date | None:
    """Parse the ISO timestamps the boards return, with or without an offset."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None
