"""Recommendation service - ranked, explainable job suggestions."""

from __future__ import annotations

import logging

from sqlmodel import select

from jobpilot.database.engine import db_session
from jobpilot.database.models import Application, Job, JobMatchRow
from jobpilot.matching.engine import MatchingEngine, get_matching_engine
from jobpilot.models.candidate import CandidateProfile
from jobpilot.models.enums import ApplicationStage
from jobpilot.models.match import MatchResult
from jobpilot.models.normalized_job import NormalizedJob
from jobpilot.ranking.ranker import RankedJob, Ranker
from jobpilot.services.analysis_service import analysis_service
from jobpilot.services.job_service import resolve_company_names

logger = logging.getLogger(__name__)


class RecommendationService:
    """Return ranked job recommendations with structured explanations."""

    def __init__(
        self, engine: MatchingEngine | None = None, ranker: Ranker | None = None
    ) -> None:
        self.engine = engine or get_matching_engine()
        self.ranker = ranker or Ranker()

    def recommend(
        self,
        profile: CandidateProfile,
        *,
        limit: int = 20,
        minimum_score: float | None = None,
        exclude_applied: bool = False,
    ) -> list[RankedJob]:
        """Rank active jobs against a profile and return the top matches."""
        if profile.id is None:
            return []

        with db_session() as session:
            jobs = session.exec(select(Job).where(Job.status == "active")).all()

            applied_job_ids: set[int] = set()
            if exclude_applied:
                rows = session.exec(
                    select(Application.job_id).where(
                        Application.profile_id == profile.id,
                        Application.status.in_(
                            [
                                ApplicationStage.APPLIED,
                                ApplicationStage.SCREENING,
                                ApplicationStage.INTERVIEW,
                                ApplicationStage.OFFER,
                                ApplicationStage.REJECTED,
                            ]
                        ),
                    )
                ).all()
                applied_job_ids = set(rows)

            match_rows = {
                row.job_id: row
                for row in session.exec(
                    select(JobMatchRow).where(JobMatchRow.profile_id == profile.id)
                ).all()
            }
            names = resolve_company_names(session, jobs)

        candidates: list[tuple[Job, JobMatchRow | None]] = [
            (job, match_rows.get(job.id))
            for job in jobs
            if job.id not in applied_job_ids
        ]

        results: list[MatchResult] = []
        for job, match_row in candidates:
            company_name = names.get(job.company_id, "")
            if match_row is not None:
                results.append(self._from_cached(job, match_row, company_name))
            else:
                analysis = analysis_service.get_analysis(job.id)
                normalized = self._job_to_normalized(job, company_name)
                results.append(self.engine.match(normalized, profile, analysis))

        if minimum_score is not None:
            results = [result for result in results if result.score >= minimum_score]

        ranked = self.ranker.rank(results)
        return ranked[:limit]

    @staticmethod
    def _from_cached(job: Job, row: JobMatchRow, company_name: str = "") -> MatchResult:
        from jobpilot.models.match import ScoreBreakdown

        return MatchResult(
            job=RecommendationService._job_to_normalized(job, company_name),
            score=row.score,
            breakdown=ScoreBreakdown(
                skill_match=row.skill_match,
                experience_match=row.experience_match,
                role_match=row.role_match,
                location_match=row.location_match,
                remote_match=row.remote_match,
                salary_match=row.salary_match,
                seniority_match=row.seniority_match,
            ),
            matched_skills=list(row.matched_skills),
            missing_skills=list(row.missing_skills),
            reasons=list(row.reasons),
            warnings=list(row.warnings),
        )

    @staticmethod
    def _job_to_normalized(job: Job, company_name: str = "") -> NormalizedJob:
        from jobpilot.models.normalized_job import NormalizedJob

        return NormalizedJob(
            id=job.id,
            source=job.source,
            source_job_id=job.source_job_id,
            title=job.title,
            company=company_name,
            location=job.location,
            remote_type=job.remote_type,
            employment_type=job.employment_type,
            description=job.description,
            requirements=job.requirements,
            responsibilities=job.responsibilities,
            skills=job.skills,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            salary_currency=job.salary_currency,
            experience_level=job.experience_level,
            education=job.education,
            url=job.url,
            application_url=job.application_url,
            company_domain=job.company_domain,
            job_hash=job.job_hash,
            metadata=job.job_metadata,
            posted_at=job.posted_at,
            discovered_at=job.discovered_at,
        )


recommendation_service = RecommendationService()
