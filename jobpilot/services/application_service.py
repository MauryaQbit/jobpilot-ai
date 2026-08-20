"""Application-tracking service - save, apply, and advance opportunities."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlmodel import select

from jobpilot.database.engine import db_session
from jobpilot.database.models import Application, Job
from jobpilot.models.enums import ApplicationStage

logger = logging.getLogger(__name__)


class ApplicationService:
    """Manage application-tracking records across the workflow stages."""

    @staticmethod
    def get_application(
        job_id: int, profile_id: int | None = None
    ) -> Application | None:
        with db_session() as session:
            statement = select(Application).where(Application.job_id == job_id)
            if profile_id is not None:
                statement = statement.where(Application.profile_id == profile_id)
            return session.exec(
                statement.order_by(Application.updated_at.desc())
            ).first()

    def save_job(
        self, job_id: int, profile_id: int | None = None, notes: str = ""
    ) -> Application:
        """Save a job for later, creating an application record if needed."""
        now = datetime.now(UTC)
        with db_session() as session:
            existing = session.exec(
                select(Application)
                .where(
                    Application.job_id == job_id,
                    Application.profile_id == profile_id,
                )
                .order_by(Application.updated_at.desc())
            ).first()
            if existing is not None:
                existing.status = ApplicationStage.SAVED
                existing.saved_at = existing.saved_at or now
                existing.updated_at = now
                if notes and notes != existing.notes:
                    existing.notes = notes
                session.flush()
                return existing
            row = Application(
                job_id=job_id,
                profile_id=profile_id,
                status=ApplicationStage.SAVED,
                saved_at=now,
                updated_at=now,
                notes=notes,
            )
            session.add(row)
            session.flush()
            return row

    def set_status(
        self,
        job_id: int,
        status: ApplicationStage,
        profile_id: int | None = None,
        *,
        notes: str | None = None,
    ) -> Application | None:
        """Move an application to a new stage, maintaining transition timestamps."""
        now = datetime.now(UTC)
        with db_session() as session:
            row = session.exec(
                select(Application)
                .where(
                    Application.job_id == job_id,
                    Application.profile_id == profile_id,
                )
                .order_by(Application.updated_at.desc())
            ).first()
            if row is None:
                row = Application(
                    job_id=job_id,
                    profile_id=profile_id,
                    status=status,
                    saved_at=now,
                    applied_at=now if status == ApplicationStage.APPLIED else None,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.status = status
                row.updated_at = now
                if status == ApplicationStage.APPLIED and row.applied_at is None:
                    row.applied_at = now
                if notes is not None:
                    row.notes = notes
            session.flush()
            return row

    def list_applications(
        self,
        profile_id: int | None = None,
        status: ApplicationStage | None = None,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[tuple[Application, Job]]:
        statement = select(Application, Job).join(Job, Application.job_id == Job.id)
        if profile_id is not None:
            statement = statement.where(Application.profile_id == profile_id)
        if status is not None:
            statement = statement.where(Application.status == status)
        statement = (
            statement.order_by(Application.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        with db_session() as session:
            return list(session.exec(statement).all())

    def count_by_status(self, profile_id: int | None = None) -> dict[str, int]:
        from sqlalchemy import func

        with db_session() as session:
            statement = select(Application.status, func.count(Application.id))
            if profile_id is not None:
                statement = statement.where(Application.profile_id == profile_id)
            rows = session.exec(statement.group_by(Application.status)).all()
            counts = {stage.value: 0 for stage in ApplicationStage}
            for status, count in rows:
                counts[str(status)] = int(count)
            return counts

    def list_recent_activity(self, limit: int = 20) -> list[tuple[Application, Job]]:
        statement = (
            select(Application, Job)
            .join(Job, Application.job_id == Job.id)
            .order_by(Application.updated_at.desc())
            .limit(limit)
        )
        with db_session() as session:
            return list(session.exec(statement).all())


application_service = ApplicationService()
