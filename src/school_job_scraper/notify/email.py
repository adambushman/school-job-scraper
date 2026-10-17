"""Gmail SMTP delivery.

Gmail needs an App Password (https://myaccount.google.com/apppasswords) rather
than the account password, and the account must have 2-Step Verification on.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any, Callable

from ..config import EmailConfig

logger = logging.getLogger(__name__)

SmtpFactory = Callable[..., Any]


class SmtpNotifier:
    """Sends one multipart/alternative message per run."""

    def __init__(self, config: EmailConfig, smtp_factory: SmtpFactory = smtplib.SMTP) -> None:
        self._config = config
        self._smtp_factory = smtp_factory

    def send(self, subject: str, text_body: str, html_body: str) -> None:
        message = self._build(subject, text_body, html_body)
        config = self._config
        logger.info("sending %r to %d recipient(s)", subject, len(config.recipients))
        # The context manager guarantees QUIT even when send_message raises.
        with self._smtp_factory(config.host, config.port, timeout=30.0) as server:
            server.starttls()
            server.login(config.username, config.password)
            server.send_message(message)

    def _build(self, subject: str, text_body: str, html_body: str) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._config.sender
        message["To"] = ", ".join(self._config.recipients)
        # set_content then add_alternative yields text/plain first, which is the
        # order multipart/alternative requires.
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")
        return message
