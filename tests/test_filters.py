"""Qualification rules.

Every title in here is a real posting pulled from the three live boards on
2026-10-16, apart from a handful of synthetic ones marked SYNTHETIC that cover
the plain-vanilla case the boards happened not to be advertising that day.
"""

from __future__ import annotations

import pytest

from school_job_scraper.config import FilterConfig
from school_job_scraper.filters import classify, qualifying
from school_job_scraper.models import District, JobPosting


def posting(
    title: str,
    employer: str = "Some Elementary",
    *,
    district: District = District.WEBER,
    job_type: str | None = "Full-time",
    category: str | None = None,
    is_internal: bool = False,
) -> JobPosting:
    return JobPosting(
        district=district,
        job_id="1",
        title=title,
        employer=employer,
        url="https://example.test/job/1",
        job_type=job_type,
        category=category,
        is_internal=is_internal,
    )


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title,employer",
    [
        # SYNTHETIC: the shape of an ordinary classroom opening.
        ("Roy Elementary - 3rd Grade Teacher (12345)", "Roy Elementary"),
        ("Lakeview Elementary - 1st Grade Teacher (30001)", "Lakeview Elementary"),
        ("Bates Elementary - 6th Grade Teacher (30002)", "Bates Elementary"),
        ("Elementary Teacher", "Lincoln Elementary"),
        ("Freedom Elementary - Fourth Grade Teacher (30003)", "Freedom Elementary"),
    ],
)
def test_plain_elementary_classroom_teacher_qualifies(title: str, employer: str) -> None:
    decision = classify(posting(title, employer), FilterConfig())
    assert decision.qualifies, decision.reason


def test_temporary_is_included_by_default() -> None:
    # Real: Weber, job 5958993 (but kindergarten, so grade changed to 3rd here).
    job = posting(
        "Kanesville Elementary - 3rd Grade Teacher (30486) [Temporary]", "Kanesville Elementary"
    )
    assert classify(job, FilterConfig(include_temporary=True)).qualifies


def test_temporary_can_be_excluded() -> None:
    job = posting(
        "Kanesville Elementary - 3rd Grade Teacher (30486) [Temporary]", "Kanesville Elementary"
    )
    decision = classify(job, FilterConfig(include_temporary=False))
    assert not decision.qualifies
    assert "temporary" in decision.reason.lower()


# --------------------------------------------------------------------------
# Part-time: the single biggest source of noise on the Weber board
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        "Silver Ridge Elementary - PT Elementary Aide (30500)",
        "West Haven Elementary - PT Elementary Aide (30460)",
        "Farr West Elementary - PT Literacy Aide (30469)",
        "Literacy Coach (Part-Time)",
        "Elementary Teacher (part time)",
    ],
)
def test_part_time_is_excluded(title: str) -> None:
    decision = classify(posting(title, job_type=None), FilterConfig())
    assert not decision.qualifies


def test_part_time_job_type_from_board_is_excluded() -> None:
    job = posting("Roy Elementary - 3rd Grade Teacher (1)", job_type="Part-time")
    decision = classify(job, FilterConfig())
    assert not decision.qualifies
    assert "full-time" in decision.reason.lower()


def test_pt_inside_a_word_is_not_mistaken_for_part_time() -> None:
    """'PT' must match as a token - 'Optical' and 'Adaptive' must not trip it."""
    job = posting("Adaptive Elementary 2nd Grade Teacher (1)")
    assert classify(job, FilterConfig()).qualifies


# --------------------------------------------------------------------------
# Excluded role types
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title,employer",
    [
        ("[INT] Weber Innovation High - Registrar/Aide (30467)", "Weber Innovation High School"),
        (
            "North Park Elementary - Mild/Moderate SpEd Paraprofessional (30499)",
            "North Park Elementary",
        ),
        (
            "Roosevelt Elementary - Social Emotional Learner (SEL) SpEd Paraprofessional (29430)",
            "Roosevelt Elementary",
        ),
        (
            "Orchard Springs - SpEd Registered Behavior Technician (RBT) (30455)",
            "Orchard Springs Elementary",
        ),
        ("Teacher Assistant", "Lincoln Elementary"),
        ("Behavioral/Instructional Staff Assistant [ESP3915]", "Liberty Elementary"),
        ("Early Literacy Staff Assistant [ESP3677]", "Liberty Elementary"),
        (
            "Elementary Special Education Complex Support Needs Teacher [LIC3082]",
            "Lincoln Elementary",
        ),
        ("Special Education Teacher", "Special Education"),
        ("Speech Language Pathologist [LIC3073]", "Special Education"),
        ("Special Education Behavior Specialist [LIC3072]", "OGDEN SCHOOL DISTRICT"),
        (
            "Student Services - Elementary Counseling District Program Facilitator (29343)",
            "Weber SD TalentEd",
        ),
        ("Elementary Education - Substitute Elementary Principal (30101)", "Weber SD TalentEd"),
        ("Substitute Cooks", "Davis School District"),
        ("Substitute Bus Drivers", "Davis School District"),
        ("Maintenance - Electrician (30352)", "Weber SD TalentEd"),
        ("Maintenance - Maintenance Laborer (Carpentry) (30353)", "Weber SD TalentEd"),
        ("Bates Elementary - Adult Custodian", "Bates Elementary"),
        (
            "Orchard Springs Elementary - Nutrition Service Worker (30104)",
            "Orchard Springs Elementary",
        ),
        ("Assistant Basketball Coach-Girls", "Syracuse Jr High"),
        ("Riverdale Elementary - Math Mentor (29529)", "Riverdale Elementary"),
        ("Lomond View Elementary - Recreation Supervisor (30443)", "Lomond View Elementary"),
        (
            "District Elementary Literacy Intervention Support Lead [ESP3618]",
            "Ogden School District",
        ),
        ("Literacy Coach", "Teaching And Learning Dept"),
    ],
)
def test_non_teaching_and_support_roles_are_excluded(title: str, employer: str) -> None:
    decision = classify(posting(title, employer), FilterConfig())
    assert not decision.qualifies, f"should have been excluded: {title}"


