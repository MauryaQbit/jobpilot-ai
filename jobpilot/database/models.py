"""Canonical SQLModel tables for JobPilot AI.

Table ownership:

- ``companies``: normalized company identities referenced by jobs
- ``jobs``: normalized job postings with analysis and match support
- ``job_analyses``: structured AI analysis per job
- ``candidate_profiles``: candidate profiles used by the matching engine
- ``job_matches``: cached matching results per (job, profile) pair
- ``applications``: application-tracking records (saved/applied/interview/offer/...)
- ``saved_searches``: repeatable scrape definitions and run health
- ``scraper_runs``: observability records for every discovery run
- ``cost_entries``: operational cost records (preserved from the derived project)
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import field_validator
from sqlalchemy import JSON, CheckConstraint, Column, String
from sqlalchemy.orm import registry
from sqlmodel import Field, SQLModel

from jobpilot.core_utils import ensure_timezone_aware
from jobpilot.models.enums import (
    ApplicationStage,
    Currency,
    EmploymentType,
    ExperienceLevel,
    JobSite,
    JobStatus,
    RemoteType,
    SavedSearchRunStatus,
    ScraperRunStatus,
)


class AppSQLModel(SQLModel, registry=registry()):
    """Application-owned SQLModel base with a reload-safe table registry."""


class CostEntry(AppSQLModel, table=True):
    """One operational cost recorded in the application database."""

    __tablename__ = "cost_entries"
    __table_args__ = (
        CheckConstraint("cost_usd >= 0", name="cost_usd_nonnegative"),
        CheckConstraint("length(trim(service)) > 0", name="service_not_blank"),
        CheckConstraint("length(trim(operation)) > 0", name="operation_not_blank"),
    )

    id: int | None = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    service: str = Field(index=True, min_length=1)
    operation: str = Field(min_length=1)
    cost_usd: float = Field(ge=0)
    extra_data: dict[str, object] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def normalize_timestamp(cls, value) -> datetime | None:
        return ensure_timezone_aware(value)

    @field_validator("cost_usd")
    @classmethod
    def reject_non_finite_cost(cls, value: float) -> float:
        if not value == value or value in (float("inf"), float("-inf")):
            raise ValueError("cost_usd must be a finite number")
        return value

    @classmethod
    def create_validated(cls, **data: object) -> CostEntry:
        return cls.model_validate(data)


class Company(AppSQLModel, table=True):
    """Normalized company identity derived from persisted jobs."""

    __tablename__ = "companies"
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),)

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True, min_length=1)
    url: str | None = None
    domain: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Job(AppSQLModel, table=True):
    """Normalized job posting with analysis and matching support."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        CheckConstraint("length(trim(url)) > 0", name="url_not_blank"),
        CheckConstraint(
            "salary_min IS NULL OR salary_min >= 0",
            name="salary_min_nonnegative",
        ),
        CheckConstraint(
            "salary_max IS NULL OR salary_max >= 0",
            name="salary_max_nonnegative",
        ),
    )

    model_config = {"validate_assignment": True}

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    source: JobSite = Field(
        default=JobSite.LINKEDIN,
        sa_column=Column(String, nullable=False, index=True),
    )
    source_job_id: str = Field(default="", index=True)
    title: str = Field(index=True, min_length=1)
    location: str = Field(default="", index=True)
    remote_type: RemoteType = Field(
        default=RemoteType.ONSITE,
        sa_column=Column(String, nullable=False, index=True),
    )
    employment_type: EmploymentType | None = Field(
        default=None,
        sa_column=Column(String, nullable=True, index=True),
    )
    description: str = ""
    requirements: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    responsibilities: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    skills: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    salary_min: int | None = Field(default=None, index=True)
    salary_max: int | None = Field(default=None, index=True)
    salary_currency: Currency | None = Field(
        default=None,
        sa_column=Column(String, nullable=True),
    )
    experience_level: ExperienceLevel | None = Field(
        default=None,
        sa_column=Column(String, nullable=True, index=True),
    )
    education: str | None = None
    url: str = Field(unique=True, min_length=1)
    application_url: str | None = None
    company_domain: str | None = Field(default=None, index=True)
    job_hash: str = Field(default="", index=True)
    job_metadata: dict[str, object] = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )
    posted_at: datetime | None = Field(default=None, index=True)
    discovered_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), index=True
    )
    last_seen: datetime | None = Field(default=None, index=True)
    status: JobStatus = Field(
        default=JobStatus.ACTIVE,
        sa_column=Column(String, nullable=False, index=True),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator(
        "posted_at", "discovered_at", "last_seen", "created_at", mode="before"
    )
    @classmethod
    def ensure_timezone_aware(cls, value) -> datetime | None:
        return ensure_timezone_aware(value)

    @classmethod
    def create_validated(cls, **data) -> Job:
        return cls.model_validate(data)


class JobAnalysisRow(AppSQLModel, table=True):
    """Structured AI analysis cached for one job."""

    __tablename__ = "job_analyses"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id", index=True, unique=True)
    summary: str = ""
    required_skills: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    preferred_skills: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    programming_languages: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    frameworks: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    cloud: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    databases: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    years_experience: int | None = None
    education: str | None = None
    seniority: ExperienceLevel | None = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    employment_type: EmploymentType | None = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    remote_type: RemoteType | None = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: Currency | None = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    responsibilities: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    preferred_qualifications: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provider: str = "offline"
    model: str | None = None
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    raw: dict[str, object] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )

    @field_validator("analyzed_at", mode="before")
    @classmethod
    def normalize_analyzed_at(cls, value) -> datetime | None:
        return ensure_timezone_aware(value)


