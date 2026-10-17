"""Weber and Ogden, both hosted on SchoolSpring (PowerSchool).

The public site is a React app, so there is no HTML to scrape; it reads from
``api.schoolspring.com``, which needs no authentication. Two things about that
API are easy to get wrong:

* ``domainName`` must be the full host ("wsd.schoolspring.com"). The short form
  ("wsd") returns an empty list rather than an error.
* The ``jobtype`` and ``gradelevel`` filters work but depend on metadata the
  districts populate inconsistently - only one of Weber's 129 live postings set
  a grade level. We therefore request the whole board and filter locally.
"""

from __future__ import annotations

from typing import Any

from ..models import District, JobPosting
from .base import JsonFetcher, parse_close_date, parse_date, strip_html

API_ROOT = "https://api.schoolspring.com/api"
PAGE_SIZE = 200

# Weber prefixes employee-only postings with [INT]; both boards use [Internal].
INTERNAL_MARKERS = ("[int]", "[internal]")


class SchoolSpringSource:
    """One SchoolSpring-hosted district board."""

    def __init__(self, district: District, domain: str, fetch: JsonFetcher) -> None:
        self.district = district
        self.domain = domain
        self._fetch = fetch

    # -- listing ---------------------------------------------------------
    def _list_url(self, page: int) -> str:
        # Every parameter must be present even when blank; the API builds its
        # query from a fixed format string and rejects a short one.
        return (
            f"{API_ROOT}/Jobs/GetPagedJobsWithSearch"
            f"?domainName={self.domain}"
            "&keyword=&location=&category=&gradelevel=&jobtype=&organization="
            "&swLat=&swLon=&neLat=&neLon="
            f"&page={page}&size={PAGE_SIZE}&sortDateAscending=false"
        )

    def list_postings(self) -> list[JobPosting]:
        payload = self._fetch(self._list_url(1))
        rows = _job_rows(payload)
        return [self._to_posting(row) for row in rows if row.get("jobId") is not None]

    def _to_posting(self, row: dict[str, Any]) -> JobPosting:
        title = str(row.get("title") or "").strip()
        job_id = str(row["jobId"])
        return JobPosting(
            district=self.district,
            job_id=job_id,
            title=title,
            employer=str(row.get("employer") or "").strip(),
            url=f"https://{self.domain}/jobdetail?jobId={job_id}",
            posted_date=parse_date(row.get("displayDate")),
            is_internal=any(marker in title.lower() for marker in INTERNAL_MARKERS),
        )

    # -- detail ----------------------------------------------------------
    def enrich(self, job: JobPosting) -> JobPosting:
        payload = self._fetch(f"{API_ROOT}/Jobs/{job.job_id}?domainName={self.domain}")
        info = _job_info(payload)
        if not info:
            return job
        job_type = info.get("jobTypeName") or info.get("shiftType")
        return JobPosting(
            district=job.district,
            job_id=job.job_id,
            title=job.title,
            employer=job.employer,
            url=job.url,
            job_type=str(job_type) if job_type else None,
            category=job.category,
            description=strip_html(info.get("jobDescription")),
            posted_date=job.posted_date or parse_date(info.get("displayDate")),
            close_date=parse_close_date(info.get("closeDate") or info.get("applicationDeadline")),
            is_internal=job.is_internal,
        )


def _job_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    value = payload.get("value")
    if not isinstance(value, dict):
        return []
    rows = value.get("jobsList")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _job_info(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    value = payload.get("value")
    if not isinstance(value, dict):
        return {}
    info = value.get("jobInfo")
    return info if isinstance(info, dict) else {}
