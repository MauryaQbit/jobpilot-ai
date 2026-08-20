"""Domain models for JobPilot AI."""

from __future__ import annotations

from jobpilot.models.analysis import JobAnalysis
from jobpilot.models.candidate import CandidateProfile
from jobpilot.models.enums import (
    ApplicationStage,
    Currency,
    EmploymentType,
    ExperienceLevel,
    JobSite,
    JobStatus,
    RemoteType,
    SavedSearchRunStatus,
    ScraperRunStatus,
)
from jobpilot.models.job_posting import JobPosting, JobScrapeRequest, JobScrapeResult
from jobpilot.models.match import MatchResult, ScoreBreakdown
from jobpilot.models.normalized_job import NormalizedJob

__all__ = [
    "ApplicationStage",
    "CandidateProfile",
    "Currency",
    "EmploymentType",
    "ExperienceLevel",
    "JobAnalysis",
    "JobPosting",
    "JobScrapeRequest",
    "JobScrapeResult",
    "JobSite",
    "JobStatus",
    "MatchResult",
    "NormalizedJob",
    "RemoteType",
    "SavedSearchRunStatus",
    "ScoreBreakdown",
    "ScraperRunStatus",
]
