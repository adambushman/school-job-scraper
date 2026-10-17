"""The daily scan.

Filtering happens twice on purpose. The board listings carry only a title,
school and date, which is enough to reject the overwhelming majority of
postings (120 of Weber's 129 on a typical day) without a second request. Only
the handful that survive are looked up in detail, and the authoritative
job type that comes back can still overturn the earlier pass - a title with no
"PT" marker sometimes turns out to be part-time.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .config import AppConfig
from .filters import classify
from .models import Decision, JobPosting
from .sources.base import JobSource

logger = logging.getLogger(__name__)

# Order districts the way the email reads best, independent of scan order.
_DISTRICT_ORDER = ("Weber School District", "Davis School District", "Ogden School District")


@dataclass(frozen=True)
class ScanResult:
    """What one run found."""

    postings: list[JobPosting] = field(default_factory=list)
    rejections: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    scanned: int = 0

    @property
    def found_any(self) -> bool:
        return bool(self.postings)


def scan(sources: Iterable[JobSource], config: AppConfig) -> ScanResult:
    """Scan every board and return the postings that qualify."""
    postings: list[JobPosting] = []
    rejections: list[str] = []
    errors: list[str] = []
    scanned = 0
    detail_budget = config.max_detail_lookups

    for source in sources:
        district = source.district.value
        try:
            listed = source.list_postings()
        except Exception as exc:  # one board being down must not lose the rest
            logger.warning("%s: listing failed: %s", district, exc)
            errors.append(f"{district}: could not read the job board ({exc})")
            continue

        scanned += len(listed)
        logger.info("%s: %d postings listed", district, len(listed))

        for job in listed:
            first_pass = classify(job, config.filters)
            if not first_pass.qualifies:
                rejections.append(_describe(first_pass))
                continue

            if detail_budget <= 0:
                logger.warning(
                    "detail lookup budget exhausted; reporting %s unconfirmed", job.job_id
                )
                postings.append(job)
                continue

            detail_budget -= 1
            confirmed = _confirm(source, job, config, errors, rejections)
            if confirmed is None:
                continue
            postings.append(confirmed)

    postings.sort(key=_sort_key)
    return ScanResult(postings=postings, rejections=rejections, errors=errors, scanned=scanned)


def _confirm(
    source: JobSource,
    job: JobPosting,
    config: AppConfig,
    errors: list[str],
    rejections: list[str],
) -> JobPosting | None:
    """Re-check a candidate against its detail record."""
    try:
        enriched = source.enrich(job)
    except Exception as exc:
        # Report it rather than drop it: a posting we cannot confirm is better
        # surfaced to a human than silently discarded.
        logger.warning(
            "%s: detail lookup failed for %s: %s", source.district.value, job.job_id, exc
        )
        errors.append(f"{source.district.value}: could not confirm {job.title!r} ({exc})")
        return job

    second_pass = classify(enriched, config.filters)
    if second_pass.qualifies:
        return enriched
    logger.info("%s rejected on detail: %s", enriched.title, second_pass.reason)
    rejections.append(_describe(second_pass))
    return None


def _describe(decision: Decision) -> str:
    return f"[{decision.posting.district.value}] {decision.posting.title} - {decision.reason}"


def _sort_key(job: JobPosting) -> tuple[int, str]:
    try:
        rank = _DISTRICT_ORDER.index(job.district.value)
    except ValueError:
        rank = len(_DISTRICT_ORDER)
    return rank, job.title.lower()


def summarise(result: ScanResult) -> str:
    """A one-line summary for the log."""
    return (
        f"{len(result.postings)} qualifying of {result.scanned} scanned; "
        f"{len(result.errors)} error(s)"
    )
