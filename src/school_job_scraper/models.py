"""Core data types shared by sources, filters and renderers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Protocol


class JsonFetcher(Protocol):
    """Turns a URL into decoded JSON.

    Board adapters are handed one of these rather than touching the network
    themselves, which keeps every parser testable against captured payloads and
    keeps retry and timeout policy in a single place.
    """

    def __call__(self, url: str) -> Any: ...


class District(str, Enum):
    """The districts whose boards we scan."""

    WEBER = "Weber School District"
    DAVIS = "Davis School District"
    OGDEN = "Ogden School District"


@dataclass(frozen=True)
class JobPosting:
    """One posting, normalised across the three boards.

    Fields the boards do not all provide are optional. ``job_type`` holds the
    board's own wording (SchoolSpring says "Full-time"); Davis omits it
    entirely, so full-time status there is inferred from the text.
    """

    district: District
    job_id: str
    title: str
    employer: str
    url: str
    job_type: str | None = None
    category: str | None = None
    description: str | None = None
    posted_date: date | None = None
    close_date: date | None = None
    is_internal: bool = False

    @property
    def search_text(self) -> str:
        """Lower-cased title and employer, the fields every board populates.

        Descriptions are deliberately excluded: they mention excluded terms far
        too freely ("works alongside the special education team") and matching
        on them produced false exclusions against live data.
        """
        return f"{self.title} {self.employer}".lower()


@dataclass(frozen=True)
class Decision:
    """Why a posting was kept or dropped. Carried so runs are auditable."""

    posting: JobPosting
    qualifies: bool
    reason: str
