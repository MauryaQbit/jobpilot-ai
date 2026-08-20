"""End-to-end discovery run - saved search to ranked recommendations.

Owns the same atomicity contract as the derived ``scrape_all`` module: job
persistence and the saved-search terminal run health commit in one transaction.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from time import perf_counter

from jobpilot.database.engine import db_session
from jobpilot.models.enums import SavedSearchRunStatus, ScraperRunStatus
from jobpilot.models.job_posting import JobScrapeRequest
from jobpilot.pipeline.orchestrator import PipelineResult, discovery_pipeline
from jobpilot.scrapers.registry import get_source
from jobpilot.services.analysis_service import analysis_service
from jobpilot.services.candidate_service import candidate_service
from jobpilot.services.job_service import job_service
from jobpilot.services.matching_service import matching_service
from jobpilot.services.saved_search_service import SavedSearchDTO, saved_search_service
from jobpilot.services.scraper_run_service import scraper_run_service

logger = logging.getLogger(__name__)


class SavedSearchRunInProgressError(RuntimeError):
    """Raised when a saved search already has a live run lease."""


class RunOutcome:
    """Summary of one end-to-end discovery run."""

    def __init__(
        self,
        *,
        search: SavedSearchDTO | None,
        pipeline: PipelineResult | None = None,
        run_id: int | None = None,
        status: SavedSearchRunStatus = SavedSearchRunStatus.FAILED,
        error: str | None = None,
        jobs_new: int = 0,
        jobs_analyzed: int = 0,
        jobs_matched: int = 0,
    ) -> None:
        self.search = search
        self.pipeline = pipeline
        self.run_id = run_id
        self.status = status
        self.error = error
        self.jobs_new = jobs_new
        self.jobs_analyzed = jobs_analyzed
        self.jobs_matched = jobs_matched

    @property
    def succeeded(self) -> bool:
        return self.status in {
            SavedSearchRunStatus.SUCCEEDED,
            SavedSearchRunStatus.PARTIAL,
        }

    @property
    def jobs_seen(self) -> int:
        return self.pipeline.total_found if self.pipeline else 0

    @property
    def jobs_duplicates(self) -> int:
        return len(self.pipeline.duplicates) if self.pipeline else 0

    @property
    def jobs_rejected(self) -> int:
        return self.pipeline.invalid_rows if self.pipeline else 0

    @property
    def duration_ms(self) -> int:
        return self.pipeline.duration_ms if self.pipeline else 0


async def run_saved_search(search_id: int) -> RunOutcome:
    """Run one saved search end-to-end and return its outcome."""
    started_at = datetime.now(UTC)
    started_clock = perf_counter()
    search = saved_search_service.claim_run(search_id, started_at)
    if search is None:
        if saved_search_service.get(search_id) is None:
            return RunOutcome(search=None, error="Saved search no longer exists")
        raise SavedSearchRunInProgressError(
            f"Saved search {search_id} already has an active run"
        )

    pipeline: PipelineResult | None = None
    run_id: int | None = None
    try:
        run_id = scraper_run_service.start_run(
            source="jobspy",
            search_term=search.query,
            location=search.location,
            remote_only=search.remote_only,
            job_type=search.job_type.value if search.job_type else None,
        ).id

        request = JobScrapeRequest(
            site_name=list(search.sites),
            search_term=search.query,
            location=search.location,
            is_remote=search.remote_only,
            job_type=search.job_type,
            results_wanted=search.results_limit,
        )
        source = get_source("jobspy")
        pipeline = discovery_pipeline.run(request, source=source)

        if not pipeline.success:
            return _finish_failed(
                search,
                pipeline,
                run_id,
                started_clock,
                started_at,
                pipeline.error or "Discovery failed",
            )

        # Persist + record saved-search health in one transaction.
        with db_session() as session:
            persistence = job_service.persist_pipeline_result(pipeline, session=session)
            run_status = (
                SavedSearchRunStatus.PARTIAL
                if pipeline.invalid_rows
                else SavedSearchRunStatus.SUCCEEDED
            )
            saved_search_service.record_run(
                search_id,
                status=run_status,
                started_at=started_at,
                duration_ms=pipeline.duration_ms,
                jobs_seen=pipeline.total_found,
                jobs_new=persistence["inserted"],
                jobs_duplicates=len(pipeline.duplicates),
                error=(
                    f"{pipeline.invalid_rows} provider rows rejected"
                    if pipeline.invalid_rows
                    else None
                ),
                session=session,
            )

        # Downstream intelligence (analysis + matching) runs after the commit.
        new_jobs = job_service.list_jobs(limit=500, order_by="posted_at")
        new_jobs = [job for job, _ in new_jobs]
        analysis_stats = analysis_service.analyze_jobs(new_jobs)
        profile = candidate_service.get_active()
        matched_count = 0
        if profile is not None and profile.id is not None:
            matched = matching_service.match_jobs(new_jobs, profile, minimum_score=0.0)
            matched_count = len(matched)

        scraper_run_service.finish_run(
            run_id,
            status=ScraperRunStatus.SUCCEEDED
            if not pipeline.invalid_rows
            else ScraperRunStatus.PARTIAL,
            jobs_seen=pipeline.total_found,
            jobs_new=persistence["inserted"],
            jobs_duplicates=len(pipeline.duplicates),
            jobs_rejected=pipeline.invalid_rows,
            jobs_analyzed=analysis_stats.get("analyzed", 0),
            jobs_matched=matched_count,
            duration_ms=round((perf_counter() - started_clock) * 1000),
            error=None
            if not pipeline.invalid_rows
            else f"{pipeline.invalid_rows} rows rejected",
        )
        completed = saved_search_service.get(search_id)
        return RunOutcome(
            search=completed,
            pipeline=pipeline,
            run_id=run_id,
            status=completed.last_run_status
            if completed
            else SavedSearchRunStatus.FAILED,
            jobs_new=persistence["inserted"],
            jobs_analyzed=analysis_stats.get("analyzed", 0),
            jobs_matched=matched_count,
        )
    except asyncio.CancelledError:
        saved_search_service.record_run(
            search_id,
            status=SavedSearchRunStatus.CANCELLED,
            started_at=started_at,
            duration_ms=round((perf_counter() - started_clock) * 1000),
            error="Run cancelled",
        )
        if run_id:
            scraper_run_service.finish_run(
                run_id,
                status=ScraperRunStatus.CANCELLED,
                duration_ms=round((perf_counter() - started_clock) * 1000),
                error="Run cancelled",
            )
        raise
    except Exception as error:
        logger.exception("Saved search %s failed", search_id)
        return _finish_failed(
            search, pipeline, run_id, started_clock, started_at, str(error)
        )


def _finish_failed(
    search: SavedSearchDTO,
    pipeline: PipelineResult | None,
    run_id: int | None,
    started_clock: float,
    started_at: datetime,
    error: str,
) -> RunOutcome:
    duration = round((perf_counter() - started_clock) * 1000)
    saved_search_service.record_run(
        search.id,
        status=SavedSearchRunStatus.FAILED,
        started_at=started_at,
        duration_ms=duration,
        jobs_seen=pipeline.total_found if pipeline else 0,
        jobs_duplicates=len(pipeline.duplicates) if pipeline else 0,
        error=error,
    )
    if run_id:
        scraper_run_service.finish_run(
            run_id,
            status=ScraperRunStatus.FAILED,
            duration_ms=duration,
            error=error,
        )
    return RunOutcome(
        search=saved_search_service.get(search.id),
        pipeline=pipeline,
        run_id=run_id,
        status=SavedSearchRunStatus.FAILED,
        error=error,
    )


async def run_all_enabled() -> list[RunOutcome]:
    """Run every enabled saved search sequentially."""
    outcomes: list[RunOutcome] = []
    for search in saved_search_service.list(enabled_only=True):
        try:
            outcomes.append(await run_saved_search(search.id))
        except SavedSearchRunInProgressError:
            logger.info("Skipping saved search %s with an active run", search.id)
            continue
    return outcomes


def run_all_enabled_sync() -> list[RunOutcome]:
    """Run enabled saved searches from synchronous callers."""
    return asyncio.run(run_all_enabled())


__all__ = [
    "RunOutcome",
    "SavedSearchRunInProgressError",
    "run_all_enabled",
    "run_all_enabled_sync",
    "run_saved_search",
]
