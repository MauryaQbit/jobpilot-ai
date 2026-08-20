"""Matching service - compute and persist job/profile compatibility."""

from __future__ import annotations

import logging

from sqlmodel import Session, select

from jobpilot.database.engine import db_session
from jobpilot.database.models import Job, JobMatchRow
from jobpilot.matching.engine import MatchingEngine, get_matching_engine
from jobpilot.models.analysis import JobAnalysis
from jobpilot.models.candidate import CandidateProfile
from jobpilot.models.match import MatchResult
from jobpilot.models.normalized_job import NormalizedJob
from jobpilot.services.analysis_service import analysis_service
from jobpilot.services.job_service import resolve_company_names

logger = logging.getLogger(__name__)


class MatchingService:
    """Score jobs against a candidate profile and cache the results."""

    def __init__(self, engine: MatchingEngine | None = None) -> None:
        self.engine = engine or get_matching_engine()

    def match_job(
        self, job: Job, profile: CandidateProfile, analysis: JobAnalysis | None = None
    ) -> MatchResult:
        with db_session() as session:
            names = resolve_company_names(session, [job])
        normalized = self._job_to_normalized(job, names.get(job.company_id, ""))
        if analysis is None:
            analysis = analysis_service.get_analysis(job.id)
        result = self.engine.match(normalized, profile, analysis)
        self._persist(job.id, profile.id, result)
        return result

    def match_jobs(
        self,
        jobs: list[Job],
        profile: CandidateProfile,
        *,
        session: Session | None = None,
        minimum_score: float | None = None,
    ) -> list[MatchResult]:
        """Match a batch of jobs, persisting results that clear the minimum."""
        results: list[MatchResult] = []
        if not jobs or profile.id is None:
            return results
        if session is not None:
            return self._match_batch(session, jobs, profile, minimum_score)
        with db_session() as owned_session:
            return self._match_batch(owned_session, jobs, profile, minimum_score)

    def _match_batch(
        self,
        session: Session,
        jobs: list[Job],
        profile: CandidateProfile,
        minimum_score: float | None,
    ) -> list[MatchResult]:
        results: list[MatchResult] = []
        names = resolve_company_names(session, jobs)
        for job in jobs:
            try:
                analysis = analysis_service.get_analysis(job.id)
                normalized = self._job_to_normalized(job, names.get(job.company_id, ""))
                result = self.engine.match(normalized, profile, analysis)
                if minimum_score is None or result.score >= minimum_score:
                    self._persist(job.id, profile.id, result, session=session)
                    results.append(result)
            except Exception:
                logger.exception("Matching failed for job %s", job.id)
        return results

    @staticmethod
    def _persist(
        job_id: int,
        profile_id: int | None,
        result: MatchResult,
        *,
        session: Session | None = None,
    ) -> None:
        if profile_id is None:
            return
        payload = {
            "job_id": job_id,
            "profile_id": profile_id,
            "score": result.score,
            "skill_match": result.breakdown.skill_match,
            "experience_match": result.breakdown.experience_match,
            "role_match": result.breakdown.role_match,
            "location_match": result.breakdown.location_match,
            "remote_match": result.breakdown.remote_match,
            "salary_match": result.breakdown.salary_match,
            "seniority_match": result.breakdown.seniority_match,
            "matched_skills": result.matched_skills,
            "missing_skills": result.missing_skills,
            "reasons": result.reasons,
            "warnings": result.warnings,
            "scored_at": result.computed_at,
        }

        def _upsert(bound_session: Session) -> None:
            existing = bound_session.exec(
                select(JobMatchRow).where(
                    JobMatchRow.job_id == job_id,
                    JobMatchRow.profile_id == profile_id,
                )
            ).first()
            if existing is None:
                bound_session.add(JobMatchRow(**payload))
            else:
                for key, value in payload.items():
                    setattr(existing, key, value)

        if session is not None:
            _upsert(session)
        else:
            with db_session() as owned_session:
                _upsert(owned_session)

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

    def get_match(self, job_id: int, profile_id: int) -> JobMatchRow | None:
        with db_session() as session:
            return session.exec(
                select(JobMatchRow).where(
                    JobMatchRow.job_id == job_id,
                    JobMatchRow.profile_id == profile_id,
                )
            ).first()

    def get_match_map(
        self, profile_id: int, job_ids: list[int]
    ) -> dict[int, JobMatchRow]:
        """Return a job_id -> cached match map for one profile and job set."""
        job_ids = [job_id for job_id in job_ids if job_id]
        if not job_ids:
            return {}
        with db_session() as session:
            rows = session.exec(
                select(JobMatchRow).where(
                    JobMatchRow.profile_id == profile_id,
                    JobMatchRow.job_id.in_(job_ids),
                )
            ).all()
        return {row.job_id: row for row in rows}


matching_service = MatchingService()
