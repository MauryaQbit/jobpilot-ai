"""Job service - persistence, queries, and filtering over normalized jobs."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_
from sqlmodel import Session, col, select

from jobpilot.core_utils import ensure_timezone_aware
from jobpilot.database.engine import db_session
from jobpilot.database.models import Application, Company, Job, JobMatchRow
from jobpilot.models.enums import ApplicationStage, JobStatus
from jobpilot.models.filters import JobFilters
from jobpilot.models.normalized_job import NormalizedJob
from jobpilot.pipeline.orchestrator import PipelineResult
from jobpilot.utils.text import parse_domain_from_url

logger = logging.getLogger(__name__)

type PersistStats = dict[str, int]


def resolve_company_names(session: Session, jobs: list[Job]) -> dict[int, str]:
    """Map ``company_id`` to the normalized company name for a batch of jobs."""
    company_ids = {job.company_id for job in jobs if job.company_id}
    if not company_ids:
        return {}
    rows = session.exec(select(Company).where(Company.id.in_(company_ids))).all()
    return {company.id: company.name for company in rows}


class JobService:
    """Query and persist normalized jobs in the canonical application database."""

    # ------------------------------------------------------------- conversion

    @staticmethod
    def _normalized_to_row(job: NormalizedJob, company_id: int) -> Job:
        return Job.create_validated(
            company_id=company_id,
            source=job.source,
            source_job_id=job.source_job_id,
            title=job.title,
            location=job.location,
            remote_type=job.remote_type,
            employment_type=job.employment_type,
            description=job.description,
            requirements=job.requirements,
            responsibilities=job.responsibilities,
            skills=job.skills,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            salary_currency=job.salary_currency,
            experience_level=job.experience_level,
            education=job.education,
            url=job.url,
            application_url=job.application_url,
            company_domain=job.company_domain,
            job_hash=job.job_hash,
            job_metadata=job.metadata,
            posted_at=job.posted_at,
            discovered_at=job.discovered_at,
            last_seen=job.discovered_at,
        )

    @staticmethod
    def _row_to_normalized(row: Job, company_name: str | None = None) -> NormalizedJob:
        return NormalizedJob(
            source=row.source,
            source_job_id=row.source_job_id,
            title=row.title,
            company=company_name or "",
            location=row.location,
            remote_type=row.remote_type,
            employment_type=row.employment_type,
            description=row.description,
            requirements=row.requirements,
            responsibilities=row.responsibilities,
            skills=row.skills,
            salary_min=row.salary_min,
            salary_max=row.salary_max,
            salary_currency=row.salary_currency,
            experience_level=row.experience_level,
            education=row.education,
            url=row.url,
            application_url=row.application_url,
            company_domain=row.company_domain,
            job_hash=row.job_hash,
            metadata=row.job_metadata,
            posted_at=row.posted_at,
            discovered_at=row.discovered_at,
        )

    # ----------------------------------------------------------- persistence

    def persist_pipeline_result(
        self,
        result: PipelineResult,
        *,
        session: Session | None = None,
    ) -> PersistStats:
        """Persist a pipeline result, merging provider fields without clobbering user state."""
        stats: PersistStats = {
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "duplicates": 0,
        }
        stats["duplicates"] = len(result.duplicates)

        if session is not None:
            self._persist_jobs(session, result.jobs, stats)
            return stats
        with db_session() as owned_session:
            self._persist_jobs(owned_session, result.jobs, stats)
        return stats

    def _persist_jobs(
        self, session: Session, jobs: list[NormalizedJob], stats: PersistStats
    ) -> None:
        for job in jobs:
            existing = session.exec(select(Job).where(Job.url == job.url)).first()
            company_id = self._get_or_create_company(
                session,
                job.company,
                parse_domain_from_url(job.url),
            )
            if existing is None:
                session.add(self._normalized_to_row(job, company_id))
                stats["inserted"] += 1
                continue

            candidate = self._normalized_to_row(job, company_id)
            changed = False
            for field in (
                "source",
                "source_job_id",
                "title",
                "location",
                "remote_type",
                "employment_type",
                "description",
                "requirements",
                "responsibilities",
                "skills",
                "salary_min",
                "salary_max",
                "salary_currency",
                "experience_level",
                "education",
                "application_url",
                "company_domain",
                "job_hash",
                "posted_at",
            ):
                incoming = getattr(candidate, field)
                current = getattr(existing, field)
                if isinstance(incoming, datetime) or isinstance(current, datetime):
                    incoming = ensure_timezone_aware(incoming)
                    current = ensure_timezone_aware(current)
                if incoming != current:
                    setattr(existing, field, incoming)
                    changed = True
            existing.company_id = company_id
            existing.last_seen = job.discovered_at or datetime.now(UTC)
            stats["updated" if changed else "skipped"] += 1

    @staticmethod
    def _get_or_create_company(
        session: Session, company_name: str, domain: str | None
    ) -> int:
        company = session.exec(
            select(Company).where(Company.name == company_name)
        ).first()
        if company is None:
            company = Company(name=company_name, url=domain, domain=domain)
            session.add(company)
            session.flush()
        else:
            if not company.url and domain:
                company.url = domain
            if not company.domain and domain:
                company.domain = domain
        if company.id is None:
            raise RuntimeError("Company ID was not assigned")
        return company.id

    # ---------------------------------------------------------------- queries

    def get_job(self, job_id: int) -> Job | None:
        with db_session() as session:
            row = session.get(Job, job_id)
            return row

    def get_job_with_company(self, job_id: int) -> tuple[Job, str] | None:
        with db_session() as session:
            row = session.exec(
                select(Job, Company.name)
                .join(Company, Job.company_id == Company.id)
                .where(Job.id == job_id)
            ).first()
            return row

    def _apply_filters(self, statement, filters: JobFilters):
        if filters.query:
            terms = filters.query.split()
            for term in terms:
                statement = statement.where(
                    or_(
                        Job.title.contains(term, autoescape=True),
                        Job.description.contains(term, autoescape=True),
                        Company.name.contains(term, autoescape=True),
                        Job.location.contains(term, autoescape=True),
                    )
                )
        if filters.keyword:
            statement = statement.where(
                or_(
                    Job.title.contains(filters.keyword, autoescape=True),
                    Job.description.contains(filters.keyword, autoescape=True),
                    Job.skills.cast(str).contains(filters.keyword, autoescape=True),
                )
            )
        if filters.role:
            statement = statement.where(
                Job.title.contains(filters.role, autoescape=True)
            )
        if filters.company:
            statement = statement.where(Company.name.in_(filters.company))
        if filters.location:
            statement = statement.where(
                Job.location.contains(filters.location, autoescape=True)
            )
        if filters.remote:
            statement = statement.where(Job.remote_type == filters.remote)
        if filters.salary_min is not None:
            statement = statement.where(
                or_(Job.salary_max.is_(None), Job.salary_max >= filters.salary_min)
            )
        if filters.salary_max is not None:
            statement = statement.where(
                or_(Job.salary_min.is_(None), Job.salary_min <= filters.salary_max)
            )
        if filters.experience:
            statement = statement.where(Job.experience_level.in_(filters.experience))
        if filters.employment_type:
            statement = statement.where(
                Job.employment_type.in_(filters.employment_type)
            )
        if filters.required_skill:
            statement = statement.where(
                Job.skills.cast(str).contains(filters.required_skill, autoescape=True)
            )
        if filters.source:
            statement = statement.where(Job.source.in_(filters.source))
        if filters.posted_after:
            statement = statement.where(
                Job.posted_at
                >= datetime.combine(
                    filters.posted_after, datetime.min.time(), tzinfo=UTC
                )
            )
        if filters.posted_before:
            statement = statement.where(
                Job.posted_at
                <= datetime.combine(
                    filters.posted_before, datetime.max.time(), tzinfo=UTC
                )
            )
        if not filters.include_archived:
            statement = statement.where(Job.status == JobStatus.ACTIVE)
        return statement

    def list_jobs(
        self,
        filters: JobFilters | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "posted_at",
        profile_id: int | None = None,
    ) -> list[tuple[Job, str]]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        if offset < 0:
            raise ValueError("offset must be nonnegative")

        statement = select(Job, Company.name).join(
            Company, Job.company_id == Company.id
        )
        statement = self._apply_filters(statement, filters or JobFilters())

        if order_by == "salary":
            statement = statement.order_by(
                col(Job.salary_max).desc().nullslast(), Job.posted_at.desc()
            )
        elif order_by == "match_score":
            if profile_id is None:
                raise ValueError("match_score ordering requires profile_id")
            statement = statement.join(
                JobMatchRow,
                JobMatchRow.job_id == Job.id,
            ).where(JobMatchRow.profile_id == profile_id)
            statement = statement.order_by(
                JobMatchRow.score.desc(),
                Job.posted_at.desc().nullslast(),
            )
        else:
            statement = statement.order_by(
                Job.posted_at.desc().nullslast(), Job.id.desc()
            )

        statement = statement.offset(offset).limit(limit)
        with db_session() as session:
            return list(session.exec(statement).all())

    def count_jobs(self, filters: JobFilters | None = None) -> int:
        statement = select(func.count(Job.id)).join(
            Company, Job.company_id == Company.id
        )
        statement = self._apply_filters(statement, filters or JobFilters()).order_by(
            None
        )
        with db_session() as session:
            return int(session.exec(statement).one())

    def recent_jobs(self, days: int = 7, limit: int = 100) -> list[tuple[Job, str]]:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        with db_session() as session:
            rows = session.exec(
                select(Job, Company.name)
                .join(Company, Job.company_id == Company.id)
                .where(Job.posted_at >= cutoff, Job.status == JobStatus.ACTIVE)
                .order_by(Job.posted_at.desc())
                .limit(limit)
            ).all()
            return list(rows)

    def get_status_counts(self) -> dict[str, int]:
        """Count applications grouped by workflow stage."""
        with db_session() as session:
            rows = session.exec(
                select(Application.status, func.count(Application.id)).group_by(
                    Application.status
                )
            ).all()
            counts = {stage.value: 0 for stage in ApplicationStage}
            for status, count in rows:
                counts[str(status)] = int(count)
            return counts

    def get_discovery_stats(self) -> dict[str, Any]:
        with db_session() as session:
            total = int(session.exec(select(func.count(Job.id))).one())
            added_today = int(
                session.exec(
                    select(func.count(Job.id)).where(
                        func.date(Job.discovered_at) == func.date("now")
                    )
                ).one()
            )
            analyzed = int(
                session.exec(select(func.count(Job.id)).where(Job.job_hash != "")).one()
            )
            return {
                "total_jobs": total,
                "added_today": added_today,
                "archived": int(
                    session.exec(
                        select(func.count(Job.id)).where(
                            Job.status == JobStatus.ARCHIVED
                        )
                    ).one()
                ),
                "with_description": int(
                    session.exec(
                        select(func.count(Job.id)).where(Job.description != "")
                    ).one()
                ),
                "analyzed": analyzed,
            }


job_service = JobService()
