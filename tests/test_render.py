"""Email subject and bodies."""

from __future__ import annotations

from datetime import date

from school_job_scraper.models import District, JobPosting
from school_job_scraper.pipeline import ScanResult
from school_job_scraper.render import render_html, render_subject, render_text


def job(
    title: str = "Roy Elementary - 3rd Grade Teacher (30001)",
    *,
    district: District = District.WEBER,
    employer: str = "Roy Elementary",
    job_id: str = "1",
    close_date: date | None = None,
    is_internal: bool = False,
    description: str | None = None,
) -> JobPosting:
    return JobPosting(
        district=district,
        job_id=job_id,
        title=title,
        employer=employer,
        url=f"https://wsd.schoolspring.com/jobdetail?jobId={job_id}",
        job_type="Full-time",
        close_date=close_date,
        is_internal=is_internal,
        description=description,
    )


def test_subject_counts_the_openings() -> None:
    result = ScanResult(postings=[job(job_id="1"), job(job_id="2")], scanned=200)
    subject = render_subject(result)
    assert "2" in subject
    assert "elementary" in subject.lower()


def test_subject_is_singular_for_one_opening() -> None:
    subject = render_subject(ScanResult(postings=[job()], scanned=200))
    assert "1 full-time elementary teacher opening" in subject
    assert "openings" not in subject


def test_subject_says_so_when_nothing_qualifies() -> None:
    subject = render_subject(ScanResult(postings=[], scanned=200))
    assert "no" in subject.lower()


def test_text_body_lists_every_posting_with_its_link() -> None:
    postings = [
        job(job_id="1", title="Roy Elementary - 3rd Grade Teacher (30001)"),
        job(job_id="2", title="Bates Elementary - 5th Grade Teacher (30002)"),
    ]
    body = render_text(ScanResult(postings=postings, scanned=200))
    for posting in postings:
        assert posting.title in body
        assert posting.url in body


def test_text_body_groups_by_district() -> None:
    postings = [
        job(job_id="1", district=District.WEBER),
        job(
            job_id="2",
            district=District.DAVIS,
            title="3rd Grade Teacher",
            employer="Eagle Bay Elementary",
        ),
    ]
    body = render_text(ScanResult(postings=postings, scanned=200))
    assert "Weber School District" in body
    assert "Davis School District" in body
    assert body.index("Weber School District") < body.index("Davis School District")


def test_bodies_label_internal_postings() -> None:
    result = ScanResult(postings=[job(is_internal=True)], scanned=10)
    assert "internal" in render_text(result).lower()
    assert "internal" in render_html(result).lower()


def test_bodies_do_not_label_public_postings_as_internal() -> None:
    result = ScanResult(postings=[job(is_internal=False)], scanned=10)
    assert "internal" not in render_text(result).lower()


def test_text_body_shows_the_closing_date_when_known() -> None:
    body = render_text(ScanResult(postings=[job(close_date=date(2026, 10, 24))], scanned=10))
    assert "Oct" in body and "24" in body


def test_bodies_report_board_errors() -> None:
    result = ScanResult(
        postings=[job()],
        errors=["Ogden School District: could not read the job board (timeout)"],
        scanned=10,
    )
    assert "Ogden" in render_text(result)
    assert "Ogden" in render_html(result)


def test_empty_result_body_is_still_informative() -> None:
    body = render_text(ScanResult(postings=[], scanned=202))
    assert "202" in body


def test_html_body_links_are_anchors() -> None:
    posting = job(job_id="42")
    html = render_html(ScanResult(postings=[posting], scanned=10))
    assert f'href="{posting.url}"' in html
    assert "<html" in html.lower()


def test_html_escapes_posting_text() -> None:
    posting = job(title="Roy Elementary - Grade 3 <script>alert(1)</script> Teacher")
    html = render_html(ScanResult(postings=[posting], scanned=10))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_description_is_truncated_rather_than_dumped() -> None:
    posting = job(description="word " * 400)
    body = render_text(ScanResult(postings=[posting], scanned=10))
    assert len(body) < 3000


# --------------------------------------------------------------------------
# Closing dates
# --------------------------------------------------------------------------


def test_bodies_say_open_until_filled_when_there_is_no_closing_date() -> None:
    result = ScanResult(postings=[job(close_date=None)], scanned=10)
    assert "Open until filled" in render_text(result)
    assert "Open until filled" in render_html(result)


def test_bodies_prefer_a_real_closing_date_over_the_label() -> None:
    result = ScanResult(postings=[job(close_date=date(2026, 10, 30))], scanned=10)
    text = render_text(result)
    assert "Oct 30, 2026" in text
    assert "Open until filled" not in text
