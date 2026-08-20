"""Read-only company facets derived from persisted jobs."""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import case, func
from sqlmodel import select

from jobpilot.database.engine import db_session
from jobpilot.database.models import Company, Job


class CompanyFacet(BaseModel):
    """Aggregated view of one company from the jobs it owns."""

    id: int
    name: str
    url: str | None = None
    domain: str | None = None
    total_jobs: int = 0
    active_jobs: int = 0
    last_job_posted: object | None = None


class CompanyService:
    """Expose companies as job-derived facets."""

    def list_companies(self, *, limit: int = 200) -> list[CompanyFacet]:
        with db_session() as session:
            rows = session.exec(
                select(
                    Company.id,
                    Company.name,
                    Company.url,
                    Company.domain,
                    func.count(Job.id),
                    func.sum(case((Job.status == "active", 1), else_=0)),
                    func.max(Job.posted_at),
                )
                .join(Job, Job.company_id == Company.id)
                .group_by(Company.id)
                .order_by(func.count(Job.id).desc(), Company.name)
                .limit(limit)
            ).all()
            return [
                CompanyFacet(
                    id=company_id,
                    name=name,
                    url=url,
                    domain=domain,
                    total_jobs=total_jobs,
                    active_jobs=active_jobs or 0,
                    last_job_posted=last_job_posted,
                )
                for (
                    company_id,
                    name,
                    url,
                    domain,
                    total_jobs,
                    active_jobs,
                    last_job_posted,
                ) in rows
            ]

    def get_company(self, company_id: int) -> Company | None:
        with db_session() as session:
            return session.get(Company, company_id)


company_service = CompanyService()
