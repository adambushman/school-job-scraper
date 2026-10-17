"""The delivery contract."""

from __future__ import annotations

from typing import Protocol


class Notifier(Protocol):
    """Anything that can deliver one rendered summary."""

    def send(self, subject: str, text_body: str, html_body: str) -> None: ...
