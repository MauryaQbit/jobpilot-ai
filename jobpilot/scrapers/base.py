"""Job-source abstraction for JobPilot AI.

A :class:`JobSource` is any provider that can produce raw job postings. New
sources can be added by implementing this interface without touching the rest
of the discovery pipeline.

Sources must respect the terms, robots policies, and authentication
restrictions of the services they read. Implementations must not bypass access
controls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from jobpilot.models.job_posting import JobScrapeRequest, JobScrapeResult


class SourceHealth(BaseModel):
    """Health snapshot for one job source."""

    source: str
    available: bool
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class JobSource(Protocol):
    """Protocol implemented by every discoverable job source."""

    name: str

    def fetch_jobs(self, request: JobScrapeRequest) -> JobScrapeResult:
        """Fetch and validate jobs for the given request."""
        ...

    async def fetch_jobs_async(self, request: JobScrapeRequest) -> JobScrapeResult:
        """Fetch jobs without blocking the event loop."""
        ...

    def health_check(self) -> SourceHealth:
        """Return an honest availability snapshot for the source."""
        ...
