"""Matching and ranking result schemas.

A :class:`MatchResult` captures the structured evidence behind a 0-100 score so
that ranking explanations are generated from data rather than fabricated text.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from jobpilot.models.analysis import JobAnalysis
from jobpilot.models.normalized_job import NormalizedJob


class ScoreBreakdown(BaseModel):
    """Weighted scoring dimensions behind a match score."""

    skill_match: float = Field(default=0.0, ge=0.0, le=100.0)
    experience_match: float = Field(default=0.0, ge=0.0, le=100.0)
    role_match: float = Field(default=0.0, ge=0.0, le=100.0)
    location_match: float = Field(default=0.0, ge=0.0, le=100.0)
    remote_match: float = Field(default=0.0, ge=0.0, le=100.0)
    salary_match: float = Field(default=0.0, ge=0.0, le=100.0)
    seniority_match: float = Field(default=0.0, ge=0.0, le=100.0)

    def weighted_sum(self, weights: dict[str, float]) -> float:
        total = 0.0
        for key, weight in weights.items():
            total += getattr(self, key, 0.0) * weight
        return total


class MatchResult(BaseModel):
    """The full result of matching one job against a candidate profile."""

    job: NormalizedJob
    analysis: JobAnalysis | None = None
    score: float = Field(ge=0.0, le=100.0)
    breakdown: ScoreBreakdown
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_strong_match(self) -> bool:
        return self.score >= 80

    def explanation_text(self) -> str:
        """Render the structured reasons as a readable explanation."""
        if not self.reasons:
            return "No specific reasons available."
        return " ".join(self.reasons)
