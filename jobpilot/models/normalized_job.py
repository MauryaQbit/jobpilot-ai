"""The normalized job model - the canonical pipeline payload.

Every job discovered by any source is converted into a :class:`NormalizedJob`
before deduplication, analysis, matching, and persistence. The model enforces
validation rules and handles missing provider values safely.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from jobpilot.models.enums import (
    Currency,
    EmploymentType,
    ExperienceLevel,
    JobSite,
    RemoteType,
)
from jobpilot.utils.formatters import parse_salary
from jobpilot.utils.text import (
    job_fingerprint,
    normalize_company_name,
    parse_domain_from_url,
    slugify,
)

MIN_YEAR = 1990


def _safe_datetime(value: object) -> datetime | None:
    """Convert a date/datetime/string to a UTC-aware datetime or None."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, datetime.min.time(), tzinfo=UTC)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return None


class NormalizedJob(BaseModel):
    """A validated, canonical job record.

    Attributes:
        source: Which job-board source produced the job.
        source_job_id: Provider-owned identifier (may be empty when absent).
        title: Normalized job title.
        company: Normalized company name.
        location: Human-readable location string.
        remote_type: Remote, hybrid, or on-site classification.
        employment_type: Full-time, contract, etc.
        description: Full job description text (may be empty).
        requirements: Required qualifications extracted during normalization.
        responsibilities: Job responsibilities extracted during normalization.
        skills: Provider- or heuristically-provided skill names.
        salary_min / salary_max: Annualized salary bounds in ``salary_currency``.
        salary_currency: ISO currency code.
        experience_level: Normalized seniority bucket when identifiable.
        education: Education requirement text when present.
        url: Canonical listing URL (direct application URL wins).
        application_url: Application URL when distinct from the listing URL.
        posted_at: When the job was posted (UTC).
        discovered_at: When the pipeline discovered the job (UTC).
        company_domain: Bare domain derived from company URLs.
        job_hash: Deterministic content fingerprint for deduplication.
        metadata: Free-form provider and pipeline metadata.
    """

    source: JobSite
    source_job_id: str = ""
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    location: str = ""
    remote_type: RemoteType = RemoteType.ONSITE
    employment_type: EmploymentType | None = None
    description: str = ""
    requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: Currency | None = None
    experience_level: ExperienceLevel | None = None
    education: str | None = None
    url: str = Field(min_length=1)
    application_url: str | None = None
    posted_at: datetime | None = None
    discovered_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))
    company_domain: str | None = None
    job_hash: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)
    id: int | None = None

    @field_validator("title", "company", "location", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("requirements", "responsibilities", "skills", mode="before")
    @classmethod
    def _normalize_string_lists(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.splitlines() if item.strip()]
        if isinstance(value, tuple | set):
            return list(value)
        return value

    @field_validator("posted_at", "discovered_at", mode="before")
    @classmethod
    def _normalize_datetime(cls, value: object) -> datetime | None:
        return _safe_datetime(value)

    @field_validator("salary_min", "salary_max", mode="before")
    @classmethod
    def _normalize_salary_number(cls, value: object) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(float(str(value).strip()))
        except (ValueError, TypeError):
            return None

    @field_validator("salary_currency", mode="before")
    @classmethod
    def _normalize_currency(cls, value: object) -> Currency | None:
        if value is None:
            return None
        return Currency.normalize(str(value))

    @field_validator("employment_type", mode="before")
    @classmethod
    def _normalize_employment(cls, value: object) -> EmploymentType | None:
        if value is None:
            return None
        return EmploymentType.normalize(str(value))

    @field_validator("remote_type", mode="before")
    @classmethod
    def _normalize_remote(cls, value: object) -> RemoteType:
        if isinstance(value, RemoteType):
            return value
        return RemoteType.normalize(str(value)) or RemoteType.ONSITE

    @field_validator("experience_level", mode="before")
    @classmethod
    def _normalize_experience(cls, value: object) -> ExperienceLevel | None:
        if value is None:
            return None
        return ExperienceLevel.normalize(str(value))

    @field_validator("source", mode="before")
    @classmethod
    def _normalize_source(cls, value: object) -> JobSite:
        if isinstance(value, JobSite):
            return value
        return JobSite.normalize(str(value)) or JobSite.LINKEDIN

    @field_validator("url", "application_url", mode="before")
    @classmethod
    def _strip_url(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def finalize(self) -> NormalizedJob:
        if not self.title.strip():
            raise ValueError("Job title cannot be empty")
        if not self.company.strip():
            raise ValueError("Job company cannot be empty")
        if not self.url.strip():
            raise ValueError("Job URL cannot be empty")

        self.company = normalize_company_name(self.company)
        self.title = (
            slugify(self.title).title()
            if not self.title[0].isupper()
            else " ".join(self.title.split())
        )

        if not self.remote_type and self.location:
            self.remote_type = RemoteType.from_flags(None, self.location)

        if self.salary_min is not None and self.salary_max is not None:
            lower, upper = sorted((self.salary_min, self.salary_max))
            self.salary_min, self.salary_max = lower, upper

        if not self.job_hash:
            self.job_hash = job_fingerprint(
                title=self.title,
                company=self.company,
                location=self.location,
                description=self.description,
            )
        if not self.company_domain:
            self.company_domain = parse_domain_from_url(self.url)
        return self

    @classmethod
    def from_posting(
        cls, posting: Any, *, source: JobSite | None = None
    ) -> NormalizedJob:
        """Build a normalized job from a provider posting with safe defaults."""
        source = source or posting.site
        url = posting.job_url_direct or posting.job_url
        domain = parse_domain_from_url(
            posting.company_url_direct or posting.company_url or url
        )
        min_amount, max_amount = parse_salary(
            (posting.min_amount, posting.max_amount)
            if posting.min_amount or posting.max_amount
            else None
        )
        return cls(
            source=source,
            source_job_id=str(posting.id or ""),
            title=posting.title,
            company=posting.company or "",
            location=posting.location or "",
            remote_type=posting.location_type,
            employment_type=posting.job_type,
            description=posting.description or "",
            skills=[str(skill) for skill in (posting.skills or [])],
            salary_min=min_amount,
            salary_max=max_amount,
            salary_currency=Currency.normalize(posting.currency),
            education=posting.experience_range,
            url=url or "",
            application_url=posting.job_url_direct or posting.job_url,
            posted_at=_safe_datetime(posting.date_posted),
            company_domain=domain,
        )
