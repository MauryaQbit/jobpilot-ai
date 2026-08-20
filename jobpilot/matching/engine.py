"""Candidate matching engine.

Computes a 0-100 compatibility score between a normalized job and a candidate
profile across configurable weighted dimensions. Every result carries the
structured evidence (breakdown, matched/missing skills, reasons) used to build
explainable ranking output.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from jobpilot.config import DEFAULT_MATCH_WEIGHTS, Settings, get_settings
from jobpilot.models.analysis import JobAnalysis
from jobpilot.models.candidate import CandidateProfile
from jobpilot.models.enums import ExperienceLevel, RemoteType
from jobpilot.models.match import MatchResult, ScoreBreakdown
from jobpilot.models.normalized_job import NormalizedJob

logger = logging.getLogger(__name__)

NEUTRAL = 50.0


class MatchingEngine:
    """Score a job against a candidate profile with configurable weights."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights or dict(DEFAULT_MATCH_WEIGHTS)
        if set(self.weights) != set(DEFAULT_MATCH_WEIGHTS):
            missing = set(DEFAULT_MATCH_WEIGHTS) - set(self.weights)
            raise ValueError(f"Matching weights missing dimensions: {sorted(missing)}")
        if abs(sum(self.weights.values()) - 1.0) > 1e-9:
            raise ValueError("Matching weights must sum to 1.0")

    def match(
        self,
        job: NormalizedJob,
        profile: CandidateProfile,
        analysis: JobAnalysis | None = None,
    ) -> MatchResult:
        breakdown = ScoreBreakdown(
            skill_match=self._skill_match(job, profile, analysis),
            experience_match=self._experience_match(job, profile, analysis),
            role_match=self._role_match(job, profile),
            location_match=self._location_match(job, profile),
            remote_match=self._remote_match(job, profile),
            salary_match=self._salary_match(job, profile),
            seniority_match=self._seniority_match(job, profile, analysis),
        )

        score = breakdown.weighted_sum(self.weights)
        score = round(min(max(score, 0.0), 100.0), 1)

        job_skills = self._job_skill_set(job, analysis)
        profile_skills = profile.normalized_skills
        matched = sorted(job_skills & profile_skills)
        missing = sorted(job_skills - profile_skills)

        reasons = self._build_reasons(
            breakdown=breakdown,
            matched=matched,
            missing=missing,
            job=job,
            profile=profile,
            analysis=analysis,
        )
        warnings = self._build_warnings(job, analysis)

        return MatchResult(
            job=job,
            analysis=analysis,
            score=score,
            breakdown=breakdown,
            matched_skills=matched,
            missing_skills=missing,
            reasons=reasons,
            warnings=warnings,
        )

    # ------------------------------------------------------------- dimensions

    @staticmethod
    def _job_skill_set(job: NormalizedJob, analysis: JobAnalysis | None) -> set[str]:
        skills = {skill.strip().lower() for skill in job.skills if skill.strip()}
        if analysis:
            for field in (
                "required_skills",
                "preferred_skills",
                "programming_languages",
                "frameworks",
                "cloud",
                "databases",
            ):
                skills.update(
                    skill.strip().lower()
                    for skill in getattr(analysis, field)
                    if skill.strip()
                )
        return skills

    @staticmethod
    def _skill_match(
        job: NormalizedJob, profile: CandidateProfile, analysis: JobAnalysis | None
    ) -> float:
        job_skills = MatchingEngine._job_skill_set(job, analysis)
        if not job_skills:
            return NEUTRAL
        profile_skills = profile.normalized_skills
        if not profile_skills:
            return 0.0
        matched = len(job_skills & profile_skills)
        return round(100.0 * matched / len(job_skills), 1)

    @staticmethod
    def _experience_match(
        job: NormalizedJob, profile: CandidateProfile, analysis: JobAnalysis | None
    ) -> float:
        profile_years = profile.years_experience
        required_years = (
            analysis.years_experience
            if analysis and analysis.years_experience is not None
            else None
        )

        if profile_years is None:
            return NEUTRAL if required_years is None else 30.0
        if required_years is not None:
            if profile_years >= required_years:
                return 100.0
            return round(max(10.0, 100.0 * profile_years / required_years), 1)

        job_level = analysis.seniority if analysis else job.experience_level
        if job_level is not None:
            expected = MatchingEngine._years_for_level(job_level)
            if expected and profile_years >= expected:
                return 100.0
            if expected:
                return round(max(10.0, 100.0 * profile_years / expected), 1)
        return NEUTRAL

    @staticmethod
    def _years_for_level(level: ExperienceLevel) -> int:
        mapping = {
            ExperienceLevel.ENTRY: 0,
            ExperienceLevel.JUNIOR: 2,
            ExperienceLevel.MID: 4,
            ExperienceLevel.SENIOR: 6,
            ExperienceLevel.STAFF: 8,
            ExperienceLevel.PRINCIPAL: 10,
            ExperienceLevel.LEAD: 8,
            ExperienceLevel.MANAGER: 8,
        }
        return mapping.get(level, 4)

    @staticmethod
    def _role_match(job: NormalizedJob, profile: CandidateProfile) -> float:
        if not profile.preferred_roles:
            return NEUTRAL
        title = job.title.lower()
        for role in profile.normalized_roles:
            role_tokens = set(role.split())
            title_tokens = set(title.split())
            if role_tokens and role_tokens <= title_tokens:
                return 100.0
            if role in title or title in role:
                return 100.0
            overlap = len(role_tokens & title_tokens)
            if overlap and overlap / max(len(role_tokens), 1) >= 0.5:
                return 80.0
        return 20.0

    @staticmethod
    def _location_match(job: NormalizedJob, profile: CandidateProfile) -> float:
        if not profile.preferred_locations:
            return NEUTRAL
        if job.remote_type == RemoteType.REMOTE:
            return 100.0
        job_location = job.location.lower()
        for preferred in profile.normalized_locations:
            if preferred in job_location or job_location in preferred:
                return 100.0
        return 20.0

    @staticmethod
    def _remote_match(job: NormalizedJob, profile: CandidateProfile) -> float:
        preference = profile.remote_preference
        if preference is None:
            return NEUTRAL
        job_remote = job.remote_type
        if preference == RemoteType.REMOTE:
            if job_remote == RemoteType.REMOTE:
                return 100.0
            if job_remote == RemoteType.HYBRID:
                return 70.0
            return 0.0
        if preference == RemoteType.HYBRID:
            return 100.0 if job_remote == RemoteType.HYBRID else 60.0
        # On-site preference
        return 100.0 if job_remote == RemoteType.ONSITE else 30.0

    @staticmethod
    def _salary_match(job: NormalizedJob, profile: CandidateProfile) -> float:
        expectation = profile.salary_expectation_min
        job_max = job.salary_max or (job.salary_min if job.salary_min else None)
        if expectation is None:
            return NEUTRAL
        if job_max is None:
            return NEUTRAL
        if job_max >= expectation:
            return 100.0
        return round(max(0.0, 100.0 * job_max / expectation), 1)

    @staticmethod
    def _seniority_match(
        job: NormalizedJob, profile: CandidateProfile, analysis: JobAnalysis | None
    ) -> float:
        """Informational seniority alignment (reported, not weighted)."""
        job_level = analysis.seniority if analysis else job.experience_level
        if job_level is None:
            return NEUTRAL
        if profile.years_experience is None:
            return NEUTRAL
        expected = MatchingEngine._years_for_level(job_level)
        if profile.years_experience >= expected:
            return 100.0
        if expected == 0:
            return 100.0
        return round(max(10.0, 100.0 * profile.years_experience / expected), 1)

    # --------------------------------------------------------- explanations

    @staticmethod
    def _build_reasons(
        *,
        breakdown: ScoreBreakdown,
        matched: Sequence[str],
        missing: Sequence[str],
        job: NormalizedJob,
        profile: CandidateProfile,
        analysis: JobAnalysis | None,
    ) -> list[str]:
        reasons: list[str] = []

        if breakdown.skill_match >= 75:
            reasons.append(f"{len(matched)} required technical skills matched")
        elif breakdown.skill_match >= 40:
            reasons.append(
                f"Partial technical skill coverage ({len(matched)} skills matched)"
            )
        elif matched:
            reasons.append(f"Few technical skills matched ({len(matched)})")

        if matched:
            reasons.append(f"Strong alignment on: {', '.join(sorted(matched)[:6])}")

        if missing and breakdown.skill_match < 80:
            reasons.append(
                f"Missing skills to develop: {', '.join(sorted(missing)[:6])}"
            )

        if breakdown.experience_match >= 90:
            reasons.append("Experience requirement met")
        elif (
            analysis
            and analysis.years_experience is not None
            and profile.years_experience is not None
        ):
            reasons.append(
                f"Experience partially matched ({profile.years_experience}y profile vs "
                f"{analysis.years_experience}y required)"
            )

        if breakdown.location_match >= 90:
            reasons.append(f"Location preference matched ({job.location or 'remote'})")

        if breakdown.remote_match >= 90:
            reasons.append("Remote-work preference matched")
        elif breakdown.remote_match < 40 and profile.remote_preference is not None:
            reasons.append("Remote-work preference not aligned")

        if breakdown.salary_match >= 90:
            reasons.append("Salary expectation aligned")
        elif analysis and analysis.salary_min:
            reasons.append("Salary information available for negotiation")

        if breakdown.role_match >= 80:
            reasons.append("Title matches your preferred role")

        return reasons[:8]

    @staticmethod
    def _build_warnings(job: NormalizedJob, analysis: JobAnalysis | None) -> list[str]:
        warnings: list[str] = []
        if not (job.description or "").strip():
            warnings.append("Job description unavailable; analysis limited")
        if analysis is None:
            warnings.append("Job has not been AI-analyzed; skills may be incomplete")
        elif analysis.confidence < 0.6:
            warnings.append("Low confidence in AI analysis")
        if job.salary_min is None and job.salary_max is None:
            warnings.append("No salary information available")
        return warnings


def get_matching_engine(settings: Settings | None = None) -> MatchingEngine:
    settings = settings or get_settings()
    return MatchingEngine(weights=settings.match_weights)


matching_engine = get_matching_engine()
