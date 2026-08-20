"""Tests for saved-search orchestration and card-ready run health."""

import asyncio
from datetime import UTC, datetime

import pytest
from jobpilot.models.enums import JobSite, SavedSearchRunStatus
from jobpilot.models.job_posting import JobScrapeRequest
from jobpilot.models.normalized_job import NormalizedJob
from jobpilot.pipeline.orchestrator import PipelineResult
from jobpilot.services.runner import (
    SavedSearchRunInProgressError,
    run_all_enabled,
    run_all_enabled_sync,
    run_saved_search,
)
from jobpilot.services.saved_search_service import (
    SavedSearchCreate,
    saved_search_service,
)
from sqlmodel import select


def _job(slot: int) -> NormalizedJob:
    return NormalizedJob(
        source=JobSite.LINKEDIN,
        source_job_id=f"job-{slot}",
        title=f"AI Engineer {slot}",
        company="Acme",
        url=f"https://example.test/jobs/{slot}",
        description="Build useful systems",
        location="Remote",
        posted_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _pipeline(
    *,
    found: int = 0,
    invalid: int = 0,
    distinct: int | None = None,
    success: bool = True,
    error: str | None = None,
) -> PipelineResult:
    request = JobScrapeRequest(site_name=[JobSite.LINKEDIN], search_term="AI")
    valid = max(found - invalid, 0)
    distinct = min(distinct or valid, valid) or 1
    jobs = [_job(index % distinct) for index in range(valid)] if valid else []
    return PipelineResult(
        source="jobspy",
        request=request,
        jobs=jobs,
        duplicates=[],
        raw_found=found,
        invalid_rows=invalid,
        total_found=found,
        duration_ms=42,
        success=success,
        error=error,
    )


def _create_search(
    name: str,
    *,
    query: str = "AI",
    sites: list[JobSite] | None = None,
    remote_only: bool = False,
    enabled: bool = True,
):
    return saved_search_service.create(
        SavedSearchCreate(
            name=name,
            query=query,
            sites=sites or [JobSite.LINKEDIN],
            remote_only=remote_only,
            enabled=enabled,
        )
    )


@pytest.mark.asyncio
async def test_run_saved_search_returns_success_health(session, monkeypatch):
    search = _create_search(
        "Remote AI",
        query="AI engineer",
        sites=[JobSite.LINKEDIN],
        remote_only=True,
    )
    captured = {}

    def fake_run(request: JobScrapeRequest, source=None):
        captured["request"] = request
        return _pipeline(found=7, distinct=3)

    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run", fake_run
    )

    outcome = await run_saved_search(search.id)

    assert outcome.status is SavedSearchRunStatus.SUCCEEDED
    assert outcome.jobs_seen == 7
    assert outcome.jobs_new == 3
    assert outcome.duration_ms is not None
    request = captured["request"]
    assert request.search_term == "AI engineer"
    assert request.location == "United States"
    assert request.is_remote is True
    assert request.results_wanted == 50
    assert request.site_name == [JobSite.LINKEDIN]


@pytest.mark.asyncio
async def test_run_saved_search_records_failed_result(session, monkeypatch):
    _create_search("AI")
    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run",
        lambda request, source=None: _pipeline(
            success=False, error="provider unavailable"
        ),
    )

    outcome = await run_saved_search(1)

    assert outcome.status is SavedSearchRunStatus.FAILED
    assert outcome.error == "provider unavailable"


@pytest.mark.asyncio
async def test_failed_result_does_not_require_persistence_metadata(
    session, monkeypatch
):
    search = _create_search("AI")
    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run",
        lambda request, source=None: _pipeline(success=False),
    )

    outcome = await run_saved_search(search.id)

    assert outcome is not None
    assert outcome.status is SavedSearchRunStatus.FAILED
    assert outcome.error == "Discovery failed"


@pytest.mark.asyncio
async def test_run_saved_search_records_partial_validation_loss(session, monkeypatch):
    search = _create_search("AI")
    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run",
        lambda request, source=None: _pipeline(found=2, invalid=1),
    )

    outcome = await run_saved_search(search.id)

    assert outcome is not None
    assert outcome.status is SavedSearchRunStatus.PARTIAL
    assert outcome.succeeded is True
    assert outcome.jobs_seen == 2
    assert outcome.jobs_new == 1
    assert outcome.jobs_rejected == 1
    recorded = saved_search_service.get(search.id)
    assert recorded.last_run_status is SavedSearchRunStatus.PARTIAL
    assert recorded.last_error == "1 provider rows rejected"


