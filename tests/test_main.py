"""CLI wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from school_job_scraper.main import build_sources, load_env_file, parse_args
from school_job_scraper.models import District


def test_builds_all_three_boards() -> None:
    sources = build_sources(lambda url: {})
    assert [source.district for source in sources] == [
        District.WEBER,
        District.DAVIS,
        District.OGDEN,
    ]


def test_env_file_is_loaded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    env = tmp_path / ".env"
    env.write_text('# a comment\nSMTP_USERNAME="me@gmail.com"\n\nINCLUDE_IMMERSION=true\n')
    load_env_file(env)
    import os

    assert os.environ["SMTP_USERNAME"] == "me@gmail.com"
    assert os.environ["INCLUDE_IMMERSION"] == "true"


def test_existing_environment_wins_over_the_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SMTP_USERNAME", "real@gmail.com")
    env = tmp_path / ".env"
    env.write_text("SMTP_USERNAME=file@gmail.com\n")
    load_env_file(env)
    import os

    assert os.environ["SMTP_USERNAME"] == "real@gmail.com"


def test_missing_env_file_is_not_an_error(tmp_path: Path) -> None:
    load_env_file(tmp_path / "nope.env")


def test_dry_run_flag_parses() -> None:
    assert parse_args(["--dry-run"]).dry_run
    assert not parse_args([]).dry_run
