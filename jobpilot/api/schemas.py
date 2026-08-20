"""HTTP API request and response models for JobPilot AI.

DB-loaded SQLModel rows hold enum-valued columns as plain strings, so response
models coerce them explicitly to clean enum values.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from jobpilot.database.models import (
    Application,
    CandidateProfileRow,
    Job,
    JobAnalysisRow,
    JobMatchRow,
    ScraperRun,
)
from jobpilot.models.enums import (
    ApplicationStage,
    Currency,
    EmploymentType,
    ExperienceLevel,
    JobSite,
    RemoteType,
    SavedSearchRunStatus,
    ScraperRunStatus,
)
from jobpilot.services.saved_search_service import SavedSearchDTO


class JobResponse(BaseModel):
    """Serializable view of one job with its normalized company name."""

    id: int
    company_id: int
    company: str
    source: JobSite
    source_job_id: str
    title: str
    location: str
    remote_type: RemoteType
    employment_type: EmploymentType | None = None
    description: str
    requirements: list[str]
    responsibilities: list[str]
    skills: list[str]
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: Currency | None = None
    experience_level: ExperienceLevel | None = None
    education: str | None = None
    url: str
    application_url: str | None = None
    company_domain: str | None = None
    job_hash: str = ""
    posted_at: datetime | None = None
    discovered_at: datetime | None = None
    last_seen: datetime | None = None
    status: str = "active"
    match_score: float | None = None

    @classmethod
    def from_row(
        cls, job: Job, company_name: str, match_score: float | None = None
    ) -> JobResponse:
        return cls(
            id=job.id,
            company_id=job.company_id,
            company=company_name,
            source=job.source,
            source_job_id=job.source_job_id,
            title=job.title,
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
            posted_at=job.posted_at,
            discovered_at=job.discovered_at,
            last_seen=job.last_seen,
            status=job.status,
            match_score=match_score,
        )


class AnalysisResponse(BaseModel):
    """Serializable view of a cached job analysis."""

    job_id: int
    summary: str
    required_skills: list[str]
    preferred_skills: list[str]
    programming_languages: list[str]
    frameworks: list[str]
    cloud: list[str]
    databases: list[str]
    years_experience: int | None = None
    education: str | None = None
    seniority: ExperienceLevel | None = None
    employment_type: EmploymentType | None = None
    remote_type: RemoteType | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: Currency | None = None
    responsibilities: list[str]
    preferred_qualifications: list[str]
    confidence: float
    provider: str
    model: str | None = None
    analyzed_at: datetime

    @classmethod
    def from_row(cls, row: JobAnalysisRow) -> AnalysisResponse:
        return cls(
            job_id=row.job_id,
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
        )


class MatchResponse(BaseModel):
    """Serializable view of one cached match result."""

    job_id: int
    profile_id: int
    score: float
    skill_match: float
    experience_match: float
    role_match: float
    location_match: float
    remote_match: float
    salary_match: float
    seniority_match: float
    matched_skills: list[str]
    missing_skills: list[str]
    reasons: list[str]
    warnings: list[str]
    scored_at: datetime

    @classmethod
    def from_row(cls, row: JobMatchRow) -> MatchResponse:
        return cls(
            job_id=row.job_id,
            profile_id=row.profile_id,
            score=row.score,
            skill_match=row.skill_match,
            experience_match=row.experience_match,
            role_match=row.role_match,
            location_match=row.location_match,
            remote_match=row.remote_match,
            salary_match=row.salary_match,
            seniority_match=row.seniority_match,
            matched_skills=row.matched_skills,
            missing_skills=row.missing_skills,
            reasons=row.reasons,
            warnings=row.warnings,
            scored_at=row.scored_at,
        )


class ProfileResponse(BaseModel):
    """Serializable view of a candidate profile."""

    id: int
    name: str
    skills: list[str]
    years_experience: int | None = None
    education: str | None = None
    preferred_locations: list[str]
    remote_preference: RemoteType | None = None
    preferred_roles: list[str]
    preferred_companies: list[str]
    salary_expectation_min: int | None = None
    salary_expectation_max: int | None = None
    salary_currency: Currency | None = None
    is_active: bool

    @classmethod
    def from_row(cls, row: CandidateProfileRow) -> ProfileResponse:
        return cls(
            id=row.id,
            name=row.name,
            skills=row.skills,
            years_experience=row.years_experience,
            education=row.education,
            preferred_locations=row.preferred_locations,
            remote_preference=row.remote_preference,
            preferred_roles=row.preferred_roles,
            preferred_companies=row.preferred_companies,
            salary_expectation_min=row.salary_expectation_min,
            salary_expectation_max=row.salary_expectation_max,
            salary_currency=row.salary_currency,
            is_active=row.is_active,
        )


class ProfileCreateRequest(BaseModel):
    """Create a candidate profile."""

    name: str = Field(min_length=1, default="My Profile")
    skills: list[str] = Field(default_factory=list)
    years_experience: int | None = Field(default=None, ge=0, le=60)
    education: str | None = None
    preferred_locations: list[str] = Field(default_factory=list)
    remote_preference: RemoteType | None = None
    preferred_roles: list[str] = Field(default_factory=list)
    preferred_companies: list[str] = Field(default_factory=list)
    salary_expectation_min: int | None = Field(default=None, ge=0)
    salary_expectation_max: int | None = Field(default=None, ge=0)
    salary_currency: Currency | None = None


class ApplicationResponse(BaseModel):
    """Serializable application record with its job summary."""

    id: int
    job_id: int
    job_title: str
    company: str
    profile_id: int | None = None
    status: ApplicationStage
    saved_at: datetime | None = None
    applied_at: datetime | None = None
    updated_at: datetime
    notes: str = ""

    @classmethod
    def from_row(
        cls, application: Application, job: Job, company_name: str
    ) -> ApplicationResponse:
        return cls(
            id=application.id,
            job_id=application.job_id,
            job_title=job.title,
            company=company_name,
            profile_id=application.profile_id,
            status=application.status,
            saved_at=application.saved_at,
            applied_at=application.applied_at,
            updated_at=application.updated_at,
            notes=application.notes,
        )


class ApplicationStatusRequest(BaseModel):
    """Transition an application to a new stage."""

    status: ApplicationStage
    profile_id: int | None = None
    notes: str | None = None


class SavedSearchResponse(BaseModel):
    """Serializable view of a saved search and its run health."""

    id: int
    name: str
    query: str
    location: str
    sites: list[JobSite]
    remote_only: bool
    job_type: EmploymentType | None = None
    results_limit: int
    enabled: bool
    last_run_at: datetime | None = None
    last_run_status: SavedSearchRunStatus = SavedSearchRunStatus.NEVER
    jobs_seen: int = 0
    jobs_new: int = 0
    jobs_duplicates: int = 0
    duration_ms: int | None = None
    last_error: str | None = None

    @classmethod
    def from_dto(cls, dto: SavedSearchDTO) -> SavedSearchResponse:
        return cls.model_validate(dto.model_dump())


class SavedSearchCreateRequest(BaseModel):
    """Create a saved search."""

    name: str = Field(min_length=1)
    query: str = Field(min_length=1)
    location: str = Field(min_length=1, default="United States")
    sites: list[JobSite] = Field(
        default_factory=lambda: [JobSite.LINKEDIN, JobSite.INDEED],
        min_length=1,
    )
    remote_only: bool = False
    job_type: EmploymentType | None = None
    results_limit: int = Field(default=50, ge=1, le=1000)
    enabled: bool = True


class SavedSearchUpdateRequest(BaseModel):
    """Update a saved search (partial)."""

    name: str | None = Field(default=None, min_length=1)
    query: str | None = Field(default=None, min_length=1)
    location: str | None = Field(default=None, min_length=1)
    sites: list[JobSite] | None = Field(default=None, min_length=1)
    remote_only: bool | None = None
    job_type: EmploymentType | None = None
    results_limit: int | None = Field(default=None, ge=1, le=1000)
    enabled: bool | None = None


class ScraperRunResponse(BaseModel):
    """Serializable view of one scraper-run observability record."""

    id: int
    source: str
    search_term: str | None = None
    location: str | None = None
    status: ScraperRunStatus
    jobs_seen: int = 0
    jobs_new: int = 0
    jobs_duplicates: int = 0
    jobs_rejected: int = 0
    jobs_analyzed: int = 0
    jobs_matched: int = 0
    duration_ms: int | None = None
    started_at: datetime
    finished_at: datetime | None = None
    error: str | None = None

    @classmethod
    def from_row(cls, row: ScraperRun) -> ScraperRunResponse:
        return cls(
            id=row.id,
            source=row.source,
            search_term=row.search_term,
            location=row.location,
            status=row.status,
            jobs_seen=row.jobs_seen,
            jobs_new=row.jobs_new,
            jobs_duplicates=row.jobs_duplicates,
            jobs_rejected=row.jobs_rejected,
            jobs_analyzed=row.jobs_analyzed,
            jobs_matched=row.jobs_matched,
            duration_ms=row.duration_ms,
            started_at=row.started_at,
            finished_at=row.finished_at,
            error=row.error,
        )


class CompanyFacetResponse(BaseModel):
    """Serializable company facet."""

    id: int
    name: str
    url: str | None = None
    domain: str | None = None
    total_jobs: int = 0
    active_jobs: int = 0
    last_job_posted: datetime | None = None

    @classmethod
    def from_facet(cls, facet) -> CompanyFacetResponse:
        return cls(
            id=facet.id,
            name=facet.name,
            url=facet.url,
            domain=facet.domain,
            total_jobs=facet.total_jobs,
            active_jobs=facet.active_jobs,
            last_job_posted=facet.last_job_posted,
        )


class RunOutcomeResponse(BaseModel):
    """Result of triggering an end-to-end saved-search run."""

    search_id: int
    search_name: str
    status: str
    jobs_seen: int = 0
    jobs_new: int = 0
    jobs_duplicates: int = 0
    jobs_rejected: int = 0
    jobs_analyzed: int = 0
    jobs_matched: int = 0
    duration_ms: int = 0
    error: str | None = None
