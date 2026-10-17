"""Email delivery, exercised against a fake SMTP server."""

from __future__ import annotations

import email
from email.message import EmailMessage, Message
from types import TracebackType
from typing import Any

import pytest

from school_job_scraper.config import ConfigError, EmailConfig
from school_job_scraper.notify.console import ConsoleNotifier
from school_job_scraper.notify.email import SmtpNotifier


class FakeSmtp:
    """Stands in for ``smtplib.SMTP``, recording what it was asked to do."""

    instances: list["FakeSmtp"] = []

    def __init__(self, host: str, port: int, timeout: float = 30.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args: tuple[str, str] | None = None
        self.sent: list[EmailMessage] = []
        self.quit_called = False
        FakeSmtp.instances.append(self)

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *exc: object) -> None:
        self.quit_called = True

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def send_message(self, message: EmailMessage) -> None:
        if self.login_args is None:
            raise AssertionError("send attempted before login")
        self.sent.append(message)


@pytest.fixture(autouse=True)
def _reset() -> None:
    FakeSmtp.instances.clear()


def config(**overrides: Any) -> EmailConfig:
    base: dict[str, Any] = {
        "host": "smtp.gmail.com",
        "port": 587,
        "username": "sender@gmail.com",
        "password": "app-password",
        "sender": "sender@gmail.com",
        "recipients": ("a@example.com", "b@example.com"),
    }
    base.update(overrides)
    return EmailConfig(**base)


def test_sends_over_starttls_after_logging_in() -> None:
    SmtpNotifier(config(), smtp_factory=FakeSmtp).send("Subject", "text body", "<p>html</p>")
    server = FakeSmtp.instances[0]
    assert (server.host, server.port) == ("smtp.gmail.com", 587)
    assert server.started_tls, "Gmail on 587 requires STARTTLS"
    assert server.login_args == ("sender@gmail.com", "app-password")
    assert len(server.sent) == 1


def test_message_headers_and_recipients() -> None:
    SmtpNotifier(config(), smtp_factory=FakeSmtp).send("Two openings", "text", "<p>html</p>")
    message = FakeSmtp.instances[0].sent[0]
    assert message["Subject"] == "Two openings"
    assert message["From"] == "sender@gmail.com"
    assert message["To"] == "a@example.com, b@example.com"


def test_message_is_multipart_alternative_with_both_bodies() -> None:
    SmtpNotifier(config(), smtp_factory=FakeSmtp).send("Subject", "PLAIN BODY", "<p>HTML BODY</p>")
    message = FakeSmtp.instances[0].sent[0]
    assert message.get_content_type() == "multipart/alternative"

    parts = {part.get_content_type(): part for part in message.walk() if not part.is_multipart()}
    assert "PLAIN BODY" in parts["text/plain"].get_content()
    assert "HTML BODY" in parts["text/html"].get_content()


def test_plain_text_part_comes_first() -> None:
    """multipart/alternative is ordered least-rich first."""
    SmtpNotifier(config(), smtp_factory=FakeSmtp).send("Subject", "text", "<p>html</p>")
    message = FakeSmtp.instances[0].sent[0]
    payload = message.get_payload()
    assert isinstance(payload, list)
    types = [part.get_content_type() for part in payload if isinstance(part, Message)]
    assert types == ["text/plain", "text/html"]


def test_connection_is_closed_even_when_sending_fails() -> None:
    class Failing(FakeSmtp):
        def send_message(self, message: EmailMessage) -> None:
            raise OSError("connection reset")

    with pytest.raises(OSError):
        SmtpNotifier(config(), smtp_factory=Failing).send("Subject", "text", "<p>html</p>")
    assert FakeSmtp.instances[0].quit_called


def test_console_notifier_writes_the_text_body() -> None:
    written: list[str] = []
    ConsoleNotifier(write=written.append).send("Subject line", "the text body", "<p>ignored</p>")
    output = "\n".join(written)
    assert "Subject line" in output
    assert "the text body" in output


def test_email_config_rejects_missing_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_RECIPIENTS"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ConfigError) as caught:
        EmailConfig.from_env()
    assert "SMTP_USERNAME" in str(caught.value)


def test_email_config_reads_and_splits_recipients(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_USERNAME", "me@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("EMAIL_RECIPIENTS", "one@example.com, two@example.com ,")
    loaded = EmailConfig.from_env()
    assert loaded.recipients == ("one@example.com", "two@example.com")
    assert loaded.sender == "me@gmail.com"