@pytest.mark.asyncio
async def test_job_persistence_rolls_back_if_terminal_health_cannot_commit(
    session, monkeypatch
):
    from jobpilot.database.models import Job

    search = _create_search("AI")
    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run",
        lambda request, source=None: _pipeline(found=1),
    )
    original_record_run = saved_search_service.record_run
    failed_once = False

    def fail_terminal_once(search_id, *, session=None, **kwargs):
        nonlocal failed_once
        if session is not None and not failed_once:
            failed_once = True
            raise RuntimeError("terminal write failed")
        return original_record_run(search_id, session=session, **kwargs)

    monkeypatch.setattr(saved_search_service, "record_run", fail_terminal_once)

    outcome = await run_saved_search(search.id)

    assert outcome is not None
    assert outcome.status is SavedSearchRunStatus.FAILED
    assert outcome.error == "terminal write failed"
    session.expire_all()
    assert session.exec(select(Job)).all() == []


@pytest.mark.asyncio
async def test_run_saved_search_records_raised_failure(session, monkeypatch):
    _create_search("AI")

    def failing_run(request: JobScrapeRequest, source=None):
        raise ConnectionError("offline")

    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run", failing_run
    )

    outcome = await run_saved_search(1)

    assert outcome is not None
    assert outcome.status is SavedSearchRunStatus.FAILED
    assert outcome.error == "offline"


@pytest.mark.asyncio
async def test_run_saved_search_records_cancellation_and_reraises(session, monkeypatch):
    search = _create_search("AI")

    def cancelling_run(request: JobScrapeRequest, source=None):
        raise asyncio.CancelledError()

    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run", cancelling_run
    )

    with pytest.raises(asyncio.CancelledError):
        await run_saved_search(search.id)

    recorded = saved_search_service.get(search.id)
    assert recorded is not None
    assert recorded.last_run_status is SavedSearchRunStatus.CANCELLED
    assert recorded.last_error == "Run cancelled"


@pytest.mark.asyncio
async def test_run_saved_search_rejects_an_overlapping_run(session, monkeypatch):
    search = _create_search("AI")
    assert saved_search_service.claim_run(search.id, datetime.now(UTC)) is not None
    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run",
        lambda request, source=None: _pipeline(found=1),
    )

    with pytest.raises(SavedSearchRunInProgressError):
        await run_saved_search(search.id)


@pytest.mark.asyncio
async def test_run_saved_search_returns_failed_outcome_for_missing_definition(session):
    outcome = await run_saved_search(404)

    assert outcome is not None
    assert outcome.search is None
    assert outcome.status is SavedSearchRunStatus.FAILED


@pytest.mark.asyncio
async def test_scrape_all_runs_only_enabled_searches(session, monkeypatch):
    _create_search("A")
    _create_search("B")
    _create_search("Disabled", enabled=False)
    results = [_pipeline(found=2), _pipeline(found=1)]
    calls = {"count": 0}

    def fake_run(request: JobScrapeRequest, source=None):
        result = results[min(calls["count"], 1)]
        calls["count"] += 1
        return result

    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run", fake_run
    )

    outcomes = await run_all_enabled()

    assert [outcome.search.name for outcome in outcomes] == ["A", "B"]
    assert [outcome.jobs_new for outcome in outcomes] == [2, 0]
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_scrape_all_skips_an_already_running_search(session, monkeypatch):
    running = _create_search("A")
    _create_search("B")
    assert saved_search_service.claim_run(running.id, datetime.now(UTC)) is not None
    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run",
        lambda request, source=None: _pipeline(found=1),
    )

    outcomes = await run_all_enabled()

    assert [outcome.search.name for outcome in outcomes] == ["B"]


@pytest.mark.asyncio
async def test_scrape_all_without_enabled_searches_is_noop(session, monkeypatch):
    _create_search("Disabled", enabled=False)
    calls = {"count": 0}

    def fake_run(request: JobScrapeRequest, source=None):
        calls["count"] += 1
        return _pipeline(found=1)

    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run", fake_run
    )

    assert await run_all_enabled() == []
    assert calls["count"] == 0


def test_sync_wrapper_returns_same_health_contract(session, monkeypatch):
    _create_search("AI")
    monkeypatch.setattr(
        "jobpilot.pipeline.orchestrator.discovery_pipeline.run",
        lambda request, source=None: _pipeline(found=4, distinct=1),
    )

    outcomes = run_all_enabled_sync()

    assert len(outcomes) == 1
    assert outcomes[0].status is SavedSearchRunStatus.SUCCEEDED
    assert outcomes[0].jobs_seen == 4
    assert outcomes[0].jobs_new == 1
