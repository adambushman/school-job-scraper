"""Davis School District (dsdjobs.net).

An Angular app backed by an unauthenticated JSON endpoint at ``/Jobs/GetList``.
Note the endpoint sits at the site root, not under ``/api`` - that path
redirects to an error page.

Davis differs from the SchoolSpring boards in two ways that matter:

* It publishes no full-time/part-time field at all, so that has to be inferred
  from the title ("Literacy Coach (Part-Time)").
* It does categorise every posting as LICENSED EDUCATOR, CLASSIFIED or
  SUBSTITUTE, which is a stronger signal than anything in the title.
"""

from __future__ import annotations

from typing import Any

from ..models import District, JobPosting
from .base import JsonFetcher, extract_summary, parse_close_date, parse_date

SITE_ROOT = "https://dsdjobs.net"
# The board caps page size at 50 regardless of what is requested.
PAGE_SIZE = 50
MAX_PAGES = 20


class DavisSource:
    """The Davis board."""

    district = District.DAVIS

    def __init__(self, fetch: JsonFetcher) -> None:
        self._fetch = fetch

    def list_postings(self) -> list[JobPosting]:
        postings: list[JobPosting] = []
        seen: set[str] = set()
        page = 1
        while page <= MAX_PAGES:
            payload = self._fetch(f"{SITE_ROOT}/Jobs/GetList?page={page}&pageSize={PAGE_SIZE}")
            rows = _rows(payload)
            if not rows:
                break
            for row in rows:
                if row.get("id") is None:
                    continue
                job = self._to_posting(row)
                if job.job_id in seen:
                    continue
                seen.add(job.job_id)
                postings.append(job)

            total = _total(payload)
            if total is None or len(seen) >= total:
                break
            page += 1
        return postings

    def _to_posting(self, row: dict[str, Any]) -> JobPosting:
        job_id = str(row["id"])
        category = row.get("category")
        return JobPosting(
            district=self.district,
            job_id=job_id,
            title=str(row.get("title") or "").strip(),
            employer=str(row.get("location") or "").strip(),
            url=f"{SITE_ROOT}/announcement/{job_id}",
            job_type=None,  # Davis never provides one.
            category=str(category).strip() if category else None,
            close_date=parse_close_date(row.get("closingDate")),
            is_internal=bool(row.get("inHouse")),
        )

    def enrich(self, job: JobPosting) -> JobPosting:
        payload = self._fetch(f"{SITE_ROOT}/Jobs/GetDetail/{job.job_id}")
        data = payload.get("Data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return job
        description = extract_summary(data.get("description")) or extract_summary(
            data.get("summary")
        )
        return JobPosting(
            district=job.district,
            job_id=job.job_id,
            title=job.title,
            employer=job.employer,
            url=job.url,
            job_type=job.job_type,
            category=job.category or (str(data["category"]) if data.get("category") else None),
            description=description,
            posted_date=job.posted_date or parse_date(data.get("openDate")),
            close_date=job.close_date or parse_close_date(data.get("closeDate")),
            is_internal=job.is_internal or bool(data.get("inHouse")),
        )


def _rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("announcements")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _total(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    total = payload.get("total")
    return total if isinstance(total, int) else None
