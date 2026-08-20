"""Behavioral tests for canonical job querying and persistence."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from jobpilot.database.models import Application
from jobpilot.models.enums import ApplicationStage, JobSite, JobStatus
from jobpilot.models.filters import JobFilters
from jobpilot.models.job_posting import JobScrapeRequest
from jobpilot.models.normalized_job import NormalizedJob
from jobpilot.pipeline.orchestrator import PipelineResult
from jobpilot.services.job_service import JobService, job_service
from sqlalchemy.exc import OperationalError

from tests.factories import CompanyFactory, JobFactory


def _normalized_job(
    *,
    identifier: str = "job-1",
    title: str = "AI Engineer",
    company: str = "Acme",
    url: str = "https://example.com/jobs/1",
    description: str = "Build useful systems",
    **overrides,
) -> NormalizedJob:
    return NormalizedJob(
        source=JobSite.LINKEDIN,
        source_job_id=identifier,
        title=title,
        company=company,
        url=url,
        description=description,
        location="Remote",
        posted_at=datetime(2026, 1, 1, tzinfo=UTC),
        salary_min=120_000,
        salary_max=180_000,
        **overrides,
    )


def _pipeline_result(jobs, duplicates=None) -> PipelineResult:
    return PipelineResult(
        source="jobspy",
        request=JobScrapeRequest(
            site_name=[JobSite.LINKEDIN], search_term="AI engineer"
        ),
        jobs=jobs,
        duplicates=duplicates or [],
        raw_found=len(jobs),
        invalid_rows=0,
        total_found=len(jobs),
        duration_ms=0,
        success=True,
    )


@pytest.fixture
def seeded_jobs(session):
    tech = CompanyFactory(name="TechCorp")
    startup = CompanyFactory(name="StartupCo")
    jobs = [
        JobFactory(
            company=tech,
            title="Senior Python Developer",
            posted_at=datetime.now(UTC) - timedelta(days=1),
            salary_min=120_000,
            salary_max=180_000,
        ),
        JobFactory(
            company=startup,
            title="ML Engineer",
            posted_at=datetime.now(UTC) - timedelta(days=5),
            salary_min=100_000,
            salary_max=150_000,
        ),
        JobFactory(
            company=tech,
            title="Archived Data Scientist",
            posted_at=datetime.now(UTC) - timedelta(days=10),
            salary_min=90_000,
            salary_max=130_000,
            status=JobStatus.ARCHIVED,
        ),
    ]
    session.commit()
    return tech, startup, jobs


def test_row_to_normalized_uses_explicit_company_name(session):
    company = CompanyFactory(name="Acme")
    record = JobFactory(
        company=company,
        title="Platform Engineer",
        description="Description",
        salary_min=100_000,
        salary_max=140_000,
    )
    job = JobService._row_to_normalized(record, "Acme")

    assert isinstance(job, NormalizedJob)
    assert job.company == "acme"
    assert job.salary_min == 100_000
    assert job.salary_max == 140_000


def test_filtered_jobs_apply_canonical_facets(seeded_jobs):
    unfiltered = JobService().list_jobs()
    assert [job.title for job, _ in unfiltered] == [
        "Senior Python Developer",
        "ML Engineer",
    ]

    assert [
        job.title
        for job, name in JobService().list_jobs(JobFilters(company=["TechCorp"]))
    ] == ["Senior Python Developer"]
    assert [
        job.title for job, _ in JobService().list_jobs(JobFilters(salary_min=160_000))
    ] == ["Senior Python Developer"]
    assert len(JobService().list_jobs(JobFilters(include_archived=True))) == 3


def test_job_crud_and_counts_persist(seeded_jobs, session):
    _, _, jobs = seeded_jobs
    job_id = jobs[0].id
    assert job_id is not None

    job = JobService().get_job(job_id)
    assert job is not None
    assert job.title == "Senior Python Developer"

    assert JobService().count_jobs() == 2
    assert JobService().count_jobs(JobFilters(include_archived=True)) == 3

    session.add_all(
        [
            Application(job_id=jobs[0].id, status=ApplicationStage.APPLIED),
            Application(job_id=jobs[1].id, status=ApplicationStage.APPLIED),
        ]
    )
    session.commit()
    counts = JobService().get_status_counts()
    assert counts[ApplicationStage.APPLIED.value] == 2
    assert counts[ApplicationStage.INBOX.value] == 0


def test_job_crud_returns_none_for_missing_records(session):
    assert JobService().get_job(404) is None
    assert JobService().get_job_with_company(404) is None


def test_recent_jobs_are_ordered_and_limited(seeded_jobs):
    recent = JobService().recent_jobs(days=7, limit=1)
    assert [job.title for job, _ in recent] == ["Senior Python Developer"]


def test_persistence_reports_insert_update_and_skip(session):
    service = JobService()
    original = _normalized_job()
    second = _normalized_job(
        identifier="job-2",
        company="Beta",
        url="https://example.com/jobs/2",
    )

    assert service.persist_pipeline_result(_pipeline_result([original, second])) == {
        "inserted": 2,
        "updated": 0,
        "skipped": 0,
        "duplicates": 0,
    }
    assert service.persist_pipeline_result(_pipeline_result([original, second])) == {
        "inserted": 0,
        "updated": 0,
        "skipped": 2,
        "duplicates": 0,
    }
    changed = original.model_copy(update={"title": "Principal AI Engineer"})
    assert service.persist_pipeline_result(_pipeline_result([changed])) == {
        "inserted": 0,
        "updated": 1,
        "skipped": 0,
        "duplicates": 0,
    }
    rows = JobService().list_jobs(JobFilters(query="Acme"))
    assert rows[0][0].title == "Principal AI Engineer"


def test_persistence_propagates_database_failure():
    with (
        patch(
            "jobpilot.services.job_service.db_session",
            side_effect=OperationalError("statement", {}, RuntimeError("offline")),
        ),
        pytest.raises(OperationalError),
    ):
        JobService().persist_pipeline_result(_pipeline_result([_normalized_job()]))


def test_global_service_instance_is_ready():
    assert isinstance(job_service, JobService)
