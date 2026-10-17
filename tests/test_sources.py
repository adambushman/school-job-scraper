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


# --------------------------------------------------------------------------
# Description summaries: skip the boilerplate, keep the prose
# --------------------------------------------------------------------------


def test_summary_skips_weber_contract_boilerplate() -> None:
    """Weber front-loads payroll metadata before any prose about the job."""
    from school_job_scraper.sources.base import extract_summary

    raw = load("schoolspring_weber_detail.json")["value"]["jobInfo"]["jobDescription"]
    summary = extract_summary(raw) or ""

    # The label/value preamble must be gone...
    assert not summary.startswith("Title:")
    for boilerplate in ("182 Days", "FLSA Status", "Benefits-Eligible", "Salary Schedule"):
        assert boilerplate not in summary, f"{boilerplate!r} is boilerplate"
    # ...and the first thing a reader actually needs must lead.
    assert summary.startswith("Candidates must be fluent in Chinese")


def test_summary_drops_the_application_process_note() -> None:
    """'Application Note: ...' is process boilerplate repeated on every posting."""
    from school_job_scraper.sources.base import extract_summary

    raw = load("schoolspring_weber_detail.json")["value"]["jobInfo"]["jobDescription"]
    assert "minimum of five working days" not in (extract_summary(raw) or "")


def test_summary_keeps_davis_plain_text_prose() -> None:
    """Davis sends plain text in blank-line-separated blocks, not HTML."""
    from school_job_scraper.sources.base import extract_summary

    raw = load("davis_detail.json")["Data"]["description"]
    summary = extract_summary(raw) or ""
    assert "BASKETBALL" in summary.upper()
    assert "Looking for an individual" in summary


def test_summary_keeps_prose_that_merely_contains_a_colon() -> None:
    """A long lead-in ending in a colon is prose, not a metadata label."""
    from school_job_scraper.sources.base import extract_summary

    raw = "The following position is available at Syracuse Junior High:\n\nReal detail here."
    summary = extract_summary(raw) or ""
    assert summary.startswith("The following position is available")


def test_summary_falls_back_when_everything_looks_like_metadata() -> None:
    """Better to show the labels than to show nothing at all."""
    from school_job_scraper.sources.base import extract_summary

    raw = "<p><strong>Title:</strong> Elementary Teacher</p><p><strong>Hours:</strong> 8.0</p>"
    summary = extract_summary(raw) or ""
    assert "Elementary Teacher" in summary


def test_summary_handles_missing_and_empty_descriptions() -> None:
    from school_job_scraper.sources.base import extract_summary

    assert extract_summary(None) is None
    assert extract_summary("") is None
    assert extract_summary("<p>&nbsp;</p>\r\n<hr />") is None


def test_enrich_uses_the_summary_not_the_raw_dump() -> None:
    source = SchoolSpringSource(
        district=District.WEBER,
        domain="wsd.schoolspring.com",
        fetch=fetcher_for(
            {
                "GetPagedJobsWithSearch": load("schoolspring_wsd_list.json"),
                "/api/Jobs/5958993": load("schoolspring_weber_detail.json"),
            }
        ),
    )
    job = next(j for j in source.list_postings() if j.job_id == "5958993")
    enriched = source.enrich(job)
    assert (enriched.description or "").startswith("Candidates must be fluent")
    # The 2050-01-01 sentinel must still be discarded.
    assert enriched.close_date is None


def test_summary_skips_weber_standing_notes_and_section_headings() -> None:
    """Weber repeats the same process note, policy note and EEO notice verbatim.

    On this posting the "Application Note:" label carries an inline value, so
    the standing note that follows is not swallowed as a label value the way it
    is on other postings - it has to be recognised on its own.
    """
    from school_job_scraper.sources.base import extract_summary

    raw = load("schoolspring_weber_temp_detail.json")["value"]["jobInfo"]["jobDescription"]
    summary = extract_summary(raw) or ""

    assert summary.startswith("Under the direction of the school principal")
    for standing in (
        "will remain open until filled",
        "In accordance with Weber School District Policy",
        "has the right to revise this position description",
        "EQUAL OPPORTUNITY",
    ):
        assert standing not in summary, f"{standing!r} is standing boilerplate"
    assert not summary.startswith("Job Overview")


def test_summary_keeps_section_headings_that_are_not_boilerplate() -> None:
    """Only the known section headings are dropped, not any short line."""
    from school_job_scraper.sources.base import extract_summary

    raw = "ASSISTANT GIRLS BASKETBALL COACH\n\nLooking for someone with experience."
    assert "BASKETBALL" in (extract_summary(raw) or "")