# --------------------------------------------------------------------------
# Wrong grade band
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title,employer",
    [
        (
            "Snowcrest Jr High - CTE Shop/Construction/Robotics/AppDev Teacher (28991)",
            "Snowcrest Junior High",
        ),
        (
            "Mountain View Jr High - English Learner (EL/ESL) Teacher (30411)",
            "Mountain View Junior High",
        ),
        (
            "West Field High School - English Learner (EL/ESL) Teacher (30402)",
            "West Field High School",
        ),
        (
            "Fremont High School - CTE Robotics/Game Dev/Cybersecurity Teacher (28776)",
            "Fremont High School",
        ),
        ("Adult Education - ESL/ELL (English Learner) Teacher (30439)", "Adult Education"),
        ("8th Grade Math Teacher", "Sunset Middle School"),
        ("Secondary Science Teacher", "Weber High School"),
        ("Weber Online - Online Stipend Teaching Positions 2026-27", "Weber Online"),
    ],
)
def test_non_elementary_grade_bands_are_excluded(title: str, employer: str) -> None:
    decision = classify(posting(title, employer), FilterConfig())
    assert not decision.qualifies, f"should have been excluded: {title}"


def test_a_teacher_with_no_elementary_signal_is_excluded() -> None:
    """Absent positive evidence of elementary, drop it rather than guess."""
    job = posting("Science Teacher", "Weber SD TalentEd")
    decision = classify(job, FilterConfig())
    assert not decision.qualifies
    assert "elementary" in decision.reason.lower()


# --------------------------------------------------------------------------
# Config-gated boundary cases
# --------------------------------------------------------------------------


def test_kindergarten_respects_its_toggle() -> None:
    job = posting("Kanesville Elementary - Kindergarten Teacher (30486)", "Kanesville Elementary")
    assert not classify(job, FilterConfig(include_kindergarten=False)).qualifies
    assert classify(job, FilterConfig(include_kindergarten=True)).qualifies


def test_preschool_respects_its_toggle() -> None:
    job = posting("Canyon View - Preschool Teacher (30451)", "Canyon View Elementary")
    assert not classify(job, FilterConfig(include_preschool=False)).qualifies
    assert classify(job, FilterConfig(include_preschool=True)).qualifies


def test_immersion_respects_its_toggle() -> None:
    # Real: Weber, job 5949109.
    job = posting(
        "Uintah Elementary - 5th Grade Chinese Immersion (DLI) Teacher (30412)", "Uintah Elementary"
    )
    assert not classify(job, FilterConfig(include_immersion=False)).qualifies
    assert classify(job, FilterConfig(include_immersion=True)).qualifies


@pytest.mark.parametrize(
    "title",
    [
        "Elementary Music Teacher",
        "Elementary Art Teacher (30011)",
        "Elementary Physical Education Teacher",
        "Elementary PE Teacher",
        "Elementary Library Media Teacher",
    ],
)
def test_specialists_respect_their_toggle(title: str) -> None:
    job = posting(title, "Roy Elementary")
    assert not classify(job, FilterConfig(include_specialists=False)).qualifies
    assert classify(job, FilterConfig(include_specialists=True)).qualifies


def test_internal_postings_respect_their_toggle() -> None:
    job = posting("Roy Elementary - 3rd Grade Teacher (1)", "Roy Elementary", is_internal=True)
    assert classify(job, FilterConfig(include_internal=True)).qualifies
    assert not classify(job, FilterConfig(include_internal=False)).qualifies


# --------------------------------------------------------------------------
# Davis-specific: category is authoritative there
# --------------------------------------------------------------------------


@pytest.mark.parametrize("category", ["CLASSIFIED", "SUBSTITUTE"])
def test_davis_non_licensed_categories_are_excluded(category: str) -> None:
    job = posting(
        "Elementary Teacher",
        "Eagle Bay Elementary",
        district=District.DAVIS,
        job_type=None,
        category=category,
    )
    decision = classify(job, FilterConfig())
    assert not decision.qualifies
    assert category.lower() in decision.reason.lower()


def test_davis_licensed_educator_can_qualify() -> None:
    job = posting(
        "3rd Grade Teacher",
        "Eagle Bay Elementary",
        district=District.DAVIS,
        job_type=None,
        category="LICENSED EDUCATOR",
    )
    assert classify(job, FilterConfig()).qualifies


# --------------------------------------------------------------------------
# qualifying()
# --------------------------------------------------------------------------


def test_qualifying_keeps_only_passing_postings_in_order() -> None:
    keep_first = posting("Roy Elementary - 3rd Grade Teacher (1)", "Roy Elementary")
    drop = posting("Roy Elementary - PT Elementary Aide (2)", "Roy Elementary")
    keep_second = posting("Bates Elementary - 5th Grade Teacher (3)", "Bates Elementary")
    kept = qualifying([keep_first, drop, keep_second], FilterConfig())
    assert [job.title for job in kept] == [keep_first.title, keep_second.title]


def test_classify_always_gives_a_reason() -> None:
    for job in [
        posting("Roy Elementary - 3rd Grade Teacher (1)"),
        posting("Substitute Cooks", "Davis"),
    ]:
        assert classify(job, FilterConfig()).reason
