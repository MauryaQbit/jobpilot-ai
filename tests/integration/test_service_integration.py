"""End-to-end service tests over the canonical SQLAlchemy database."""

from datetime import date

import pytest
from jobpilot.models.enums import JobSite, SavedSearchRunStatus
from jobpilot.models.job_posting import JobPosting, JobScrapeRequest
from jobpilot.pipeline.normalizer import Normalizer
from jobpilot.pipeline.orchestrator import PipelineResult
from jobpilot.services import analytics_service, company_service, job_service
from jobpilot.services.runner import run_saved_search
from jobpilot.services.saved_search_service import (
    SavedSearchCreate,
    saved_search_service,
)


def _pipeline_result(request, *, title: str = "AI Platform Engineer"):
    posting = JobPosting(
        id="linkedin-123",
        site=JobSite.LINKEDIN,
        title=title,
        company="Signal Labs",
        company_url="https://signal.example",
        job_url="https://signal.example/jobs/123",
        location="Remote",
        date_posted=date.today(),
        min_amount=150_000,
        max_amount=210_000,
        description="Build the platform",
    )
    return PipelineResult(
        source="jobspy",
        request=request,
        jobs=[Normalizer().normalize_posting(posting)],
        duplicates=[],
        raw_found=1,
        invalid_rows=0,
        total_found=1,
        duration_ms=42,
        success=True,
    )


def _create_search(name: str, *, query: str = "AI", results_limit: int | None = None):
    return saved_search_service.create(
        SavedSearchCreate(
            name=name,
            query=query,
            location="United States",
            sites=[JobSite.LINKEDIN],
            remote_only=True,
            results_limit=results_limit or 50,
        )
    )


@pytest.mark.asyncio
async def test_saved_search_run_drives_persistence_facets_and_analytics(
    session, monkeypatch
):
    search = _create_search("Remote AI roles", query="AI platform engineer")
    captured = {}

    def fake_run(request: JobScrapeRequest, source=None):
        captured["request"] = request
        return _pipeline_result(request)

    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run", fake_run
    )

    outcome = await run_saved_search(search.id)

    assert outcome is not None
    assert outcome.status is SavedSearchRunStatus.SUCCEEDED
    assert outcome.jobs_seen == 1
    assert outcome.jobs_new == 1
    assert outcome.error is None
    assert outcome.duration_ms is not None

    sent = captured["request"]
    assert sent.search_term == "AI platform engineer"
    assert sent.is_remote is True
    assert sent.results_wanted == 50

    rows = job_service.list_jobs()
    assert len(rows) == 1
    assert rows[0][1] == "signal labs"
    assert rows[0][0].posted_at is not None

    companies = company_service.list_companies()
    assert len(companies) == 1
    assert companies[0].name == "signal labs"
    assert companies[0].total_jobs == 1
    assert companies[0].active_jobs == 1

    trends = analytics_service.job_trends()
    salary = analytics_service.salary_stats()
    assert trends["status"] == "success"
    assert sum(item["job_count"] for item in trends["trends"]) == 1
    assert salary["avg_min_salary"] == 150_000
    assert salary["avg_max_salary"] == 210_000


@pytest.mark.asyncio
async def test_repeat_run_reports_no_new_jobs(session, monkeypatch):
    _create_search("AI")
    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run",
        lambda request, source=None: _pipeline_result(request),
    )

    first = await run_saved_search(1)
    second = await run_saved_search(1)

    assert first is not None and first.jobs_new == 1
    assert second is not None and second.jobs_new == 0
    assert len(job_service.list_jobs()) == 1


@pytest.mark.asyncio
async def test_failed_run_records_stable_health(session, monkeypatch):
    _create_search("AI")

    def failing_run(request: JobScrapeRequest, source=None):
        raise ConnectionError("provider unavailable")

    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run", failing_run
    )

    outcome = await run_saved_search(1)

    assert outcome is not None
    assert outcome.status is SavedSearchRunStatus.FAILED
    assert outcome.jobs_seen == 0
    assert outcome.jobs_new == 0
    assert outcome.error == "provider unavailable"


@pytest.mark.asyncio
async def test_scraper_failure_result_is_not_reported_as_success(session, monkeypatch):
    _create_search("AI")
    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run",
        lambda request, source=None: PipelineResult(
            source="jobspy",
            request=request,
            jobs=[],
            duplicates=[],
            total_found=0,
            duration_ms=42,
            success=False,
            error="rate limited",
        ),
    )

    outcome = await run_saved_search(1)

    assert outcome is not None
    assert outcome.status is SavedSearchRunStatus.FAILED
    assert outcome.error == "rate limited"


@pytest.mark.asyncio
async def test_deleting_search_never_deletes_persisted_jobs(session, monkeypatch):
    search = _create_search("AI")
    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run",
        lambda request, source=None: _pipeline_result(request),
    )
    await run_saved_search(search.id)

    assert saved_search_service.delete(search.id) is True
    assert saved_search_service.get(search.id) is None
    assert len(job_service.list_jobs()) == 1


def test_analytics_status_reports_canonical_engine(session):
    status = analytics_service.status_report()
    assert status["analytics_method"] == "sqlalchemy"
    assert status["database_url"].startswith("sqlite:///")
