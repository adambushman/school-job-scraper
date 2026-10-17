"""Turn a scan into an email.

Both a plain-text and an HTML body are produced, sent as a multipart/alternative
so it reads correctly in any client. The HTML uses inline styles only, since
most mail clients strip stylesheets.
"""

from __future__ import annotations

import html as html_module
from collections import OrderedDict
from datetime import date

from .models import District, JobPosting
from .pipeline import ScanResult

DESCRIPTION_LIMIT = 240


def _plural(count: int) -> str:
    return "opening" if count == 1 else "openings"


def render_subject(result: ScanResult) -> str:
    count = len(result.postings)
    if count == 0:
        return "No full-time elementary teacher openings today"
    districts = ", ".join(_district_names(result.postings))
    return f"{count} full-time elementary teacher {_plural(count)} ({districts})"


def _district_names(postings: list[JobPosting]) -> list[str]:
    """District short names, in the order they appear."""
    seen: OrderedDict[str, None] = OrderedDict()
    for posting in postings:
        seen.setdefault(_short_name(posting.district), None)
    return list(seen)


def _short_name(district: District) -> str:
    return district.value.replace(" School District", "")


def _grouped(postings: list[JobPosting]) -> OrderedDict[District, list[JobPosting]]:
    groups: OrderedDict[District, list[JobPosting]] = OrderedDict()
    for posting in postings:
        groups.setdefault(posting.district, []).append(posting)
    return groups


def _format_date(value: date) -> str:
    return value.strftime("%b %d, %Y")


def _shorten(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


# --------------------------------------------------------------------------
# Plain text
# --------------------------------------------------------------------------


def render_text(result: ScanResult) -> str:
    lines: list[str] = []

    if not result.postings:
        lines.append("No full-time elementary teacher openings matched today.")
        lines.append("")
        lines.append(f"Scanned {result.scanned} postings across the three district boards.")
    else:
        count = len(result.postings)
        lines.append(
            f"{count} full-time elementary teacher {_plural(count)} "
            f"(scanned {result.scanned} postings)."
        )
        for district, postings in _grouped(result.postings).items():
            lines.append("")
            lines.append(district.value)
            lines.append("-" * len(district.value))
            for posting in postings:
                lines.append("")
                label = " [internal only]" if posting.is_internal else ""
                lines.append(f"* {posting.title}{label}")
                if posting.employer:
                    lines.append(f"  School:  {posting.employer}")
                if posting.close_date:
                    lines.append(f"  Closes:  {_format_date(posting.close_date)}")
                if posting.description:
                    lines.append(f"  {_shorten(posting.description)}")
                lines.append(f"  Apply:   {posting.url}")

    if result.errors:
        lines.append("")
        lines.append("Problems during this run:")
        for error in result.errors:
            lines.append(f"  - {error}")

    lines.append("")
    lines.append("-- ")
    lines.append("Sent by school-job-scraper.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------


def _esc(value: str) -> str:
    return html_module.escape(value, quote=True)


def render_html(result: ScanResult) -> str:
    body: list[str] = []

    if not result.postings:
        body.append(
            '<p style="margin:0 0 16px;">No full-time elementary teacher openings '
            "matched today.</p>"
        )
        body.append(
            f'<p style="margin:0;color:#555;">Scanned {result.scanned} postings across the '
            "three district boards.</p>"
        )
    else:
        count = len(result.postings)
        body.append(
            f'<p style="margin:0 0 20px;">Found <strong>{count}</strong> full-time elementary '
            f"teacher {_plural(count)} (scanned {result.scanned} postings).</p>"
        )
        for district, postings in _grouped(result.postings).items():
            body.append(
                '<h2 style="font-size:16px;margin:24px 0 8px;padding-bottom:4px;'
                f'border-bottom:1px solid #ddd;">{_esc(district.value)}</h2>'
            )
            for posting in postings:
                body.append(_render_posting_html(posting))

    if result.errors:
        items = "".join(f"<li>{_esc(error)}</li>" for error in result.errors)
        body.append(
            '<h2 style="font-size:16px;margin:24px 0 8px;">Problems during this run</h2>'
            f'<ul style="margin:0;color:#8a4b00;">{items}</ul>'
        )

    return (
        "<!doctype html>"
        '<html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "</head>"
        '<body style="margin:0;padding:24px;background:#f6f7f9;'
        "font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
        'font-size:15px;line-height:1.5;color:#1a1a1a;">'
        '<div style="max-width:640px;margin:0 auto;background:#fff;padding:24px;'
        'border-radius:8px;">'
        + "".join(body)
        + '<p style="margin:24px 0 0;padding-top:12px;border-top:1px solid #eee;'
        'color:#888;font-size:12px;">Sent by school-job-scraper.</p>'
        "</div></body></html>"
    )


def _render_posting_html(posting: JobPosting) -> str:
    label = (
        '<span style="display:inline-block;margin-left:6px;padding:1px 6px;font-size:11px;'
        'border-radius:3px;background:#fff3cd;color:#664d03;">internal only</span>'
        if posting.is_internal
        else ""
    )
    meta: list[str] = []
    if posting.employer:
        meta.append(_esc(posting.employer))
    if posting.close_date:
        meta.append(f"closes {_format_date(posting.close_date)}")
    meta_html = (
        f'<div style="color:#555;font-size:13px;margin:2px 0 6px;">{" &middot; ".join(meta)}</div>'
        if meta
        else ""
    )
    description_html = (
        f'<div style="color:#444;margin:0 0 8px;">{_esc(_shorten(posting.description))}</div>'
        if posting.description
        else ""
    )
    return (
        '<div style="margin:0 0 18px;">'
        f'<div style="font-weight:600;">{_esc(posting.title)}{label}</div>'
        f"{meta_html}{description_html}"
        f'<a href="{_esc(posting.url)}" '
        'style="color:#0b5cab;text-decoration:none;font-size:14px;">View posting &rarr;</a>'
        "</div>"
    )
