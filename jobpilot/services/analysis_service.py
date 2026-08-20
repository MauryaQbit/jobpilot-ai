"""AI analysis service - analyze jobs and persist structured results."""

from __future__ import annotations

import logging

from sqlalchemy import func
from sqlmodel import Session, select

from jobpilot.ai.analyzer import JobAnalyzer, job_analyzer
from jobpilot.database.engine import db_session
from jobpilot.database.models import Job, JobAnalysisRow
from jobpilot.models.analysis import JobAnalysis
from jobpilot.services.job_service import resolve_company_names

logger = logging.getLogger(__name__)

type AnalysisStats = dict[str, int]


class AnalysisService:
    """Analyze normalized jobs with the AI layer and cache results."""

    def __init__(self, analyzer: JobAnalyzer | None = None) -> None:
        self.analyzer = analyzer or job_analyzer

    def analyze_job(self, job: Job) -> JobAnalysis:
        """Analyze a persisted job and upsert its structured analysis."""
        with db_session() as session:
            names = resolve_company_names(session, [job])
            normalized = self._job_to_normalized(job, names.get(job.company_id, ""))
        analysis = self.analyzer.analyze(normalized)
        with db_session() as session:
            self._upsert_analysis(session, job.id, analysis)
        return analysis

    def analyze_jobs(
        self, jobs: list[Job], *, session: Session | None = None
    ) -> AnalysisStats:
        """Analyze a batch of jobs, persisting each result."""
        stats: AnalysisStats = {"analyzed": 0, "failed": 0, "skipped": 0}
        if not jobs:
            return stats
        if session is not None:
            return self._analyze_batch(session, jobs, stats)
        with db_session() as owned_session:
            return self._analyze_batch(owned_session, jobs, stats)

    def _analyze_batch(
        self, session: Session, jobs: list[Job], stats: AnalysisStats
    ) -> AnalysisStats:
        names = resolve_company_names(session, jobs)
        for job in jobs:
            try:
                normalized = self._job_to_normalized(job, names.get(job.company_id, ""))
                analysis = self.analyzer.analyze(normalized)
                self._upsert_analysis(session, job.id, analysis)
                stats["analyzed"] += 1
            except Exception:
                logger.exception("Analysis failed for job %s", job.id)
                stats["failed"] += 1
        return stats

    @staticmethod
    def _upsert_analysis(session: Session, job_id: int, analysis: JobAnalysis) -> None:
        existing = session.exec(
            select(JobAnalysisRow).where(JobAnalysisRow.job_id == job_id)
        ).first()
        payload = {
            "job_id": job_id,
            "summary": analysis.summary,
            "required_skills": analysis.required_skills,
            "preferred_skills": analysis.preferred_skills,
            "programming_languages": analysis.programming_languages,
            "frameworks": analysis.frameworks,
            "cloud": analysis.cloud,
            "databases": analysis.databases,
            "years_experience": analysis.years_experience,
            "education": analysis.education,
            "seniority": analysis.seniority,
            "employment_type": analysis.employment_type,
            "remote_type": analysis.remote_type,
            "salary_min": analysis.salary_min,
            "salary_max": analysis.salary_max,
            "salary_currency": analysis.salary_currency,
            "responsibilities": analysis.responsibilities,
            "preferred_qualifications": analysis.preferred_qualifications,
            "confidence": analysis.confidence,
            "provider": analysis.provider,
            "model": analysis.model,
            "analyzed_at": analysis.analyzed_at,
            "raw": analysis.raw,
        }
        if existing is None:
            session.add(JobAnalysisRow(**payload))
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
            existing.analyzed_at = analysis.analyzed_at

    def get_analysis(self, job_id: int) -> JobAnalysis | None:
        with db_session() as session:
            row = session.exec(
                select(JobAnalysisRow).where(JobAnalysisRow.job_id == job_id)
            ).first()
            return self._row_to_model(row) if row else None

    def count_analyzed(self) -> int:
        with db_session() as session:
            return int(session.exec(select(func.count(JobAnalysisRow.id))).one())

    def unanalyzed_jobs(self, *, limit: int = 500, offset: int = 0) -> list[Job]:
        """Return active jobs that have no cached analysis yet."""
        from sqlalchemy.orm import aliased

        analysis = aliased(JobAnalysisRow)
        with db_session() as session:
            statement = (
                select(Job)
                .outerjoin(analysis, analysis.job_id == Job.id)
                .where(Job.status == "active", analysis.id.is_(None))
                .order_by(Job.posted_at.desc().nullslast(), Job.id.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(session.exec(statement).all())

    @staticmethod
    def _row_to_model(row: JobAnalysisRow) -> JobAnalysis:
        return JobAnalysis(
            summary=row.summary,
            required_skills=row.required_skills,
            preferred_skills=row.preferred_skills,
            programming_languages=row.programming_languages,
            frameworks=row.frameworks,
            cloud=row.cloud,
            databases=row.databases,
            years_experience=row.years_experience,
            education=row.education,
            seniority=row.seniority,
            employment_type=row.employment_type,
            remote_type=row.remote_type,
            salary_min=row.salary_min,
            salary_max=row.salary_max,
            salary_currency=row.salary_currency,
            responsibilities=row.responsibilities,
            preferred_qualifications=row.preferred_qualifications,
            confidence=row.confidence,
            provider=row.provider,
            model=row.model,
            analyzed_at=row.analyzed_at,
            raw=row.raw,
        )

    @staticmethod
    def _job_to_normalized(job: Job, company_name: str = ""):
        """Rebuild a normalized view of a persisted job for analysis input."""
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


analysis_service = AnalysisService()
