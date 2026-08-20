"""The discovery pipeline orchestrator.

Pipeline stages:

    Source -> Scraper -> Parser -> Normalizer -> Deduplicator -> Enricher

Each stage has a single responsibility. The orchestrator wires them together
and returns a :class:`PipelineResult` with truthful counts for observability.
Persistence, AI analysis, matching, and ranking are performed by downstream
services against the pipeline output.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from jobpilot.models.job_posting import JobScrapeRequest
from jobpilot.models.normalized_job import NormalizedJob
from jobpilot.pipeline.deduplicator import Deduplicator, DedupResult
from jobpilot.pipeline.enricher import Enricher
from jobpilot.pipeline.normalizer import Normalizer
from jobpilot.scrapers.base import JobSource, SourceHealth
from jobpilot.scrapers.registry import get_source


class PipelineResult(BaseModel):
    """Truthful counts and outputs from one discovery pipeline run."""

    source: str
    request: JobScrapeRequest
    jobs: list[NormalizedJob] = Field(default_factory=list)
    duplicates: list[NormalizedJob] = Field(default_factory=list)
    raw_found: int = 0
    invalid_rows: int = 0
    total_found: int = 0
    dedup_signals: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    success: bool = True
    error: str | None = None
    source_health: SourceHealth | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class DiscoveryPipeline:
    """Wires scraping, parsing, normalization, enrichment, and deduplication."""

    normalizer: Normalizer = field(default_factory=Normalizer)
    enricher: Enricher = field(default_factory=Enricher)
    deduplicator: Deduplicator = field(default_factory=Deduplicator)

    def run(
        self, request: JobScrapeRequest, source: JobSource | None = None
    ) -> PipelineResult:
        started = time.perf_counter()
        source = source or get_source("jobspy")
        try:
            raw_result = source.fetch_jobs(request)
        except Exception as error:
            logger = logging.getLogger(__name__)
            logger.exception("Source %s failed during discovery", source.name)
            return PipelineResult(
                source=source.name,
                request=request,
                success=False,
                error=f"Source {source.name} failed: {error}",
                duration_ms=round((time.perf_counter() - started) * 1000),
            )

        try:
            health = source.health_check()
        except Exception:
            health = SourceHealth(source=source.name, available=False)

        normalized, rejected = self.normalizer.normalize_batch(
            raw_result.jobs, source=source
        )
        normalized = [self.enricher.enrich(job) for job in normalized]

        dedup: DedupResult = self.deduplicator.deduplicate(normalized)
        duration_ms = round((time.perf_counter() - started) * 1000)

        return PipelineResult(
            source=source.name,
            request=request,
            jobs=dedup.unique_jobs,
            duplicates=dedup.duplicates,
            raw_found=int(raw_result.metadata.get("raw_found", len(raw_result.jobs))),
            invalid_rows=rejected + int(raw_result.metadata.get("invalid_rows", 0)),
            total_found=len(raw_result.jobs),
            dedup_signals=dedup.signals,
            duration_ms=duration_ms,
            success=bool(raw_result.metadata.get("success", True)),
            error=str(raw_result.metadata.get("error"))
            if raw_result.metadata.get("error")
            else None,
            source_health=health,
            metadata=dict(raw_result.metadata),
        )


discovery_pipeline = DiscoveryPipeline()
