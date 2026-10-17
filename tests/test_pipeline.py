"""The two-stage scan: cheap title filter, then confirm against job detail."""

from __future__ import annotations

from school_job_scraper.config import AppConfig, FilterConfig
from school_job_scraper.models import District, JobPosting
from school_job_scraper.pipeline import scan


class FakeSource:
    """A board that serves a fixed list and a fixed detail lookup."""

    def __init__(
        self,
        district: District,
        postings: list[JobPosting],
        detail: dict[str, str] | None = None,
        fail: bool = False,
    ) -> None:
        self.district = district
        self._postings = postings
        self._detail = detail or {}
        self._fail = fail
        self.enrich_calls: list[str] = []

    def list_postings(self) -> list[JobPosting]:
        if self._fail:
            raise RuntimeError("board unreachable")
        return list(self._postings)

    def enrich(self, job: JobPosting) -> JobPosting:
        self.enrich_calls.append(job.job_id)
        job_type = self._detail.get(job.job_id)
        if job_type is None:
            return job
        return JobPosting(
            district=job.district,
            job_id=job.job_id,
            title=job.title,
            employer=job.employer,
            url=job.url,
            job_type=job_type,
            category=job.category,
            description="Detail text.",
            posted_date=job.posted_date,
            close_date=job.close_date,
            is_internal=job.is_internal,
        )


def job(job_id: str, title: str, employer: str = "Roy Elementary") -> JobPosting:
    return JobPosting(
        district=District.WEBER,
        job_id=job_id,
        title=title,
        employer=employer,
        url=f"https://example.test/{job_id}",
    )


def test_scan_returns_only_confirmed_full_time_elementary_teachers() -> None:
    source = FakeSource(
        District.WEBER,
        [
            job("1", "Roy Elementary - 3rd Grade Teacher (1)"),
            job("2", "Roy Elementary - PT Elementary Aide (2)"),
            job("3", "Snowcrest Jr High - Science Teacher (3)", "Snowcrest Junior High"),
        ],
        detail={"1": "Full-time"},
    )
    result = scan([source], AppConfig())
    assert [j.job_id for j in result.postings] == ["1"]
    assert result.scanned == 3


def test_scan_only_looks_up_detail_for_plausible_candidates() -> None:
    """The expensive call must not be made for the 120-odd obvious rejects."""
    source = FakeSource(
        District.WEBER,
        [
            job("1", "Roy Elementary - 3rd Grade Teacher (1)"),
            job("2", "Roy Elementary - PT Elementary Aide (2)"),
            job("3", "Maintenance - Electrician (3)", "Weber SD TalentEd"),
            job("4", "Substitute Cooks (4)", "Weber SD TalentEd"),
        ],
        detail={"1": "Full-time"},
    )
    scan([source], AppConfig())
    assert source.enrich_calls == ["1"]


def test_detail_can_overturn_a_title_level_pass() -> None:
    """A title with no 'PT' marker can still turn out to be part-time."""
    source = FakeSource(
        District.WEBER,
        [job("1", "Roy Elementary - 3rd Grade Teacher (1)")],
        detail={"1": "Part-time"},
    )
    result = scan([source], AppConfig())
    assert result.postings == []
    assert any("part" in reason.lower() for reason in result.rejections)


def test_a_posting_with_no_detail_available_is_still_reported() -> None:
    """Davis never returns a job type; absence must not be read as part-time."""
    davis = FakeSource(
        District.DAVIS,
        [
            JobPosting(
                district=District.DAVIS,
                job_id="7",
                title="3rd Grade Teacher",
                employer="Eagle Bay Elementary",
                url="https://dsdjobs.net/announcement/7",
                category="LICENSED EDUCATOR",
            )
        ],
    )
    result = scan([davis], AppConfig())
    assert [j.job_id for j in result.postings] == ["7"]


def test_one_failing_board_does_not_abort_the_others() -> None:
    broken = FakeSource(District.OGDEN, [], fail=True)
    working = FakeSource(
        District.WEBER,
        [job("1", "Roy Elementary - 3rd Grade Teacher (1)")],
        detail={"1": "Full-time"},
    )
    result = scan([broken, working], AppConfig())
    assert [j.job_id for j in result.postings] == ["1"]
    assert len(result.errors) == 1
    assert "Ogden" in result.errors[0]


def test_detail_lookups_are_capped() -> None:
    many = [job(str(i), f"Roy Elementary - {i % 6 + 1}st Grade Teacher ({i})") for i in range(40)]
    source = FakeSource(District.WEBER, many)
    config = AppConfig(max_detail_lookups=5)
    scan([source], config)
    assert len(source.enrich_calls) == 5


def test_results_are_sorted_by_district_then_title() -> None:
    weber = FakeSource(
        District.WEBER,
        [
            job("2", "Zeta Elementary - 2nd Grade Teacher (2)", "Zeta Elementary"),
            job("1", "Alpha Elementary - 1st Grade Teacher (1)", "Alpha Elementary"),
        ],
        detail={"1": "Full-time", "2": "Full-time"},
    )
    result = scan([weber], AppConfig())
    assert [j.job_id for j in result.postings] == ["1", "2"]


def test_rejections_are_recorded_with_reasons() -> None:
    source = FakeSource(District.WEBER, [job("2", "Roy Elementary - PT Elementary Aide (2)")])
    result = scan([source], AppConfig())
    assert result.rejections
    assert "Elementary Aide" in result.rejections[0]


def test_filter_toggles_are_honoured_end_to_end() -> None:
    postings = [job("1", "Uintah Elementary - 5th Grade Chinese Immersion (DLI) Teacher (1)")]
    detail = {"1": "Full-time"}
    off = scan([FakeSource(District.WEBER, postings, detail)], AppConfig())
    assert off.postings == []
    on = scan(
        [FakeSource(District.WEBER, postings, detail)],
        AppConfig(filters=FilterConfig(include_immersion=True)),
    )
    assert [j.job_id for j in on.postings] == ["1"]
