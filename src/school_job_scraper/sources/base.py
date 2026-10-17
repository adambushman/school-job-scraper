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

# Tags that end a block of text. Replaced with newlines before the rest of the
# markup is stripped, so block structure survives into the plain text.
_BLOCK_END_RE = re.compile(
    r"</(?:p|div|li|ul|ol|h[1-6]|tr|table|blockquote)>|<br\s*/?>|<hr\s*/?>",
    re.IGNORECASE,
)

# A metadata line: a short label, then a colon, then its value -
# "Title: Elementary Teacher", "FLSA Status: Exempt". The length and word-count
# ceilings are what separate a label from prose that happens to end in a colon
# ("The following position is available at Syracuse Junior High:").
_LABEL_MAX_CHARS = 40
_LABEL_MAX_WORDS = 5

# Text the districts repeat verbatim on every posting. It describes the hiring
# process or restates policy, so it never distinguishes one opening from
# another - and on postings where the "Application Note:" label carries an
# inline value it would otherwise lead the summary. Matched as a prefix,
# case-insensitively.
STANDING_NOTES: tuple[str, ...] = (
    "this position will remain open until filled",
    "in accordance with weber school district policy",
    "weber school district has the right to revise",
    "weber school district is an equal opportunity",
    "attendance is an essential function of this position",
)

# Section headings in the districts' posting template. Dropped so the prose
# under the first one leads instead. Matched in full, not as a prefix, so a
# genuine short line of content ("ASSISTANT GIRLS BASKETBALL COACH") survives.
SECTION_HEADINGS: frozenset[str] = frozenset(
    {
        "job overview",
        "overview",
        "job summary",
        "position summary",
        "summary",
        "essential duties and responsibilties",
        "essential duties and responsibilities",
        "other duties and responsibilties",
        "other duties and responsibilities",
        "duties and responsibilities",
        "physical requirements",
        "qualifications",
        "job description",
    }
)


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


def _is_standing_note(block: str) -> bool:
    """True for text the district repeats on every posting."""
    lowered = block.lower()
    return any(lowered.startswith(note) for note in STANDING_NOTES)


def _is_section_heading(block: str) -> bool:
    """True for a bare heading from the posting template."""
    return block.rstrip(":").strip().lower() in SECTION_HEADINGS


def _looks_like_metadata(block: str) -> bool:
    """True for a "Label: value" line of posting metadata."""
    label, separator, _ = block.partition(":")
    if not separator:
        return False
    label = label.strip()
    return 0 < len(label) <= _LABEL_MAX_CHARS and len(label.split()) <= _LABEL_MAX_WORDS


def _text_blocks(raw: str) -> list[str]:
    """Split a description into plain-text blocks, HTML or not."""
    marked = _BLOCK_END_RE.sub("\n", raw)
    text = html.unescape(_TAG_RE.sub(" ", marked)).replace("\xa0", " ")
    blocks = []
    for line in text.split("\n"):
        cleaned = _WHITESPACE_RE.sub(" ", line).strip()
        if cleaned:
            blocks.append(cleaned)
    return blocks


def extract_summary(raw: str | None) -> str | None:
    """The first genuinely informative prose in a description.

    Weber opens every posting with a block of payroll metadata - title,
    contract days, salary schedule, FLSA status - followed by a standing note
    about the application process. None of it distinguishes one posting from
    another, so it is dropped and the text that follows leads instead.

    Falls back to the flattened description when a posting is nothing but
    metadata: showing the labels beats showing nothing.
    """
    if not raw:
        return None
    blocks = _text_blocks(raw)

    prose: list[str] = []
    skip_next = False
    for block in blocks:
        if skip_next:
            # The previous block was a bare label, so this is its value.
            skip_next = False
            continue
        if _is_standing_note(block) or _is_section_heading(block):
            continue
        if _looks_like_metadata(block):
            # "Application Note:" with the text on the next line (a <br> inside
            # the paragraph) leaves the label alone in its own block.
            skip_next = block.endswith(":")
            continue
        prose.append(block)

    if prose:
        return " ".join(prose)
    return " ".join(blocks) or None


def parse_date(raw: str | None) -> date | None:
    """Parse the ISO timestamps the boards return, with or without an offset."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None
