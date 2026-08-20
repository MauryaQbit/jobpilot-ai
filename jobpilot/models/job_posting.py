"""Provider-facing job posting models.

These models describe a raw job as returned by a job-board source (such as
JobSpy) before normalization. They are the input contract of the discovery
pipeline and are deliberately kept close to the provider data shape.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator

from jobpilot.models.enums import EmploymentType, JobSite, RemoteType


class JobScrapeRequest(BaseModel):
    """Request parameters for a job-board scrape."""

    site_name: list[JobSite] | JobSite = Field(default=JobSite.LINKEDIN)
    search_term: str | None = None
    google_search_term: str | None = None
    location: str | None = None
    distance: int = Field(default=50, ge=0, le=200)
    is_remote: bool = False
    job_type: EmploymentType | None = None
    easy_apply: bool | None = None
    results_wanted: int = Field(default=15, ge=1, le=1000)
    country_indeed: str = "usa"
    offset: int = Field(default=0, ge=0)
    hours_old: int | None = Field(default=None, ge=1)
    enforce_annual_salary: bool = True
    linkedin_fetch_description: bool = False
    description_format: str = "markdown"

    @field_validator("site_name", mode="before")
    @classmethod
    def normalize_site_name(cls, value: Any) -> Any:
        if isinstance(value, str):
            return JobSite.normalize(value) or value
        if isinstance(value, list):
            return [
                JobSite.normalize(site) if isinstance(site, str) else site
                for site in value
            ]
        return value

    @field_validator("job_type", mode="before")
    @classmethod
    def normalize_job_type(cls, value: Any) -> Any:
        if isinstance(value, str):
            return EmploymentType.normalize(value)
        return value


class JobPosting(BaseModel):
    """One raw job posting returned by a source."""

    id: str
    site: JobSite
    job_url: str | None = None
    job_url_direct: str | None = None
    title: str
    company: str | None = None
    location: str | None = None
    date_posted: date | None = None
    job_type: EmploymentType | None = None

    salary_source: str | None = None
    interval: str | None = None
    min_amount: float | None = None
    max_amount: float | None = None
    currency: str | None = None

    is_remote: bool = False
    location_type: RemoteType = RemoteType.ONSITE
    work_from_home_type: str | None = None

    job_level: str | None = None
    job_function: str | None = None
    listing_type: str | None = None
    description: str | None = None
    emails: list[str] | None = None
    skills: list[str] | None = None
    experience_range: str | None = None
    vacancy_count: int | None = None

    company_industry: str | None = None
    company_url: str | None = None
    company_logo: str | None = None
    company_url_direct: str | None = None
    company_addresses: list[str] | None = None
    company_num_employees: str | None = None
    company_revenue: str | None = None
    company_description: str | None = None
    company_rating: float | None = None
    company_reviews_count: int | None = None

    @model_validator(mode="after")
    def require_persistable_identity(self) -> JobPosting:
        self.title = self.title.strip()
        self.company = self.company.strip() if self.company else None
        self.job_url = self.job_url.strip() if self.job_url else None
        self.job_url_direct = (
            self.job_url_direct.strip() if self.job_url_direct else None
        )
        if not self.title:
            raise ValueError("Job title cannot be empty")
        if not self.company:
            raise ValueError("Job company cannot be empty")
        if not (self.job_url_direct or self.job_url):
            raise ValueError("Job URL cannot be empty")
        if "location_type" not in self.model_fields_set:
            self.location_type = RemoteType.from_flags(self.is_remote, self.location)
        return self

    @field_validator("min_amount", "max_amount", "company_rating", mode="before")
    @classmethod
    def safe_float_conversion(cls, value: Any) -> float | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @field_validator("site", mode="before")
    @classmethod
    def normalize_site(cls, value: Any) -> Any:
        if isinstance(value, str):
            return JobSite.normalize(value) or value
        return value

    @field_validator("job_type", mode="before")
    @classmethod
    def normalize_job_type_posting(cls, value: Any) -> Any:
        if isinstance(value, str):
            return EmploymentType.normalize(value)
        return value

    @field_validator("emails", "skills", "company_addresses", mode="before")
    @classmethod
    def normalize_string_lists(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else None
        if isinstance(value, tuple | set):
            return list(value)
        return value


class JobScrapeResult(BaseModel):
    """Complete job scraping result from one source run."""

    jobs: list[JobPosting]
    total_found: int
    request_params: JobScrapeRequest
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_pandas(
        cls,
        df: pd.DataFrame,
        request: JobScrapeRequest,
        metadata: dict[str, Any] | None = None,
    ) -> JobScrapeResult:
        jobs: list[JobPosting] = []
        for _, row in df.iterrows():
            job_data: dict[str, Any] = {}
            for col, value in row.items():
                if pd.api.types.is_scalar(value) and pd.isna(value):
                    job_data[col] = None
                elif isinstance(value, pd.Timestamp | pd.DatetimeIndex):
                    job_data[col] = value.date() if hasattr(value, "date") else None
                else:
                    job_data[col] = value
            jobs.append(JobPosting.model_validate(job_data))

        return cls(
            jobs=jobs,
            total_found=len(jobs),
            request_params=request,
            metadata=metadata or {},
        )

    def to_pandas(self) -> pd.DataFrame:
        if not self.jobs:
            return pd.DataFrame()
        return pd.DataFrame([job.model_dump() for job in self.jobs])

    @property
    def job_count(self) -> int:
        return len(self.jobs)

    def filter_by_location_type(self, location_type: RemoteType) -> JobScrapeResult:
        filtered = [job for job in self.jobs if job.location_type == location_type]
        return self.model_copy(update={"jobs": filtered, "total_found": len(filtered)})

    def filter_by_job_type(self, job_type: EmploymentType) -> JobScrapeResult:
        filtered = [job for job in self.jobs if job.job_type == job_type]
        return self.model_copy(update={"jobs": filtered, "total_found": len(filtered)})