class CandidateProfileRow(AppSQLModel, table=True):
    """One candidate profile used by the matching engine."""

    __tablename__ = "candidate_profiles"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="My Profile", min_length=1)
    skills: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    years_experience: int | None = None
    education: str | None = None
    preferred_locations: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    remote_preference: RemoteType | None = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    preferred_roles: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    preferred_companies: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    salary_expectation_min: int | None = None
    salary_expectation_max: int | None = None
    salary_currency: Currency | None = Field(
        default=None, sa_column=Column(String, nullable=True)
    )
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JobMatchRow(AppSQLModel, table=True):
    """Cached matching result for one (job, profile) pair."""

    __tablename__ = "job_matches"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="score_bounds"),
        CheckConstraint("scored_at IS NOT NULL", name="scored_at_present"),
    )

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id", index=True)
    profile_id: int = Field(foreign_key="candidate_profiles.id", index=True)
    score: float = Field(ge=0.0, le=100.0, index=True)
    skill_match: float = Field(default=0.0)
    experience_match: float = Field(default=0.0)
    role_match: float = Field(default=0.0)
    location_match: float = Field(default=0.0)
    remote_match: float = Field(default=0.0)
    salary_match: float = Field(default=0.0)
    seniority_match: float = Field(default=0.0)
    matched_skills: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    missing_skills: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    reasons: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    warnings: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    scored_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)


class Application(AppSQLModel, table=True):
    """Application-tracking record for a (job, profile) pair.

    A record transitions through the canonical :class:`ApplicationStage` states.
    A job the user has saved but not applied to is an application record with
    status ``Saved``, so saved jobs never duplicate persisted job data.
    """

    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint("length(trim(notes)) >= 0", name="notes_valid"),
        CheckConstraint(
            "status IN ('Inbox', 'Saved', 'Applied', 'Screening', "
            "'Interview', 'Offer', 'Rejected')",
            name="application_stage",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id", index=True)
    profile_id: int | None = Field(
        default=None, foreign_key="candidate_profiles.id", index=True
    )
    status: ApplicationStage = Field(
        default=ApplicationStage.SAVED,
        sa_column=Column(String, nullable=False, index=True),
    )
    saved_at: datetime | None = Field(default=None, index=True)
    applied_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    notes: str = ""

    @field_validator("saved_at", "applied_at", "updated_at", mode="before")
    @classmethod
    def normalize_dates(cls, value) -> datetime | None:
        return ensure_timezone_aware(value)


class SavedSearch(AppSQLModel, table=True):
    """A user-owned, repeatable scrape definition and its latest run health."""

    __tablename__ = "saved_searches"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(query)) > 0", name="query_not_blank"),
        CheckConstraint("results_limit BETWEEN 1 AND 1000", name="results_limit"),
        CheckConstraint("jobs_seen >= 0", name="jobs_seen_nonnegative"),
        CheckConstraint("jobs_new >= 0", name="jobs_new_nonnegative"),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="duration_ms_nonnegative",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True, min_length=1)
    query: str = Field(min_length=1)
    location: str = Field(default="United States", min_length=1)
    sites: list[JobSite] = Field(
        default_factory=lambda: [JobSite.LINKEDIN, JobSite.INDEED],
        sa_column=Column(JSON, nullable=False),
    )
    remote_only: bool = False
    job_type: EmploymentType | None = None
    results_limit: int = Field(default=50, ge=1, le=1000)
    enabled: bool = Field(default=True, index=True)
    last_run_at: datetime | None = None
    last_run_status: SavedSearchRunStatus = Field(
        default=SavedSearchRunStatus.NEVER,
        sa_column=Column(String, nullable=False, index=True),
    )
    jobs_seen: int = Field(default=0, ge=0)
    jobs_new: int = Field(default=0, ge=0)
    jobs_duplicates: int = Field(default=0, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    last_error: str | None = None


class ScraperRun(AppSQLModel, table=True):
    """Observability record for one discovery pipeline run."""

    __tablename__ = "scraper_runs"
    __table_args__ = (
        CheckConstraint("jobs_seen >= 0", name="jobs_seen_nonnegative"),
        CheckConstraint("jobs_new >= 0", name="jobs_new_nonnegative"),
        CheckConstraint("jobs_duplicates >= 0", name="jobs_duplicates_nonnegative"),
        CheckConstraint("jobs_rejected >= 0", name="jobs_rejected_nonnegative"),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="duration_ms_nonnegative",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    search_term: str | None = None
    location: str | None = None
    remote_only: bool = False
    job_type: str | None = None
    status: ScraperRunStatus = Field(
        default=ScraperRunStatus.RUNNING,
        sa_column=Column(String, nullable=False, index=True),
    )
    jobs_seen: int = Field(default=0, ge=0)
    jobs_new: int = Field(default=0, ge=0)
    jobs_duplicates: int = Field(default=0, ge=0)
    jobs_rejected: int = Field(default=0, ge=0)
    jobs_analyzed: int = Field(default=0, ge=0)
    jobs_matched: int = Field(default=0, ge=0)
    duration_ms: int | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    finished_at: datetime | None = None
    error: str | None = None
    run_metadata: dict[str, object] = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )

    @field_validator("started_at", "finished_at", mode="before")
    @classmethod
    def normalize_dates(cls, value) -> datetime | None:
        return ensure_timezone_aware(value)
