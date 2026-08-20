"""Job, analysis, and match HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from jobpilot.api.schemas import (
    AnalysisResponse,
    JobResponse,
    MatchResponse,
)
from jobpilot.models.filters import JobFilters
from jobpilot.services.analysis_service import analysis_service
from jobpilot.services.job_service import job_service
from jobpilot.services.matching_service import matching_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobResponse])
def list_jobs(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    order_by: str = Query(
        default="posted_at", pattern="^(posted_at|salary|match_score)$"
    ),
    query: str | None = None,
    keyword: str | None = None,
    company: str | None = None,
    location: str | None = None,
    remote: str | None = Query(default=None, pattern="^(remote|onsite|hybrid)$"),
    profile_id: int | None = None,
) -> list[JobResponse]:
    """List jobs with optional filtering and ordering."""
    filters = JobFilters(
        query=query or "",
        keyword=keyword,
        company=[company] if company else [],
        location=location or "",
        remote=remote,
        include_archived=False,
    )
    rows = job_service.list_jobs(
        filters,
        limit=limit,
        offset=offset,
        order_by=order_by,
        profile_id=profile_id,
    )
    return [JobResponse.from_row(job, company_name) for job, company_name in rows]


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: int) -> JobResponse:
    """Return one job with its normalized company name."""
    row = job_service.get_job_with_company(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    job, company_name = row
    return JobResponse.from_row(job, company_name)


@router.get("/{job_id}/analysis", response_model=AnalysisResponse)
def get_analysis(job_id: int) -> AnalysisResponse:
    """Return the cached structured analysis for one job."""
    analysis = analysis_service.get_analysis(job_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"No analysis for job {job_id}")
    row = _load_analysis_row(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No analysis for job {job_id}")
    return AnalysisResponse.from_row(row)


@router.get("/{job_id}/match", response_model=MatchResponse | None)
def get_match(job_id: int, profile_id: int | None = None) -> MatchResponse | None:
    """Return the cached match for one job (uses the active profile by default)."""
    if profile_id is None:
        from jobpilot.services.candidate_service import candidate_service

        active = candidate_service.get_active()
        if active is None or active.id is None:
            return None
        profile_id = active.id
    row = matching_service.get_match(job_id, profile_id)
    if row is None:
        return None
    return MatchResponse.from_row(row)


def _load_analysis_row(job_id: int):
    from sqlmodel import select

    from jobpilot.database.engine import db_session
    from jobpilot.database.models import JobAnalysisRow

    with db_session() as session:
        return session.exec(
            select(JobAnalysisRow).where(JobAnalysisRow.job_id == job_id)
        ).first()
