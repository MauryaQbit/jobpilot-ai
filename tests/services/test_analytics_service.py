"""Analytics over the canonical SQLAlchemy database."""

from datetime import UTC, datetime, timedelta

from jobpilot.database.models import Company, Job
from jobpilot.models.enums import JobStatus
from jobpilot.services.analytics_service import analytics_service
from sqlmodel import Session


def _job_data(**overrides):
    defaults = {
        "title": "ML Engineer",
        "description": "One",
        "url": "https://first.example/1",
        "location": "Remote",
        "posted_at": datetime.now(UTC),
        "salary_min": 100_000,
        "salary_max": 150_000,
    }
    defaults.update(overrides)
    return defaults


def test_job_trends_use_current_database(session: Session) -> None:
    now = datetime.now(UTC)
    first = Company(name="First", url=None)
    session.add(first)
    session.flush()
    session.add_all(
        [
            Job.create_validated(
                company_id=first.id,
                **_job_data(url="https://first.example/1", posted_at=now),
            ),
            Job.create_validated(
                company_id=first.id,
                title="AI Engineer",
                url="https://first.example/2",
                posted_at=now - timedelta(days=1),
                salary_min=120_000,
                salary_max=180_000,
            ),
            Job.create_validated(
                company_id=first.id,
                title="Archived",
                description="Ignored",
                url="https://first.example/3",
                status=JobStatus.ARCHIVED,
            ),
        ]
    )
    session.commit()

    result = analytics_service.job_trends(days=7)

    assert result["status"] == "success"
    assert sum(point["job_count"] for point in result["trends"]) == 2


def test_company_analytics_are_job_derived(session: Session) -> None:
    now = datetime.now(UTC)
    used = Company(name="First", url=None)
    orphan = Company(name="Orphan", url=None)
    session.add_all([used, orphan])
    session.flush()
    session.add_all(
        [
            Job.create_validated(
                company_id=used.id,
                **_job_data(url="https://first.example/1", posted_at=now),
            ),
            Job.create_validated(
                company_id=used.id,
                title="AI Engineer",
                url="https://first.example/2",
                posted_at=now - timedelta(days=1),
                salary_min=120_000,
                salary_max=180_000,
            ),
        ]
    )
    session.commit()

    result = analytics_service.top_companies(limit=10)

    assert [company for company in result] == [
        {"company": "First", "total_jobs": 2, "active_jobs": 2}
    ]


def test_salary_analytics_exclude_archived_jobs(session: Session) -> None:
    now = datetime.now(UTC)
    first = Company(name="First", url=None)
    session.add(first)
    session.flush()
    session.add_all(
        [
            Job.create_validated(
                company_id=first.id,
                **_job_data(url="https://first.example/1", posted_at=now),
            ),
            Job.create_validated(
                company_id=first.id,
                title="AI Engineer",
                url="https://first.example/2",
                posted_at=now - timedelta(days=1),
                salary_min=120_000,
                salary_max=180_000,
            ),
            Job.create_validated(
                company_id=first.id,
                title="Archived",
                description="Ignored",
                url="https://first.example/3",
                status=JobStatus.ARCHIVED,
                salary_min=90_000,
                salary_max=130_000,
            ),
        ]
    )
    session.commit()

    result = analytics_service.salary_stats(days=7)

    assert result == {
        "jobs_with_salary": 2,
        "avg_min_salary": 110_000,
        "avg_max_salary": 165_000,
        "min_salary": 100_000,
        "max_salary": 180_000,
        "analysis_period_days": 7,
    }


def test_status_reports_canonical_engine(session: Session) -> None:
    status = analytics_service.status_report()

    assert status["analytics_method"] == "sqlalchemy"
    assert status["status"] == "active"
    assert "sqlite" in status["database_url"]
