"""Structured AI job analysis schema.

The AI analysis service must return a :class:`JobAnalysis` conforming to this
schema. Validation is enforced with Pydantic rather than trusting arbitrary
LLM output, and every field has a safe default.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from jobpilot.models.enums import Currency, EmploymentType, ExperienceLevel, RemoteType


class JobAnalysis(BaseModel):
    """Structured insights extracted from a job description.

    Attributes:
        summary: One-paragraph human summary of the role.
        required_skills: Skills the role explicitly requires.
        preferred_skills: Skills listed as nice-to-have or preferred.
        programming_languages: Languages called out in the description.
        frameworks: Frameworks and libraries mentioned.
        cloud: Cloud platforms mentioned (aws, gcp, azure, ...).
        databases: Database technologies mentioned.
        years_experience: Minimum years of experience (None when unspecified).
        education: Education requirement (e.g. "Bachelor's degree").
        seniority: Normalized seniority level.
        employment_type: Normalized employment type.
        remote_type: Remote / hybrid / on-site classification.
        salary_min / salary_max: Annualized salary bounds when present.
        salary_currency: ISO currency code when present.
        responsibilities: Key responsibilities distilled from the description.
        preferred_qualifications: Additional preferred qualifications.
        confidence: 0.0-1.0 confidence in the analysis.
        provider: The analysis provider that produced this result.
        model: The model name used, when applicable.
        analyzed_at: When the analysis was produced.
        raw: Free-form additional signals (validated later).
    """

    summary: str = ""
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    programming_languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    cloud: list[str] = Field(default_factory=list)
    databases: list[str] = Field(default_factory=list)
    years_experience: int | None = None
    education: str | None = None
    seniority: ExperienceLevel | None = None
    employment_type: EmploymentType | None = None
    remote_type: RemoteType | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: Currency | None = None
    responsibilities: list[str] = Field(default_factory=list)
    preferred_qualifications: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provider: str = "offline"
    model: str | None = None
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "required_skills",
        "preferred_skills",
        "programming_languages",
        "frameworks",
        "cloud",
        "databases",
        "responsibilities",
        "preferred_qualifications",
        mode="before",
    )
    @classmethod
    def _normalize_lists(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.splitlines() if item.strip()]
        if isinstance(value, tuple | set):
            return list(value)
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return value

    @field_validator("years_experience", mode="before")
    @classmethod
    def _normalize_years(cls, value: object) -> int | None:
        if value is None or value == "":
            return None
        try:
            number = float(str(value).strip())
        except (ValueError, TypeError):
            return None
        if number < 0 or number > 60:
            return None
        return round(number)

    @field_validator("seniority", mode="before")
    @classmethod
    def _normalize_seniority(cls, value: object) -> ExperienceLevel | None:
        if value is None:
            return None
        return ExperienceLevel.normalize(str(value))

    @field_validator("employment_type", mode="before")
    @classmethod
    def _normalize_employment(cls, value: object) -> EmploymentType | None:
        if value is None:
            return None
        return EmploymentType.normalize(str(value))

    @field_validator("remote_type", mode="before")
    @classmethod
    def _normalize_remote(cls, value: object) -> RemoteType | None:
        if value is None:
            return None
        return RemoteType.normalize(str(value))

    @field_validator("salary_currency", mode="before")
    @classmethod
    def _normalize_currency(cls, value: object) -> Currency | None:
        if value is None:
            return None
        return Currency.normalize(str(value))

    @field_validator("salary_min", "salary_max", mode="before")
    @classmethod
    def _normalize_salary(cls, value: object) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(float(str(value).strip()))
        except (ValueError, TypeError):
            return None

    @model_validator(mode="after")
    def _finalize(self) -> JobAnalysis:
        if self.salary_min is not None and self.salary_max is not None:
            lower, upper = sorted((self.salary_min, self.salary_max))
            self.salary_min, self.salary_max = lower, upper
        return self
