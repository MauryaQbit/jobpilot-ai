"""Simplified test factories using factory-boy best practices.

Essential factories for core models with predictable test data.
No complex traits or realistic data generation - simple, maintainable patterns.

Factories:
- CompanyFactory: Basic company records
- JobFactory: Simple job postings

Key simplifications:
- Standard factory-boy patterns only
- Predictable test data over realistic data
- No complex traits or helper functions
"""

from datetime import UTC, datetime, timedelta

from factory import LazyAttribute, Sequence, SubFactory
from factory.alchemy import SQLAlchemyModelFactory
from jobpilot.database.models import Company, Job
from jobpilot.models.enums import RemoteType


class CompanyFactory(SQLAlchemyModelFactory):
    """Factory for creating Company test records."""

    class Meta:
        """Factory configuration."""

        model = Company
        sqlalchemy_session = None
        sqlalchemy_session_persistence = "flush"

    name = Sequence(lambda n: f"Test Company {n}")
    url = Sequence(lambda n: f"https://company{n}.com/careers")


class JobFactory(SQLAlchemyModelFactory):
    """Factory for creating Job test records."""

    class Meta:
        """Factory configuration."""

        model = Job
        sqlalchemy_session = None
        sqlalchemy_session_persistence = "flush"

    company = SubFactory(CompanyFactory)
    company_id = LazyAttribute(lambda o: o.company.id)

    title = Sequence(lambda n: f"Software Engineer {n}")
    url = Sequence(lambda n: f"https://jobs.test.com/job/{n}")
    description = "Test job description"
    location = "Remote"
    remote_type = RemoteType.REMOTE
    posted_at = datetime.now(UTC) - timedelta(days=1)
    salary_min = 100000
    salary_max = 150000
    job_hash = Sequence(lambda n: f"hash{n}")
    last_seen = datetime.now(UTC)
