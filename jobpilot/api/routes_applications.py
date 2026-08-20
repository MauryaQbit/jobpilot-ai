"""Application-tracking HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select

from jobpilot.api.schemas import ApplicationResponse, ApplicationStatusRequest
from jobpilot.database.engine import db_session
from jobpilot.database.models import Company, Job
from jobpilot.models.enums import ApplicationStage
from jobpilot.services.application_service import application_service
from jobpilot.services.job_service import job_service

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=list[ApplicationResponse])
def list_applications(
    status: ApplicationStage | None = None,
    profile_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ApplicationResponse]:
    """List application records, optionally filtered by stage."""
    rows = application_service.list_applications(
        profile_id=profile_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    company_names = _company_names_by_job([job for _, job in rows])
    return [
        ApplicationResponse.from_row(application, job, company_names.get(job.id, ""))
        for application, job in rows
    ]


@router.post("/{job_id}/save", response_model=ApplicationResponse)
def save_job(job_id: int, profile_id: int | None = None) -> ApplicationResponse:
    """Save a job for later."""
    _require_job(job_id)
    application = application_service.save_job(job_id, profile_id)
    return _from_application(application)


@router.post("/{job_id}/status", response_model=ApplicationResponse)
def set_status(job_id: int, data: ApplicationStatusRequest) -> ApplicationResponse:
    """Move an application to a new workflow stage."""
    _require_job(job_id)
    application = application_service.set_status(
        job_id,
        data.status,
        data.profile_id,
        notes=data.notes,
    )
    if application is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return _from_application(application)


@router.get("/status-counts", response_model=dict[str, int])
def status_counts(profile_id: int | None = None) -> dict[str, int]:
    """Return application counts grouped by workflow stage."""
    return application_service.count_by_status(profile_id)


def _require_job(job_id: int) -> None:
    if job_service.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")


def _from_application(application) -> ApplicationResponse:
    row = job_service.get_job_with_company(application.job_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Job {application.job_id} not found"
        )
    job, company_name = row
    return ApplicationResponse.from_row(application, job, company_name)


def _company_names_by_job(jobs: list[Job]) -> dict[int, str]:
    job_ids = {job.id for job in jobs if job.id}
    if not job_ids:
        return {}
    with db_session() as session:
        rows = session.exec(
            select(Job.id, Company.name)
            .join(Company, Job.company_id == Company.id)
            .where(Job.id.in_(job_ids))
        ).all()
    return {job_id: name for job_id, name in rows}
