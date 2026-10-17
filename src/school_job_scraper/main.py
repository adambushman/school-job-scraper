"""Command line entry point, intended to be run once a day from cron."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .config import AppConfig, ConfigError, EmailConfig, FilterConfig
from .http import build_fetcher, default_session
from .models import District, JsonFetcher
from .notify.base import Notifier
from .notify.console import ConsoleNotifier
from .notify.email import SmtpNotifier
from .pipeline import ScanResult, scan, summarise
from .render import render_html, render_subject, render_text
from .sources.base import JobSource
from .sources.davis import DavisSource
from .sources.schoolspring import SchoolSpringSource

logger = logging.getLogger("school_job_scraper")

ENV_FILE = ".env"


def load_env_file(path: Path) -> None:
    """Load ``KEY=value`` lines from a .env file without adding a dependency.

    Values already in the real environment win, so cron or a shell export can
    override the file.
    """
    if not path.is_file():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def build_sources(fetch: JsonFetcher) -> list[JobSource]:
    """The three boards. Weber and Ogden share the SchoolSpring adapter."""
    return [
        SchoolSpringSource(District.WEBER, "wsd.schoolspring.com", fetch),
        DavisSource(fetch),
        SchoolSpringSource(District.OGDEN, "ogdensd.schoolspring.com", fetch),
    ]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="school-job-scraper",
        description=(
            "Scan the Weber, Davis and Ogden school district job boards for full-time "
            "elementary teacher openings and email a summary."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the summary instead of sending it (needs no SMTP settings)",
    )
    parser.add_argument(
        "--show-rejections",
        action="store_true",
        help="list every posting that was filtered out, and why",
    )
    parser.add_argument(
        "--send-when-empty",
        action="store_true",
        help="send an email even when nothing qualifies",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    config = AppConfig(filters=FilterConfig.from_env())
    logger.debug("filters: %s", config.filters)

    session = default_session()
    fetch = build_fetcher(session=session, timeout=config.timeout_seconds)
    result = scan(build_sources(fetch), config)
    logger.info("%s", summarise(result))

    if args.show_rejections:
        for line in result.rejections:
            print(f"  rejected: {line}")

    notifier, send_when_empty = _delivery(args)
    if notifier is None:
        return 1

    if not result.found_any and not send_when_empty:
        logger.info("nothing qualified; no email sent")
        _report_errors(result)
        return 0

    try:
        notifier.send(render_subject(result), render_text(result), render_html(result))
    except Exception as exc:
        logger.error("could not send the summary email: %s", exc)
        return 1

    _report_errors(result)
    return 0


def _delivery(args: argparse.Namespace) -> tuple[Notifier | None, bool]:
    """Pick a backend. Returns ``(None, ...)`` when email is misconfigured."""
    if args.dry_run:
        return ConsoleNotifier(), True
    try:
        email_config = EmailConfig.from_env()
    except ConfigError as exc:
        logger.error("%s", exc)
        return None, False
    return SmtpNotifier(email_config), args.send_when_empty or email_config.send_when_empty


def _report_errors(result: ScanResult) -> None:
    for error in result.errors:
        logger.warning("%s", error)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        stream=sys.stderr,
    )
    load_env_file(Path(ENV_FILE))
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
