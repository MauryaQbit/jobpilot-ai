"""Company facets are derived from jobs, never scrape configuration."""

from datetime import UTC, datetime, timedelta

from jobpilot.database.models import Company, Job
from jobpilot.models.enums import JobStatus
from jobpilot.services.company_service import company_service
from sqlmodel import Session


def test_company_facets_include_only_companies_with_jobs(session: Session) -> None:
    now = datetime.now(UTC)
    used = Company(name="Used", url="https://used.example")
    orphan = Company(name="Orphan", url=None)
    session.add_all([used, orphan])
    session.flush()
    session.add_all(
        [
            Job.create_validated(
                company_id=used.id,
                title="Current",
                description="Current job",
                url="https://used.example/jobs/current",
                location="Remote",
                posted_at=now,
            ),
            Job.create_validated(
                company_id=used.id,
                title="Archived",
                description="Archived job",
                url="https://used.example/jobs/archived",
                location="Remote",
                posted_at=now - timedelta(days=2),
                status=JobStatus.ARCHIVED,
            ),
        ]
    )
    session.commit()

    facets = company_service.list_companies()

    assert len(facets) == 1
    facet = facets[0]
    assert facet.id == used.id
    assert facet.name == "Used"
    assert facet.url == "https://used.example"
    assert facet.total_jobs == 2
    assert facet.active_jobs == 1
    assert facet.last_job_posted is not None


def test_company_facets_are_empty_without_jobs(session: Session) -> None:
    session.add(Company(name="Not a scrape source", url=None))
    session.commit()

    assert company_service.list_companies() == []
