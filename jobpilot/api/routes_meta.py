"""Recommendation, analytics, and meta HTTP routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from jobpilot.api.schemas import CompanyFacetResponse, ScraperRunResponse
from jobpilot.config import get_settings
from jobpilot.services.analytics_service import analytics_service
from jobpilot.services.candidate_service import candidate_service
from jobpilot.services.company_service import company_service
from jobpilot.services.cost_monitor import cost_monitor
from jobpilot.services.recommendation_service import recommendation_service
from jobpilot.services.scraper_run_service import scraper_run_service

router = APIRouter(tags=["meta"])


class RecommendationItem(BaseModel):
    """One ranked, explainable recommendation."""

    job_id: int | None
    title: str
    company: str
    score: float
    matched_skills: list[str]
    missing_skills: list[str]
    reasons: list[str]
    warnings: list[str]
    rank: int

    @classmethod
    def from_ranked(cls, ranked) -> RecommendationItem:
        return cls(
            job_id=ranked.job.id,
            title=ranked.job.title,
            company=ranked.job.company,
            score=ranked.score,
            matched_skills=list(ranked.matched_skills),
            missing_skills=list(ranked.missing_skills),
            reasons=list(ranked.match.reasons),
            warnings=list(ranked.match.warnings),
            rank=ranked.rank,
        )


@router.get("/recommendations", response_model=list[RecommendationItem])
def recommendations(
    limit: int = Query(default=20, ge=1, le=100),
    minimum_score: float = Query(default=50.0, ge=0.0, le=100.0),
    exclude_applied: bool = True,
) -> list[RecommendationItem]:
    """Return ranked, explainable recommendations for the active profile."""
    profile = candidate_service.get_active()
    if profile is None:
        raise HTTPException(status_code=404, detail="No active candidate profile")
    ranked = recommendation_service.recommend(
        profile,
        limit=limit,
        minimum_score=minimum_score,
        exclude_applied=exclude_applied,
    )
    return [RecommendationItem.from_ranked(item) for item in ranked]


@router.get("/stats")
def stats() -> dict[str, Any]:
    """Return aggregated application analytics."""
    return analytics_service.get_dashboard()


@router.get("/companies", response_model=list[CompanyFacetResponse])
def companies(
    limit: int = Query(default=50, ge=1, le=500),
) -> list[CompanyFacetResponse]:
    """Return job-derived company facets."""
    return [
        CompanyFacetResponse.from_facet(facet)
        for facet in company_service.list_companies(limit=limit)
    ]


@router.get("/runs", response_model=list[ScraperRunResponse])
def runs(limit: int = Query(default=20, ge=1, le=200)) -> list[ScraperRunResponse]:
    """Return recent scraper-run observability records."""
    return [
        ScraperRunResponse.from_row(row)
        for row in scraper_run_service.list_runs(limit=limit)
    ]


@router.get("/budget")
def budget() -> dict[str, Any]:
    """Return current-month cost and budget health."""
    return cost_monitor.get_monthly_summary()


@router.get("/health")
def health() -> dict[str, Any]:
    """Return process, database, provider, and budget health."""
    settings = get_settings()
    database_ok = True
    error: str | None = None
    try:
        from jobpilot.database.engine import get_engine

        with get_engine().connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except Exception as exc:  # pragma: no cover - defensive
        database_ok = False
        error = str(exc)
    return {
        "status": "ok" if database_ok else "error",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "database": database_ok,
        "database_error": error,
        "ai_provider": settings.ai_provider,
        "ai_configured": bool(settings.ai_api_key),
        "budget_status": cost_monitor.get_monthly_summary()["budget_status"],
    }
