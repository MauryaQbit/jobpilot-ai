"""Integration tests for JobSpy conversion and atomic persistence."""

from datetime import UTC, date, datetime
from unittest.mock import Mock, patch

import pandas as pd
import pytest
from jobpilot.database.models import Application, Job
from jobpilot.models.enums import ApplicationStage, JobSite
from jobpilot.models.job_posting import JobPosting, JobScrapeRequest
from jobpilot.models.normalized_job import NormalizedJob
from jobpilot.pipeline.orchestrator import PipelineResult
from jobpilot.scrapers.jobspy_source import JobSpySource
from jobpilot.services.job_service import JobService
from sqlmodel import select

from tests.factories import CompanyFactory, JobFactory


def _posting(
    *,
    identifier: str,
    url: str,
    title: str = "AI Engineer",
    description: str = "Original description",
) -> JobPosting:
    return JobPosting(
        id=identifier,
        site=JobSite.LINKEDIN,
        title=title,
        company="Acme",
        job_url=url,
        location="Remote",
        date_posted=date.today(),
        description=description,
    )


def _pipeline(jobs: list[NormalizedJob]) -> PipelineResult:
    return PipelineResult(
        source="jobspy",
        request=JobScrapeRequest(site_name=[JobSite.LINKEDIN], search_term="AI"),
        jobs=jobs,
        duplicates=[],
        raw_found=len(jobs),
        invalid_rows=0,
        total_found=len(jobs),
        duration_ms=0,
        success=True,
    )


def test_dataframe_conversion_normalizes_real_jobspy_shapes():
    frame = pd.DataFrame(
        [
            {
                "id": None,
                "site": None,
                "title": " Platform Engineer ",
                "company": " Acme ",
                "job_url": "https://example.com/jobs/1",
                "date_posted": pd.Timestamp("2026-07-14"),
                "emails": "jobs@example.com",
                "skills": ["Python", "SQL"],
                "company_addresses": ("Denver",),
                "min_amount": "120000",
            }
        ]
    )

    jobs, invalid_rows = JobSpySource()._dataframe_to_models(frame, JobSite.LINKEDIN)

    assert len(jobs) == 1
    assert invalid_rows == 0
    job = jobs[0]
    assert job.id == "https://example.com/jobs/1"
    assert job.site is JobSite.LINKEDIN
    assert job.title == "Platform Engineer"
    assert job.company == "Acme"
    assert job.emails == ["jobs@example.com"]
    assert job.skills == ["Python", "SQL"]
    assert job.company_addresses == ["Denver"]
    assert job.min_amount == 120_000


def test_dataframe_conversion_skips_rows_without_persistable_identity():
    frame = pd.DataFrame(
        [
            {
                "id": "valid",
                "site": "linkedin",
                "title": "AI Engineer",
                "company": "Acme",
                "job_url": "https://example.com/valid",
            },
            {
                "id": "missing-company",
                "site": "linkedin",
                "title": "AI Engineer",
                "job_url": "https://example.com/no-company",
            },
            {
                "id": "missing-url",
                "site": "linkedin",
                "title": "AI Engineer",
                "company": "Acme",
            },
            {
                "id": "missing-title",
                "site": "linkedin",
                "title": " ",
                "company": "Acme",
                "job_url": "https://example.com/no-title",
            },
        ]
    )

    jobs, invalid_rows = JobSpySource()._dataframe_to_models(frame, JobSite.LINKEDIN)

    assert [job.id for job in jobs] == ["valid"]
    assert invalid_rows == 3


def test_sync_scrape_returns_explicit_failed_result_on_provider_error():
    request = JobScrapeRequest(
        site_name=JobSite.LINKEDIN,
        search_term="AI Engineer",
    )
    with patch(
        "jobpilot.scrapers.jobspy_source.scrape_jobs",
        side_effect=ConnectionError("offline"),
    ):
        result = JobSpySource().fetch_jobs(request)

    assert result.jobs == []
    assert result.total_found == 0
    assert result.metadata == {
        "scraping_method": "jobspy",
        "success": False,
        "raw_found": 0,
        "valid_rows": 0,
        "invalid_rows": 0,
        "error": "Scraping operation failed",
    }


@pytest.mark.asyncio
async def test_async_scrape_delegates_to_sync_implementation():
    scraper = JobSpySource()
    request = JobScrapeRequest(site_name=JobSite.LINKEDIN, search_term="AI")
    expected = scraper._empty_result(request)
    scraper.fetch_jobs = Mock(return_value=expected)

    assert await scraper.fetch_jobs_async(request) == expected
    scraper.fetch_jobs.assert_called_once_with(request)


def test_scrape_persistence_is_atomic(session):
    company = CompanyFactory(name="Acme")
    session.commit()
    service = JobService()
    jobs = [
        NormalizedJob.from_posting(
            _posting(identifier="one", url="https://example.com/jobs/one")
        ),
        NormalizedJob.from_posting(
            _posting(identifier="two", url="https://example.com/jobs/two")
        ),
    ]
    with (
        patch.object(
            service,
            "_get_or_create_company",
            side_effect=[company.id, RuntimeError("second row failed")],
        ),
        pytest.raises(RuntimeError, match="second row failed"),
    ):
        service.persist_pipeline_result(_pipeline(jobs))

    session.expire_all()
    assert session.exec(select(Job)).all() == []


def test_rescrape_preserves_user_owned_state(session):
    company = CompanyFactory(name="Acme")
    job = JobFactory(
        company=company,
        url="https://example.com/jobs/1",
        title="AI Engineer",
    )
    session.commit()
    now = datetime.now(UTC)
    session.add(
        Application(
            job_id=job.id,
            status=ApplicationStage.APPLIED,
            saved_at=now,
            updated_at=now,
            notes="Warm intro",
        )
    )
    session.commit()

    result = JobService().persist_pipeline_result(
        _pipeline(
            [
                NormalizedJob.from_posting(
                    _posting(
                        identifier="one",
                        url="https://example.com/jobs/1",
                        title="Principal AI Engineer",
                        description="Expanded scope",
                    )
                )
            ]
        )
    )

    assert result == {"inserted": 0, "updated": 1, "skipped": 0, "duplicates": 0}
    session.expire_all()
    refreshed = session.get(Job, job.id)
    assert refreshed is not None
    assert refreshed.title == "Principal AI Engineer"
    assert refreshed.description == "Expanded scope"
    application = session.exec(
        select(Application).where(Application.job_id == job.id)
    ).one()
    assert application.status == ApplicationStage.APPLIED.value
    assert application.notes == "Warm intro"


def test_direct_application_url_is_canonical(session):
    posting = _posting(identifier="one", url="https://listing.example/1")
    posting.job_url_direct = "https://apply.example/1"

    result = JobService().persist_pipeline_result(
        _pipeline([NormalizedJob.from_posting(posting)])
    )

    assert result["inserted"] == 1
    saved = session.exec(select(Job)).one()
    assert saved.url == "https://apply.example/1"
    assert saved.application_url == "https://apply.example/1"
