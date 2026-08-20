"""Explainable ranking engine.

Ranks matched jobs by score and renders structured matching data into
human-readable explanations. Explanations are generated from the evidence in
the :class:`MatchResult` - never fabricated prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jobpilot.models.candidate import CandidateProfile
from jobpilot.models.match import MatchResult
from jobpilot.models.normalized_job import NormalizedJob


@dataclass
class RankedJob:
    """A job ranked for the candidate with its explanation."""

    job: NormalizedJob
    match: MatchResult
    rank: int
    explanation: str = ""
    missing_skills: list[str] = field(default_factory=list)
    matched_skills: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.match.score

    @property
    def is_strong_match(self) -> bool:
        return self.match.is_strong_match


class Ranker:
    """Sort and explain match results for one candidate profile."""

    def rank(self, matches: list[MatchResult]) -> list[RankedJob]:
        ordered = sorted(matches, key=lambda result: result.score, reverse=True)
        return [
            RankedJob(
                job=result.job,
                match=result,
                rank=index + 1,
                explanation=self.explain(result),
                missing_skills=list(result.missing_skills),
                matched_skills=list(result.matched_skills),
            )
            for index, result in enumerate(ordered)
        ]

    @staticmethod
    def explain(result: MatchResult) -> str:
        """Build a structured explanation from matching evidence."""
        lines = [f"Match Score: {result.score:.0f}%"]
        if result.reasons:
            lines.append("Why: " + "; ".join(f"{reason}." for reason in result.reasons))
        if result.missing_skills:
            lines.append("Missing: " + ", ".join(sorted(result.missing_skills)))
        if result.warnings:
            lines.append("Note: " + "; ".join(result.warnings))
        return "\n".join(lines)


def build_explanation_for_profile(
    result: MatchResult,
    profile: CandidateProfile | None = None,
) -> str:
    """Convenience wrapper for callers that only need the explanation text."""
    del profile  # Reserved for profile-aware phrasing.
    return Ranker.explain(result)


ranker = Ranker()
