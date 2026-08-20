"""Query and filter models for job discovery and recommendation."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from jobpilot.models.enums import ApplicationStage, EmploymentType, JobSite, RemoteType


class JobFilters(BaseModel):
    """Validated filters for job queries.

    All filters are optional; an unset filter does not constrain results.
    """

    keyword: str | None = None
    role: str | None = None
    company: list[str] = Field(default_factory=list)
    location: str | None = None
    remote: RemoteType | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    experience: list[str] = Field(default_factory=list)
    employment_type: list[EmploymentType] = Field(default_factory=list)
    required_skill: str | None = None
    min_match_score: float | None = Field(default=None, ge=0.0, le=100.0)
    source: list[JobSite] = Field(default_factory=list)
    posted_after: date | None = None
    posted_before: date | None = None
    status: ApplicationStage | None = None
    include_archived: bool = False
    query: str | None = None  # General text search over title/company/location

    @field_validator("remote", mode="before")
    @classmethod
    def normalize_remote(cls, value: object) -> RemoteType | None:
        if value is None:
            return None
        return RemoteType.normalize(str(value))

    @field_validator("employment_type", "source", mode="before")
    @classmethod
    def normalize_enum_lists(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("salary_min", "salary_max", mode="before")
    @classmethod
    def normalize_salary(cls, value: object) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(float(str(value).strip()))
        except (ValueError, TypeError):
            return None

    @field_validator("posted_after", "posted_before", mode="before")
    @classmethod
    def normalize_dates(cls, value: object) -> date | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None

    @property
    def is_empty(self) -> bool:
        return self.model_dump(exclude_none=True, exclude_unset=True) == {}

    def to_filter_dict(self) -> dict[str, object]:
        return self.model_dump(exclude_none=True, exclude_unset=True, mode="json")
