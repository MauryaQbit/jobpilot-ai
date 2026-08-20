"""Candidate profile model for the matching engine."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from jobpilot.models.enums import Currency, RemoteType


class CandidateProfile(BaseModel):
    """A candidate's professional profile used for job matching.

    All optional fields default to ``None`` / empty lists so a profile can be
    created incrementally and still produce a valid match score.
    """

    model_config = ConfigDict(validate_assignment=True)

    id: int | None = None
    name: str = "My Profile"
    skills: list[str] = Field(default_factory=list)
    years_experience: int | None = None
    education: str | None = None
    preferred_locations: list[str] = Field(default_factory=list)
    remote_preference: RemoteType | None = None
    preferred_roles: list[str] = Field(default_factory=list)
    preferred_companies: list[str] = Field(default_factory=list)
    salary_expectation_min: int | None = None
    salary_expectation_max: int | None = None
    salary_currency: Currency | None = None
    is_active: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator(
        "skills",
        "preferred_locations",
        "preferred_roles",
        "preferred_companies",
        mode="before",
    )
    @classmethod
    def _normalize_lists(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, tuple | set):
            return list(value)
        return value

    @field_validator("years_experience", mode="before")
    @classmethod
    def _normalize_years(cls, value: object) -> int | None:
        if value is None or value == "":
            return None
        try:
            number = int(float(str(value).strip()))
        except (ValueError, TypeError):
            return None
        return number if 0 <= number <= 60 else None

    @field_validator("remote_preference", mode="before")
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

    @property
    def normalized_skills(self) -> set[str]:
        return {skill.strip().lower() for skill in self.skills if skill.strip()}

    @property
    def normalized_roles(self) -> set[str]:
        return {role.strip().lower() for role in self.preferred_roles if role.strip()}

    @property
    def normalized_companies(self) -> set[str]:
        return {
            company.strip().lower()
            for company in self.preferred_companies
            if company.strip()
        }

    @property
    def normalized_locations(self) -> set[str]:
        return {
            location.strip().lower()
            for location in self.preferred_locations
            if location.strip()
        }

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
