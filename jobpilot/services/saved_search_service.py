"""Saved-search persistence and run-health ownership.

Preserves the atomic run-claim contract from the derived ``ai-job-scraper``
project, now backed by the ``saved_searches`` table.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, update
from sqlalchemy.engine import CursorResult
from sqlmodel import Session, col, select

from jobpilot.database.engine import db_session
from jobpilot.database.models import SavedSearch
from jobpilot.models.enums import EmploymentType, JobSite, SavedSearchRunStatus

RUN_LEASE = timedelta(minutes=30)


class SavedSearchCreate(BaseModel):
    """Validated input for creating a saved search."""

    name: str
    query: str
    location: str = "United States"
    sites: list[JobSite] = Field(
        default_factory=lambda: [JobSite.LINKEDIN, JobSite.INDEED],
        min_length=1,
    )
    remote_only: bool = False
    job_type: EmploymentType | None = None
    results_limit: int = Field(default=50, ge=1, le=1000)
    enabled: bool = True

    @field_validator("name", "query", "location")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Saved-search text fields cannot be empty")
        return value


class SavedSearchUpdate(BaseModel):
    """Validated editable fields for an existing saved search."""

    name: str | None = None
    query: str | None = None
    location: str | None = None
    sites: list[JobSite] | None = Field(default=None, min_length=1)
    remote_only: bool | None = None
    job_type: EmploymentType | None = None
    results_limit: int | None = Field(default=None, ge=1, le=1000)
    enabled: bool | None = None

    @field_validator("name", "query", "location")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Saved-search text fields cannot be empty")
        return value


class SavedSearchDTO(BaseModel):
    """Detached saved-search definition and run health for services and UI."""

    id: int
    name: str
    query: str
    location: str
    sites: list[JobSite]
    remote_only: bool
    job_type: EmploymentType | None
    results_limit: int
    enabled: bool
    last_run_at: datetime | None = None
    last_run_status: SavedSearchRunStatus = SavedSearchRunStatus.NEVER
    jobs_seen: int = 0
    jobs_new: int = 0
    jobs_duplicates: int = 0
    duration_ms: int | None = None
    last_error: str | None = None


class SavedSearchService:
    """CRUD and latest-run health for user-owned scrape definitions."""

    @staticmethod
    def _to_dto(search: SavedSearch) -> SavedSearchDTO:
        return SavedSearchDTO(
            id=search.id,
            name=search.name,
            query=search.query,
            location=search.location,
            sites=[JobSite(site) for site in (search.sites or [])],
            remote_only=search.remote_only,
            job_type=search.job_type,
            results_limit=search.results_limit,
            enabled=search.enabled,
            last_run_at=search.last_run_at,
            last_run_status=search.last_run_status,
            jobs_seen=search.jobs_seen,
            jobs_new=search.jobs_new,
            jobs_duplicates=search.jobs_duplicates,
            duration_ms=search.duration_ms,
            last_error=search.last_error,
        )

    def list(self, *, enabled_only: bool = False) -> list[SavedSearchDTO]:
        with db_session() as session:
            statement = select(SavedSearch)
            if enabled_only:
                statement = statement.where(col(SavedSearch.enabled).is_(True))
            searches = session.exec(statement.order_by(SavedSearch.name)).all()
            return [self._to_dto(search) for search in searches]

    def get(self, search_id: int) -> SavedSearchDTO | None:
        with db_session() as session:
            search = session.get(SavedSearch, search_id)
            return self._to_dto(search) if search else None

    def create(self, data: SavedSearchCreate) -> SavedSearchDTO:
        with db_session() as session:
            search = SavedSearch.model_validate(data.model_dump())
            session.add(search)
            session.flush()
            return self._to_dto(search)

    def update(self, search_id: int, data: SavedSearchUpdate) -> SavedSearchDTO | None:
        with db_session() as session:
            search = session.get(SavedSearch, search_id)
            if search is None:
                return None
            for field, value in data.model_dump(exclude_unset=True).items():
                setattr(search, field, value)
            session.flush()
            return self._to_dto(search)

    def delete(self, search_id: int) -> bool:
        """Delete only the search definition; persisted jobs remain untouched."""
        with db_session() as session:
            search = session.get(SavedSearch, search_id)
            if search is None:
                return False
            session.delete(search)
            return True

    def claim_run(self, search_id: int, started_at: datetime) -> SavedSearchDTO | None:
        """Atomically claim one run or reclaim a stale run lease."""
        stale_before = started_at - RUN_LEASE
        with db_session() as session:
            result = cast(
                CursorResult[Any],
                session.execute(
                    update(SavedSearch)
                    .where(
                        col(SavedSearch.id) == search_id,
                        or_(
                            col(SavedSearch.last_run_status)
                            != SavedSearchRunStatus.RUNNING,
                            col(SavedSearch.last_run_at).is_(None),
                            col(SavedSearch.last_run_at) < stale_before,
                        ),
                    )
                    .values(
                        last_run_at=started_at,
                        last_run_status=SavedSearchRunStatus.RUNNING,
                        jobs_seen=0,
                        jobs_new=0,
                        jobs_duplicates=0,
                        duration_ms=None,
                        last_error=None,
                    )
                ),
            )
            if result.rowcount != 1:
                return None
            search = session.get(SavedSearch, search_id)
            return self._to_dto(search) if search else None

    def record_run(
        self,
        search_id: int,
        *,
        status: SavedSearchRunStatus,
        started_at: datetime,
        duration_ms: int,
        jobs_seen: int = 0,
        jobs_new: int = 0,
        jobs_duplicates: int = 0,
        error: str | None = None,
        session: Session | None = None,
    ) -> SavedSearchDTO | None:
        """Record terminal run health, optionally in a caller-owned transaction."""

        def _record(bound_session: Session) -> SavedSearchDTO | None:
            result = cast(
                CursorResult[Any],
                bound_session.execute(
                    update(SavedSearch)
                    .where(
                        col(SavedSearch.id) == search_id,
                        col(SavedSearch.last_run_status)
                        == SavedSearchRunStatus.RUNNING,
                        col(SavedSearch.last_run_at) == started_at,
                    )
                    .values(
                        last_run_at=datetime.now(UTC),
                        last_run_status=status,
                        jobs_seen=jobs_seen,
                        jobs_new=jobs_new,
                        jobs_duplicates=jobs_duplicates,
                        duration_ms=duration_ms,
                        last_error=error,
                    )
                ),
            )
            if result.rowcount != 1:
                return None
            search = bound_session.get(SavedSearch, search_id)
            return self._to_dto(search) if search else None

        if session is not None:
            return _record(session)
        with db_session() as owned_session:
            return _record(owned_session)


saved_search_service = SavedSearchService()
