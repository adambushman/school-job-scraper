"""Parsers for the three boards, driven by payloads captured live on 2026-10-16."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from school_job_scraper.models import District
from school_job_scraper.sources.davis import DavisSource
from school_job_scraper.sources.schoolspring import SchoolSpringSource

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def fetcher_for(mapping: dict[str, Any]) -> Any:
    """A JSON fetcher that matches on a substring of the requested URL."""
    calls: list[str] = []

    def fetch(url: str) -> Any:
        calls.append(url)
        for fragment, payload in mapping.items():
            if fragment in url:
                return payload
        raise AssertionError(f"unexpected URL requested: {url}")

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


# --------------------------------------------------------------------------
# SchoolSpring (Weber and Ogden)
# --------------------------------------------------------------------------


def test_schoolspring_parses_the_live_weber_payload() -> None:
    source = SchoolSpringSource(
        district=District.WEBER,
        domain="wsd.schoolspring.com",
        fetch=fetcher_for({"GetPagedJobsWithSearch": load("schoolspring_wsd_list.json")}),
    )
    jobs = source.list_postings()

    assert jobs, "expected postings from the Weber fixture"
    kindergarten = next(j for j in jobs if "Kindergarten" in j.title)
    assert kindergarten.district is District.WEBER
    assert kindergarten.job_id == "5958993"
    assert kindergarten.employer == "Kanesville Elementary"
    assert kindergarten.url == "https://wsd.schoolspring.com/jobdetail?jobId=5958993"
    assert kindergarten.posted_date == date(2026, 10, 13)


def test_schoolspring_flags_internal_postings() -> None:
    source = SchoolSpringSource(
        district=District.WEBER,
        domain="wsd.schoolspring.com",
        fetch=fetcher_for({"GetPagedJobsWithSearch": load("schoolspring_wsd_list.json")}),
    )
    jobs = {job.title: job for job in source.list_postings()}
    internal = next(job for title, job in jobs.items() if title.startswith("[INT]"))
    assert internal.is_internal
    public = next(job for title, job in jobs.items() if not title.startswith("[INT]"))
    assert not public.is_internal


def test_schoolspring_requests_full_board_not_a_prefiltered_slice() -> None:
    """We filter locally.

    The board's own ``jobtype`` filter relies on metadata the districts do not
    always populate, so trusting it would silently drop postings.
    """
    fetch = fetcher_for({"GetPagedJobsWithSearch": load("schoolspring_wsd_list.json")})
    SchoolSpringSource(
        district=District.WEBER, domain="wsd.schoolspring.com", fetch=fetch
    ).list_postings()
    url = fetch.calls[0]
    assert "jobtype=&" in url or url.endswith("jobtype=")
    assert "domainName=wsd.schoolspring.com" in url, "the short domain form returns zero results"


def test_schoolspring_enrich_adds_the_authoritative_job_type() -> None:
    source = SchoolSpringSource(
        district=District.OGDEN,
        domain="ogdensd.schoolspring.com",
        fetch=fetcher_for(
            {
                "GetPagedJobsWithSearch": load("schoolspring_ogden_list.json"),
                "/api/Jobs/5960278": load("schoolspring_detail.json"),
            }
        ),
    )
    job = next(j for j in source.list_postings() if j.job_id == "5960278")
    assert job.job_type is None

    enriched = source.enrich(job)
    assert enriched.job_type == "Full-time"
    assert enriched.close_date == date(2026, 10, 24)
    assert enriched.description is not None
    assert "cognitive disabilities" in enriched.description
    # Identity and the public link must survive enrichment.
    assert enriched.job_id == job.job_id
    assert enriched.url == job.url


def test_schoolspring_enrich_survives_a_missing_detail_record() -> None:
    source = SchoolSpringSource(
        district=District.OGDEN,
        domain="ogdensd.schoolspring.com",
        fetch=fetcher_for(
            {
                "GetPagedJobsWithSearch": load("schoolspring_ogden_list.json"),
                "/api/Jobs/": {"success": False, "message": "nope", "value": None},
            }
        ),
    )
    job = source.list_postings()[0]
    assert source.enrich(job) == job


def test_schoolspring_strips_html_from_descriptions() -> None:
    source = SchoolSpringSource(
        district=District.OGDEN,
        domain="ogdensd.schoolspring.com",
        fetch=fetcher_for(
            {
                "GetPagedJobsWithSearch": load("schoolspring_ogden_list.json"),
                "/api/Jobs/5960278": load("schoolspring_detail.json"),
            }
        ),
    )
    job = next(j for j in source.list_postings() if j.job_id == "5960278")
    description = source.enrich(job).description or ""
    assert "<p>" not in description and "&nbsp;" not in description


# --------------------------------------------------------------------------
# Davis
# --------------------------------------------------------------------------


def test_davis_parses_the_live_payload() -> None:
    source = DavisSource(fetch=fetcher_for({"Jobs/GetList": load("davis_list.json")}))
    jobs = source.list_postings()

    assert jobs
    sped = next(j for j in jobs if j.title == "Special Education Teacher")
    assert sped.district is District.DAVIS
    assert sped.category == "LICENSED EDUCATOR"
    assert sped.url == f"https://dsdjobs.net/announcement/{sped.job_id}"
    assert sped.job_type is None, "Davis publishes no full-time flag"


def test_davis_follows_pagination() -> None:
    """The live board reports 57 results but caps pageSize at 50."""
    page_one = load("davis_list.json")
    assert page_one["total"] > len(page_one["announcements"]), "fixture must be a partial page"

    page_two = {
        "total": page_one["total"],
        "page": 2,
        "pageSize": 50,
        "announcements": [
            {
                "id": 99001,
                "title": "2nd Grade Teacher",
                "category": "LICENSED EDUCATOR",
                "location": "Eagle Bay Elementary",
                "closingDate": None,
                "count": 0,
                "inHouse": False,
            }
        ],
    }

    def fetch(url: str) -> Any:
        return page_two if "page=2" in url else page_one

    jobs = DavisSource(fetch=fetch).list_postings()
    assert any(job.job_id == "99001" for job in jobs), "second page was not fetched"
    assert len({job.job_id for job in jobs}) == len(jobs), "pagination produced duplicates"


def test_davis_flags_in_house_postings_as_internal() -> None:
    payload = {
        "total": 1,
        "page": 1,
        "pageSize": 50,
        "announcements": [
            {
                "id": 1,
                "title": "3rd Grade Teacher",
                "category": "LICENSED EDUCATOR",
                "location": "Eagle Bay Elementary",
                "closingDate": "2026-11-01T00:00:00-06:00",
                "count": 0,
                "inHouse": True,
            }
        ],
    }
    job = DavisSource(fetch=lambda url: payload).list_postings()[0]
    assert job.is_internal
    assert job.close_date == date(2026, 11, 1)


def test_davis_enrich_adds_description() -> None:
    source = DavisSource(
        fetch=fetcher_for(
            {
                "Jobs/GetList": load("davis_list.json"),
                "Jobs/GetDetail/28629": load("davis_detail.json"),
            }
        )
    )
    job = next(j for j in source.list_postings() if j.job_id == "28629")
    enriched = source.enrich(job)
    assert enriched.description is not None
    assert "BASKETBALL" in enriched.description.upper()


@pytest.mark.parametrize("bad", [{}, {"announcements": None}, {"announcements": []}])
def test_davis_tolerates_empty_or_malformed_payloads(bad: dict[str, Any]) -> None:
    assert DavisSource(fetch=lambda url: bad).list_postings() == []


# --------------------------------------------------------------------------
# Sentinel closing dates
# --------------------------------------------------------------------------


def test_far_future_close_dates_are_treated_as_open_until_filled() -> None:
    """Weber posts 'open until filled' roles with a 2050-01-01 close date."""
    from school_job_scraper.sources.base import parse_close_date

    assert parse_close_date("2050-01-01T06:00:00") is None
    assert parse_close_date("2026-10-24T05:59:00") == date(2026, 10, 24)
    assert parse_close_date(None) is None
