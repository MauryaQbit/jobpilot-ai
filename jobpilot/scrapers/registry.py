"""Job-source registry for JobPilot AI.

New sources register here and become available to the CLI, API, and pipeline.
"""

from __future__ import annotations

from jobpilot.scrapers.base import JobSource, SourceHealth
from jobpilot.scrapers.jobspy_source import jobspy_source

_registry: dict[str, JobSource] = {}


def register(source: JobSource) -> JobSource:
    """Register a job source under its canonical name."""
    _registry[source.name] = source
    return source


def get_source(name: str) -> JobSource:
    """Return a registered source by name or raise a clear error."""
    if name not in _registry:
        available = ", ".join(sorted(_registry))
        raise KeyError(
            f"Unknown job source {name!r}. Available sources: {available or 'none'}."
        )
    return _registry[name]


def list_sources() -> list[str]:
    return sorted(_registry)


def health_checks() -> list[SourceHealth]:
    """Run a health check against every registered source."""
    results = []
    for name in list_sources():
        try:
            results.append(get_source(name).health_check())
        except Exception as exc:
            results.append(
                SourceHealth(source=name, available=False, last_error=str(exc))
            )
    return results


register(jobspy_source)

__all__ = [
    "JobSource",
    "SourceHealth",
    "get_source",
    "health_checks",
    "list_sources",
    "register",
]
