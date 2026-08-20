"""Tests for database operations and integration.

This module contains comprehensive tests for database functionality including:
- Basic connection testing
- CRUD operations for companies and jobs
- Database constraints and integrity testing
- Transaction rollback testing
- Query filtering and data retrieval
"""

from datetime import UTC, datetime, timedelta

import pytest
from jobpilot.config import ConfigurationError
from jobpilot.database.engine import _create_engine_impl, get_engine
from jobpilot.database.models import Company, Job
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select


@pytest.mark.parametrize("factory", [_create_engine_impl, get_engine])
@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://localhost/jobs",
        "sqlite:garbage",
        "sqlite://host/jobs.db",
        "sqlite://host:invalid/jobs.db",
    ],
)
def test_engine_factories_enforce_sqlite_url_contract(factory, database_url):
    """Explicit URLs cannot bypass the app's SQLite-only contract."""
    with pytest.raises(ConfigurationError):
        factory(database_url)


def test_database_connection(session: Session):
    """Test basic database connection functionality.

    Verifies that the database session can execute a simple query
    and return expected results.
    """
    result = session.exec(select(1))
    assert result.first() == 1


def test_company_crud_operations(session: Session):
    """Test Create, Read, Update, Delete operations for companies.

    Validates that companies can be properly created, retrieved,
    updated, and deleted from the database with correct data persistence.
    """
    company = Company(name="CRUD Co", url="https://crud.co")
    session.add(company)
    session.commit()
    session.refresh(company)

    retrieved = (session.exec(select(Company).where(Company.name == "CRUD Co"))).first()
    assert retrieved.url == "https://crud.co"

    retrieved.url = "https://crud.co/jobs"
    session.commit()

    updated = (session.exec(select(Company).where(Company.name == "CRUD Co"))).first()
    assert updated.url == "https://crud.co/jobs"

    session.delete(updated)
    session.commit()

    deleted = (session.exec(select(Company).where(Company.name == "CRUD Co"))).first()
    assert deleted is None


def test_job_crud_operations(session: Session):
    """Test Create, Read, Update, Delete operations for jobs.

    Validates that jobs can be properly created, retrieved, updated,
    and deleted from the database with proper field handling.
    """
    company = Company(name="CRUD Job Co", url=None)
    session.add(company)
    session.flush()
    job = Job.create_validated(
        company_id=company.id,
        title="CRUD Job",
        description="Test desc",
        url="https://crud.co/job",
        location="Remote",
        posted_at=datetime.now(UTC),
        salary_min=100000,
        salary_max=150000,
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    retrieved = (session.exec(select(Job).where(Job.title == "CRUD Job"))).first()
    assert retrieved.location == "Remote"

    retrieved.salary_max = 160000
    session.commit()

    updated = (session.exec(select(Job).where(Job.title == "CRUD Job"))).first()
    assert updated.salary_max == 160000

    session.delete(updated)
    session.commit()

    deleted = (session.exec(select(Job).where(Job.title == "CRUD Job"))).first()
    assert deleted is None


def test_job_filtering_queries(session: Session):
    """Test database query filtering capabilities.

    Creates sample jobs with different attributes and tests
    filtering by location and date ranges to ensure
    query operations work correctly.
    """
    now = datetime.now(UTC)
    yesterday = now - timedelta(days=1)
    company = Company(name="Filter Co", url=None)
    session.add(company)
    session.flush()

    jobs = [
        Job.create_validated(
            company_id=company.id,
            title="AI Eng",
            description="AI",
            url="a1",
            location="SF",
            posted_at=now,
        ),
        Job.create_validated(
            company_id=company.id,
            title="ML Eng",
            description="ML",
            url="b1",
            location="Remote",
            posted_at=yesterday,
        ),
    ]
    session.add_all(jobs)
    session.commit()

    sf_jobs = (session.exec(select(Job).where(Job.location == "SF"))).all()
    assert len(sf_jobs) == 1

    recent = (session.exec(select(Job).where(Job.posted_at >= yesterday))).all()
    assert len(recent) == 2


def test_database_constraints(session: Session):
    """Test database integrity constraints and unique field validation.

    Verifies that unique constraints are properly enforced for:
    - Company names (must be unique)
    - Job urls (must be unique)
    Ensures IntegrityError is raised when constraints are violated.
    """
    company1 = Company(name="Const Co", url="https://const1.co")
    session.add(company1)
    session.commit()

    company2 = Company(name="Const Co", url="https://const2.co")
    session.add(company2)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    job1 = Job.create_validated(
        company_id=company1.id,
        title="Job1",
        description="Desc",
        url="https://const.co/job",
        location="Loc",
    )
    session.add(job1)
    session.commit()

    job2 = Job.create_validated(
        company_id=company1.id,
        title="Job2",
        description="Desc2",
        url="https://const.co/job",
        location="Loc2",
    )
    session.add(job2)
    with pytest.raises(IntegrityError):
        session.commit()


def test_database_rollback(session: Session):
    """Test transaction rollback functionality using savepoints.

    Creates a company, then uses a savepoint to test that failed
    transactions are properly rolled back without affecting
    previously committed data within the same session.
    """
    # Add and commit company first
    company = Company(name="Rollback Co", url="https://rollback.co")
    session.add(company)
    session.commit()
    session.refresh(company)  # Ensure company.id is available

    # Verify company was added
    companies_before = session.exec(
        select(Company).where(Company.name == "Rollback Co")
    ).all()
    assert len(companies_before) == 1

    # Create savepoint for rollback testing
    savepoint = session.begin_nested()

    try:
        # Add jobs that should be rolled back
        job = Job.create_validated(
            title="Rollback Job",
            description="Desc",
            url="https://rollback.co/job",
            location="Loc",
            company_id=company.id,
        )
        session.add(job)
        session.flush()  # Make sure job is in session but not committed

        # Verify job is in session before rollback
        jobs_before_rollback = session.exec(
            select(Job).where(Job.url.contains("rollback.co"))
        ).all()
        assert len(jobs_before_rollback) == 1

        # Force rollback of the savepoint
        savepoint.rollback()

    except Exception:
        savepoint.rollback()

    # After rollback, jobs should be gone but company should remain
    jobs_after_rollback = session.exec(
        select(Job).where(Job.url.contains("rollback.co"))
    ).all()
    assert len(jobs_after_rollback) == 0

    companies_after_rollback = session.exec(
        select(Company).where(Company.name == "Rollback Co")
    ).all()
    assert len(companies_after_rollback) == 1
