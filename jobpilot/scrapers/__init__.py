"""Job-source layer for JobPilot AI."""

from __future__ import annotations

from jobpilot.scrapers.base import JobSource, SourceHealth
from jobpilot.scrapers.jobspy_source import jobspy_source
from jobpilot.scrapers.registry import (
    get_source,
    health_checks,
    list_sources,
    register,
)

__all__ = [
    "JobSource",
    "SourceHealth",
    "get_source",
    "health_checks",
    "jobspy_source",
    "list_sources",
    "register",
]
