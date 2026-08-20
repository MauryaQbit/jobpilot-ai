"""Analytics service - aggregated insights over the application database."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from statistics import fmean
from typing import Any

from sqlalchemy import func
from sqlmodel import select

from jobpilot.database.engine import db_session
from jobpilot.database.models import Application, Job, JobAnalysisRow, JobMatchRow

logger = logging.getLogger(__name__)

METHOD = "sqlalchemy"


class AnalyticsService:
    """Compute dashboard and API analytics from the canonical database."""

    def get_dashboard(self) -> dict[str, Any]:
        """Return the headline metrics for the dashboard landing view."""
        return {
            "jobs": self.job_overview(),
            "applications": self.application_overview(),
            "matching": self.matching_overview(),
            "distribution": self.remote_distribution(),
            "top_skills": self.top_skills(limit=10),
            "top_companies": self.top_companies(limit=10),
            "method": METHOD,
            "status": "success",
        }

    def job_overview(self) -> dict[str, Any]:
        with db_session() as session:
            total = int(session.exec(select(func.count(Job.id))).one())
            added_today = int(
                session.exec(
                    select(func.count(Job.id)).where(
                        func.date(Job.discovered_at) == func.date("now")
                    )
                ).one()
            )
            with_salary = int(
                session.exec(
                    select(func.count(Job.id)).where(
                        Job.salary_min.is_not(None) | Job.salary_max.is_not(None)
                    )
                ).one()
            )
            analyzed = int(session.exec(select(func.count(JobAnalysisRow.id))).one())
        return {
            "total_jobs": total,
            "added_today": added_today,
            "with_salary": with_salary,
            "analyzed": analyzed,
        }

    def application_overview(self) -> dict[str, Any]:
        counts = self.application_by_status()
        return {
            "total": sum(counts.values()),
            "by_status": counts,
            "applied": counts.get("Applied", 0),
            "interviews": counts.get("Interview", 0) + counts.get("Screening", 0),
            "offers": counts.get("Offer", 0),
            "rejected": counts.get("Rejected", 0),
        }

    def application_by_status(self) -> dict[str, int]:
        with db_session() as session:
            rows = session.exec(
                select(Application.status, func.count(Application.id)).group_by(
                    Application.status
                )
            ).all()
            return {str(status): int(count) for status, count in rows}

    def application_trends(self, days: int = 30) -> list[dict[str, Any]]:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        with db_session() as session:
            rows = session.exec(
                select(
                    func.date(Application.updated_at),
                    Application.status,
                    func.count(Application.id),
                )
                .where(Application.updated_at >= cutoff)
                .group_by(func.date(Application.updated_at), Application.status)
                .order_by(func.date(Application.updated_at)),
            ).all()
        grouped: dict[str, dict[str, int]] = defaultdict(lambda: {})
        for date_str, status, count in rows:
            grouped[str(date_str)][str(status)] = int(count)
        return [
            {"date": date_str, **counts} for date_str, counts in sorted(grouped.items())
        ]

    def matching_overview(self) -> dict[str, Any]:
        with db_session() as session:
            rows = session.exec(select(JobMatchRow.score)).all()
        scores = [float(score) for score in rows if score is not None]
        return {
            "matches_computed": len(scores),
            "average_score": round(fmean(scores), 1) if scores else 0.0,
            "strong_matches": sum(1 for score in scores if score >= 80),
            "top_score": round(max(scores), 1) if scores else 0.0,
            "low_score": round(min(scores), 1) if scores else 0.0,
        }

    def top_skills(self, limit: int = 10) -> list[dict[str, Any]]:
        with db_session() as session:
            analysis_rows = session.exec(select(JobAnalysisRow.required_skills)).all()
            job_rows = session.exec(select(Job.skills)).all()
        counter: Counter[str] = Counter()
        for skills in analysis_rows:
            for skill in skills or []:
                counter[str(skill).strip().lower()] += 1
        for skills in job_rows:
            for skill in skills or []:
                counter[str(skill).strip().lower()] += 1
        return [
            {"skill": skill, "count": count}
            for skill, count in counter.most_common(limit)
        ]

    def top_companies(self, limit: int = 10) -> list[dict[str, Any]]:
        from jobpilot.services.company_service import company_service

        facets = company_service.list_companies(limit=limit)
        return [
            {
                "company": facet.name,
                "total_jobs": facet.total_jobs,
                "active_jobs": facet.active_jobs,
            }
            for facet in facets
        ]

    def remote_distribution(self) -> dict[str, Any]:
        with db_session() as session:
            rows = session.exec(
                select(Job.remote_type, func.count(Job.id))
                .where(Job.status == "active")
                .group_by(Job.remote_type)
            ).all()
        distribution = {str(remote_type): int(count) for remote_type, count in rows}
        total = sum(distribution.values())
        return {"distribution": distribution, "total": total}

    def job_trends(self, days: int = 30) -> dict[str, Any]:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        with db_session() as session:
            rows = session.exec(
                select(func.date(Job.posted_at), func.count(Job.id))
                .where(Job.posted_at >= cutoff, Job.status == "active")
                .group_by(func.date(Job.posted_at))
                .order_by(func.date(Job.posted_at)),
            ).all()
        return {
            "trends": [
                {"date": str(date_str), "job_count": int(count)}
                for date_str, count in rows
            ],
            "status": "success",
        }

    def salary_stats(self, days: int = 90) -> dict[str, Any]:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        with db_session() as session:
            rows = session.exec(
                select(Job.salary_min, Job.salary_max).where(
                    Job.posted_at >= cutoff, Job.status == "active"
                )
            ).all()
        minimums = [int(minimum) for minimum, _ in rows if minimum is not None]
        maximums = [int(maximum) for _, maximum in rows if maximum is not None]
        return {
            "jobs_with_salary": (
                len(minimums) + len(maximums) > 0 and max(len(minimums), len(maximums))
            )
            or 0,
            "avg_min_salary": round(fmean(minimums), 2) if minimums else 0,
            "avg_max_salary": round(fmean(maximums), 2) if maximums else 0,
            "min_salary": min(minimums) if minimums else 0,
            "max_salary": max(maximums) if maximums else 0,
            "analysis_period_days": days,
        }

    def status_report(self) -> dict[str, Any]:
        from jobpilot.database.engine import get_engine

        engine = get_engine()
        return {
            "analytics_method": METHOD,
            "database_url": engine.url.render_as_string(hide_password=True),
            "status": "active",
        }

    def _error(self, key: str, empty: object, error: Exception) -> dict[str, Any]:
        return {key: empty, "status": "error", "error": str(error), "method": METHOD}


analytics_service = AnalyticsService()
