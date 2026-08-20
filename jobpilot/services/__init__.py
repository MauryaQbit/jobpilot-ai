"""Service layer for JobPilot AI."""

from __future__ import annotations

from jobpilot.services.analysis_service import analysis_service
from jobpilot.services.analytics_service import analytics_service
from jobpilot.services.application_service import application_service
from jobpilot.services.candidate_service import candidate_service
from jobpilot.services.company_service import company_service
from jobpilot.services.cost_monitor import cost_monitor
from jobpilot.services.job_service import job_service
from jobpilot.services.matching_service import matching_service
from jobpilot.services.recommendation_service import recommendation_service
from jobpilot.services.runner import (
    RunOutcome,
    SavedSearchRunInProgressError,
    run_all_enabled,
    run_all_enabled_sync,
    run_saved_search,
)
from jobpilot.services.saved_search_service import (
    SavedSearchCreate,
    SavedSearchDTO,
    SavedSearchUpdate,
    saved_search_service,
)
from jobpilot.services.scraper_run_service import scraper_run_service

__all__ = [
    "RunOutcome",
    "SavedSearchCreate",
    "SavedSearchDTO",
    "SavedSearchRunInProgressError",
    "SavedSearchUpdate",
    "analysis_service",
    "analytics_service",
    "application_service",
    "candidate_service",
    "company_service",
    "cost_monitor",
    "job_service",
    "matching_service",
    "recommendation_service",
    "run_all_enabled",
    "run_all_enabled_sync",
    "run_saved_search",
    "saved_search_service",
    "scraper_run_service",
]
