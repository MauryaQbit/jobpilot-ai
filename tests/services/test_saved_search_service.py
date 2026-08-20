"""Saved-search CRUD and run-health contracts."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from jobpilot.core_utils import ensure_timezone_aware
from jobpilot.database.models import Company, Job, SavedSearch
from jobpilot.models.enums import JobSite, SavedSearchRunStatus
from jobpilot.services.saved_search_service import (
    SavedSearchCreate,
    SavedSearchUpdate,
    saved_search_service,
)
from pydantic import ValidationError
from sqlmodel import Session, select


def test_saved_search_crud_and_health(session: Session) -> None:
    created = saved_search_service.create(
        SavedSearchCreate(
            name="Remote ML",
            query="machine learning engineer",
            sites=[JobSite.LINKEDIN],
            remote_only=True,
        )
    )
    assert created.last_run_status is SavedSearchRunStatus.NEVER

    updated = saved_search_service.update(
        created.id,
        SavedSearchUpdate(results_limit=75, enabled=False),
    )
    assert updated is not None
    assert updated.results_limit == 75
    assert updated.enabled is False

    reported_at = datetime(2026, 7, 14, 12, tzinfo=UTC)
    completed_at = reported_at + timedelta(seconds=5)
    assert saved_search_service.claim_run(created.id, reported_at) is not None
    with patch("jobpilot.services.saved_search_service.datetime") as clock:
        clock.now.return_value = completed_at
        finished = saved_search_service.record_run(
            created.id,
            status=SavedSearchRunStatus.SUCCEEDED,
            started_at=reported_at,
            duration_ms=250,
            jobs_seen=12,
            jobs_new=4,
        )
    assert finished is not None
    assert finished.jobs_seen == 12
    assert finished.jobs_new == 4
    assert finished.last_run_status is SavedSearchRunStatus.SUCCEEDED
    assert ensure_timezone_aware(finished.last_run_at) == completed_at


def test_deleting_search_preserves_jobs(session: Session) -> None:
    search = saved_search_service.create(
        SavedSearchCreate(name="Disposable", query="data engineer")
    )
    company = Company(name="Keep Jobs", url=None)
    session.add(company)
    session.flush()
    job = Job.create_validated(
        company_id=company.id,
        title="Data Engineer",
        description="Keep this",
        url="https://keep.example/jobs/1",
        location="Remote",
    )
    session.add(job)
    session.commit()

    assert saved_search_service.delete(search.id) is True
    assert session.exec(select(SavedSearch)).all() == []
    assert session.exec(select(Job)).all() == [job]


def test_run_claim_is_exclusive_and_old_run_cannot_overwrite_reclaim(
    session: Session,
) -> None:
    search = saved_search_service.create(
        SavedSearchCreate(name="Remote ML", query="ML")
    )
    old_started_at = datetime.now(UTC) - timedelta(hours=1)
    current_started_at = datetime.now(UTC)

    assert saved_search_service.claim_run(search.id, old_started_at) is not None
    assert (
        saved_search_service.claim_run(search.id, old_started_at + timedelta(seconds=1))
        is None
    )
    assert saved_search_service.claim_run(search.id, current_started_at) is not None

    stale_completion = saved_search_service.record_run(
        search.id,
        status=SavedSearchRunStatus.SUCCEEDED,
        started_at=old_started_at,
        duration_ms=0,
    )
    current = saved_search_service.get(search.id)

    assert stale_completion is None
    assert current is not None
    assert current.last_run_status is SavedSearchRunStatus.RUNNING
    assert ensure_timezone_aware(current.last_run_at) == current_started_at


@pytest.mark.parametrize("field", ["name", "query", "location"])
def test_saved_search_updates_reject_blank_text(field: str) -> None:
    with pytest.raises(ValidationError):
        SavedSearchUpdate.model_validate({field: "   "})
