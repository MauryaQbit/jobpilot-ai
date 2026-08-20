"""Scraper-run observability service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlmodel import select

from jobpilot.database.engine import db_session
from jobpilot.database.models import ScraperRun
from jobpilot.models.enums import ScraperRunStatus


class ScraperRunService:
    """Record and query discovery pipeline runs for observability."""

    def start_run(
        self,
        *,
        source: str,
        search_term: str | None = None,
        location: str | None = None,
        remote_only: bool = False,
        job_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ScraperRun:
        with db_session() as session:
            row = ScraperRun(
                source=source,
                search_term=search_term,
                location=location,
                remote_only=remote_only,
                job_type=job_type,
                status=ScraperRunStatus.RUNNING,
                started_at=datetime.now(UTC),
                run_metadata=metadata or {},
            )
            session.add(row)
            session.flush()
            return row

    def finish_run(
        self,
        run_id: int,
        *,
        status: ScraperRunStatus,
        jobs_seen: int = 0,
        jobs_new: int = 0,
        jobs_duplicates: int = 0,
        jobs_rejected: int = 0,
        jobs_analyzed: int = 0,
        jobs_matched: int = 0,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        with db_session() as session:
            row = session.get(ScraperRun, run_id)
            if row is None:
                return
            row.status = status
            row.jobs_seen = jobs_seen
            row.jobs_new = jobs_new
            row.jobs_duplicates = jobs_duplicates
            row.jobs_rejected = jobs_rejected
            row.jobs_analyzed = jobs_analyzed
            row.jobs_matched = jobs_matched
            row.duration_ms = duration_ms
            row.finished_at = datetime.now(UTC)
            row.error = error

    def list_runs(self, *, limit: int = 20) -> list[ScraperRun]:
        with db_session() as session:
            return list(
                session.exec(
                    select(ScraperRun)
                    .order_by(ScraperRun.started_at.desc())
                    .limit(limit)
                ).all()
            )

    def summary(self) -> dict[str, Any]:
        with db_session() as session:
            total_runs = int(session.exec(select(func.count(ScraperRun.id))).one())
            successful = int(
                session.exec(
                    select(func.count(ScraperRun.id)).where(
                        ScraperRun.status == ScraperRunStatus.SUCCEEDED
                    )
                ).one()
            )
            failed = int(
                session.exec(
                    select(func.count(ScraperRun.id)).where(
                        ScraperRun.status == ScraperRunStatus.FAILED
                    )
                ).one()
            )
        return {
            "total_runs": total_runs,
            "successful_runs": successful,
            "failed_runs": failed,
        }


scraper_run_service = ScraperRunService()
