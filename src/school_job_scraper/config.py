"""Settings, read from the environment (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class FilterConfig:
    """Which boundary cases count as qualifying.

    These are toggles rather than hardcoded rules because the boundaries are a
    judgement call, and the right answer tends to become obvious only after
    seeing a few real postings.
    """

    include_temporary: bool = True
    include_kindergarten: bool = False
    include_preschool: bool = False
    include_immersion: bool = False
    include_specialists: bool = False
    include_internal: bool = True

    @classmethod
    def from_env(cls) -> FilterConfig:
        return cls(
            include_temporary=_flag("INCLUDE_TEMPORARY", True),
            include_kindergarten=_flag("INCLUDE_KINDERGARTEN", False),
            include_preschool=_flag("INCLUDE_PRESCHOOL", False),
            include_immersion=_flag("INCLUDE_IMMERSION", False),
            include_specialists=_flag("INCLUDE_SPECIALISTS", False),
            include_internal=_flag("INCLUDE_INTERNAL", True),
        )


class ConfigError(RuntimeError):
    """Raised when required email settings are missing."""


@dataclass(frozen=True)
class EmailConfig:
    """Gmail SMTP delivery settings."""

    host: str
    port: int
    username: str
    password: str
    sender: str
    recipients: tuple[str, ...]
    send_when_empty: bool = False

    @classmethod
    def from_env(cls) -> EmailConfig:
        missing = [
            key
            for key in ("SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_RECIPIENTS")
            if not os.environ.get(key)
        ]
        if missing:
            raise ConfigError(
                "Missing required environment variable(s): "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill it in."
            )
        username = os.environ["SMTP_USERNAME"]
        recipients = tuple(
            addr.strip() for addr in os.environ["EMAIL_RECIPIENTS"].split(",") if addr.strip()
        )
        if not recipients:
            raise ConfigError("EMAIL_RECIPIENTS contained no usable addresses.")
        return cls(
            host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
            port=int(os.environ.get("SMTP_PORT", "587")),
            username=username,
            password=os.environ["SMTP_PASSWORD"],
            sender=os.environ.get("EMAIL_FROM", username),
            recipients=recipients,
            send_when_empty=_flag("SEND_WHEN_EMPTY", False),
        )


@dataclass(frozen=True)
class AppConfig:
    """Everything the daily run needs."""

    filters: FilterConfig = field(default_factory=FilterConfig)
    timeout_seconds: float = 30.0
    max_detail_lookups: int = 60
