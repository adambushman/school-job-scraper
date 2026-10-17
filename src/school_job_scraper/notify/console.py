"""Print the summary instead of mailing it. Used by ``--dry-run``."""

from __future__ import annotations

from collections.abc import Callable


class ConsoleNotifier:
    """Writes the plain-text body to stdout."""

    def __init__(self, write: Callable[[str], None] = print) -> None:
        self._write = write

    def send(self, subject: str, text_body: str, html_body: str) -> None:
        self._write("=" * 70)
        self._write(f"Subject: {subject}")
        self._write("=" * 70)
        self._write(text_body)
