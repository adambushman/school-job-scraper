"""Decide whether a posting is a full-time elementary classroom teacher role.

The boards carry almost no reliable structured metadata for this, so the rules
below work on title and school name. Two principles keep the false-positive
rate down:

* Exclusions are checked before inclusions, because a title like "Elementary
  Special Education Complex Support Needs Teacher" satisfies every positive
  signal we have and is still not what we want.
* Elementary status must be positively evidenced. A bare "Science Teacher" with
  no grade band anywhere is dropped rather than guessed at.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from .config import FilterConfig
from .models import Decision, District, JobPosting

# Support staff and non-classroom roles. These are the bulk of every board.
SUPPORT_ROLE_TERMS: tuple[str, ...] = (
    "aide",
    "aides",
    "paraprofessional",
    "paraeducator",
    "para",
    "assistant",
    "clerk",
    "registrar",
    "secretary",
    "custodian",
    "custodial",
    "janitor",
    "nutrition",
    "cook",
    "cooks",
    "driver",
    "drivers",
    "maintenance",
    "laborer",
    "electrician",
    "carpentry",
    "plumber",
    "groundskeeper",
    "technician",
    "rbt",
    "mentor",
    "tutor",
    "coach",
    "supervisor",
    "principal",
    "superintendent",
    "director",
    "coordinator",
    "facilitator",
    "specialist",
    "pathologist",
    "psychologist",
    "nurse",
    "counselor",
    "counseling",
    "worker",
    "advocate",
    "internship",
    "lead",
    "stipend",
)

# Special education and related student-services roles.
SPECIAL_ED_TERMS: tuple[str, ...] = (
    "special education",
    "special ed",
    "sped",
    "spec ed",
    "mild/moderate",
    "life skills",
    "complex support needs",
    "behavior",
    "behavioral",
    "resource",
    "sel",
    "social emotional",
    "social-emotional",
    "autism",
    "deaf",
    "blind",
    "speech",
    "intervention",
    "interventionist",
)

# Grade bands that are not elementary.
NON_ELEMENTARY_TERMS: tuple[str, ...] = (
    "high school",
    "highschool",
    "jr high",
    "jr. high",
    "junior high",
    "middle school",
    "middle",
    "secondary",
    "post-secondary",
    "7th",
    "8th",
    "9th",
    "10th",
    "11th",
    "12th",
    "7-12",
    "9-12",
    "6-12",
    "adult",
    "adult education",
    "college",
    "university",
    "online",
)

SUBSTITUTE_TERMS: tuple[str, ...] = ("substitute", "sub")
TEMPORARY_TERMS: tuple[str, ...] = ("temporary", "temp")
PART_TIME_TERMS: tuple[str, ...] = ("pt", "part-time", "part time", "parttime", "half-time")
KINDERGARTEN_TERMS: tuple[str, ...] = ("kindergarten", "kinder")
PRESCHOOL_TERMS: tuple[str, ...] = ("preschool", "pre-school", "pre-k", "prek", "pre k")
IMMERSION_TERMS: tuple[str, ...] = ("immersion", "dli", "dual language", "dual-language")
SPECIALIST_TERMS: tuple[str, ...] = (
    "music",
    "band",
    "orchestra",
    "choir",
    "art",
    "physical education",
    "pe",
    "p.e.",
    "library",
    "librarian",
    "media",
    "stem",
    "computer science",
)

TEACHER_TERMS: tuple[str, ...] = ("teacher", "teachers")
ELEMENTARY_TERMS: tuple[str, ...] = ("elementary", "primary", "intermediate")

# "3rd Grade", "Fourth Grade", "K-6".
_GRADE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"(?:1st|2nd|3rd|4th|5th|6th|first|second|third|fourth|fifth|sixth)\s+grade"
    r"|k\s*-\s*(?:3|5|6|8)"
    r")"
)

# Ogden tags support-professional postings [ESP####] and licensed ones [LIC####].
_OGDEN_SUPPORT_RE = re.compile(r"\[esp\d+\]")

DAVIS_LICENSED_CATEGORY = "LICENSED EDUCATOR"


def _find(text: str, terms: Iterable[str]) -> str | None:
    """Return the first term present in ``text`` as a whole token, else None.

    Lookarounds rather than ``\\b`` so terms containing punctuation
    ("mild/moderate", "pre-k") still match, and so "PT" does not fire inside
    "Adaptive".
    """
    for term in terms:
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text):
            return term
    return None


def _is_part_time(job: JobPosting) -> str | None:
    if job.job_type and "part" in job.job_type.lower():
        return job.job_type
    return _find(job.search_text, PART_TIME_TERMS)


def classify(job: JobPosting, config: FilterConfig) -> Decision:
    """Judge one posting, carrying the reason for the verdict."""
    text = job.search_text

    def no(reason: str) -> Decision:
        return Decision(posting=job, qualifies=False, reason=reason)

    # Davis labels every posting; the category is authoritative there.
    if job.district is District.DAVIS and job.category:
        if job.category.strip().upper() != DAVIS_LICENSED_CATEGORY:
            return no(f"Davis category {job.category.lower()!r} is not a licensed educator posting")

    # Ogden's [ESP####] tag marks education support professionals.
    if _OGDEN_SUPPORT_RE.search(text):
        return no("tagged [ESP] - education support professional, not a licensed teacher")

    if (part_time := _is_part_time(job)) is not None:
        return no(f"not full-time (matched {part_time!r})")

    if (hit := _find(text, SUBSTITUTE_TERMS)) is not None:
        return no(f"substitute position (matched {hit!r})")

    if job.is_internal and not config.include_internal:
        return no("internal-only posting")

    if (hit := _find(text, SUPPORT_ROLE_TERMS)) is not None:
        return no(f"support or non-classroom role (matched {hit!r})")

    if (hit := _find(text, SPECIAL_ED_TERMS)) is not None:
        return no(f"special education or student services role (matched {hit!r})")

    if (hit := _find(text, NON_ELEMENTARY_TERMS)) is not None:
        return no(f"not an elementary grade band (matched {hit!r})")

    if _find(text, TEACHER_TERMS) is None:
        return no("title does not name a teacher position")

    has_elementary = _find(text, ELEMENTARY_TERMS) is not None or _GRADE_RE.search(text) is not None
    has_early_years = (
        _find(text, KINDERGARTEN_TERMS) is not None or _find(text, PRESCHOOL_TERMS) is not None
    )
    if not has_elementary and not has_early_years:
        return no("no elementary grade signal in the title or school name")

    if not config.include_temporary and (hit := _find(text, TEMPORARY_TERMS)) is not None:
        return no(f"temporary position (matched {hit!r})")

    if not config.include_kindergarten and (hit := _find(text, KINDERGARTEN_TERMS)) is not None:
        return no(f"kindergarten excluded by configuration (matched {hit!r})")

    if not config.include_preschool and (hit := _find(text, PRESCHOOL_TERMS)) is not None:
        return no(f"preschool excluded by configuration (matched {hit!r})")

    if not config.include_immersion and (hit := _find(text, IMMERSION_TERMS)) is not None:
        return no(f"dual-language immersion excluded by configuration (matched {hit!r})")

    if not config.include_specialists and (hit := _find(text, SPECIALIST_TERMS)) is not None:
        return no(f"specialist role excluded by configuration (matched {hit!r})")

    return Decision(posting=job, qualifies=True, reason="full-time elementary teacher")


def classify_all(jobs: Iterable[JobPosting], config: FilterConfig) -> list[Decision]:
    """Classify every posting, keeping the rejections for auditing."""
    return [classify(job, config) for job in jobs]


def qualifying(jobs: Iterable[JobPosting], config: FilterConfig) -> list[JobPosting]:
    """Just the postings that pass, in the order given."""
    return [d.posting for d in classify_all(jobs, config) if d.qualifies]


def summarise_rejections(decisions: Sequence[Decision]) -> list[str]:
    """One line per rejected posting, for the debug log."""
    return [f"{d.posting.title} -> {d.reason}" for d in decisions if not d.qualifies]
