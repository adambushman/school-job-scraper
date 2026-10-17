"""Board-specific adapters."""

from .base import JobSource, JsonFetcher
from .davis import DavisSource
from .schoolspring import SchoolSpringSource

__all__ = ["JobSource", "JsonFetcher", "DavisSource", "SchoolSpringSource"]
