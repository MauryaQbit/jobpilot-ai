"""Behavioral tests for canonical database-backed job search."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from jobpilot.models.enums import JobStatus
from jobpilot.models.filters import JobFilters
from jobpilot.services.job_service import JobService, job_service
from sqlalchemy.exc import OperationalError

from tests.factories import CompanyFactory, JobFactory


@pytest.fixture
def searchable_jobs(session):
    tech = CompanyFactory(name="Tech Corp")
    ai = CompanyFactory(name="AI Startup")
    jobs = [
        JobFactory(
            company=tech,
            title="Senior Python Developer",
            description="Build APIs with Django and FastAPI",
            location="San Francisco, CA",
            posted_at=datetime.now(UTC) - timedelta(days=1),
            salary_min=120_000,
            salary_max=180_000,
        ),
        JobFactory(
            company=tech,
            title="Machine Learning Engineer",
            description="Develop Python models with PyTorch",
            location="Remote",
            posted_at=datetime.now(UTC) - timedelta(days=2),
            salary_min=150_000,
            salary_max=220_000,
        ),
        JobFactory(
            company=ai,
            title="Data Scientist",
            description="Analyze product data",
            location="New York, NY",
            posted_at=datetime.now(UTC) - timedelta(days=3),
            salary_min=130_000,
            salary_max=190_000,
        ),
        JobFactory(
            company=ai,
            title="Frontend Developer",
            description="Build React interfaces",
            location="Austin, TX",
            posted_at=datetime.now(UTC) - timedelta(days=4),
            status=JobStatus.ARCHIVED,
        ),
    ]
    session.commit()
    return jobs


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Python", ["Senior Python Developer", "Machine Learning Engineer"]),
        ("FastAPI", ["Senior Python Developer"]),
        ("AI Startup", ["Data Scientist"]),
        ("Remote", ["Machine Learning Engineer"]),
        ("python pytorch", ["Machine Learning Engineer"]),
        ("missing", []),
    ],
)
def test_searches_all_fields_with_and_semantics(searchable_jobs, query, expected):
    rows = JobService().list_jobs(JobFilters(query=query))
    assert [job.title for job, _ in rows] == expected


def test_empty_query_returns_all_active_jobs(searchable_jobs):
    rows = JobService().list_jobs(JobFilters(query=""))
    assert [job.title for job, _ in rows] == [
        "Senior Python Developer",
        "Machine Learning Engineer",
        "Data Scientist",
    ]

    rows = JobService().list_jobs(JobFilters(query="   "))
    assert [job.title for job, _ in rows] == [
        "Senior Python Developer",
        "Machine Learning Engineer",
        "Data Scientist",
    ]


def test_search_reuses_job_filters(searchable_jobs):
    service = JobService()
    assert [
        job.title
        for job, _ in service.list_jobs(
            JobFilters(query="Python", company=["Tech Corp"])
        )
    ] == ["Senior Python Developer", "Machine Learning Engineer"]
    assert [
        job.title
        for job, _ in service.list_jobs(JobFilters(query="Python", salary_min=200_000))
    ] == ["Machine Learning Engineer"]
    assert [
        job.title
        for job, _ in service.list_jobs(
            JobFilters(query="Developer", include_archived=True)
        )
    ] == ["Senior Python Developer", "Frontend Developer"]


def test_company_filter_count_limit_and_offset_are_applied(searchable_jobs):
    service = JobService()
    filters = JobFilters(query="Python", company=["Tech Corp"])
    results = service.list_jobs(filters, limit=1)
    assert len(results) == 1
    assert results[0][1] == "Tech Corp"
    assert service.count_jobs(filters) == 2
    second_page = service.list_jobs(filters, limit=1, offset=1)
    assert second_page[0][0].id != results[0][0].id


def test_search_treats_wildcards_as_literal_text(searchable_jobs):
    assert JobService().list_jobs(JobFilters(query="%")) == []
    assert JobService().list_jobs(JobFilters(query="_")) == []


@pytest.mark.parametrize("limit", [0, 1001])
def test_search_rejects_invalid_limit(searchable_jobs, limit):
    with pytest.raises(ValueError, match="limit"):
        JobService().list_jobs(limit=limit)


def test_search_rejects_invalid_offset(searchable_jobs):
    with pytest.raises(ValueError, match="offset"):
        JobService().list_jobs(offset=-1)


def test_search_propagates_database_errors():
    with (
        patch(
            "jobpilot.services.job_service.db_session",
            side_effect=OperationalError("statement", {}, RuntimeError("offline")),
        ),
        pytest.raises(OperationalError),
    ):
        JobService().list_jobs(JobFilters(query="Python"))


def test_global_search_service_uses_canonical_default():
    assert isinstance(job_service, JobService)
