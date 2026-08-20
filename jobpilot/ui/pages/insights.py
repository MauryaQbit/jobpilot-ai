"""Read-only job-search insights."""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st
from jobpilot.services import (
    analytics_service,
    application_service,
    company_service,
    saved_search_service,
)
from jobpilot.ui.design import WORKFLOW_STAGES, empty_state, page_intro, relative_time

logger = logging.getLogger(__name__)


def _money(value: float | int) -> str:
    return "—" if not value else f"${value:,.0f}"


def render_insights_page() -> None:
    """Render stage, trend, salary, skill, and company evidence."""
    page_intro(
        "Evidence",
        "Insights",
        "See where the search is moving and which companies are producing useful opportunities.",
    )

    try:
        counts = application_service.count_by_status()
        trends = analytics_service.job_trends(days=30)
        salaries = analytics_service.salary_stats(days=90)
        skills = analytics_service.top_skills(limit=10)
        remote = analytics_service.remote_distribution()
        companies = company_service.list_companies()
        searches = saved_search_service.list()
    except Exception:
        logger.exception("Could not load insights")
        st.error("Insights could not be calculated. Check the database and retry.")
        return

    total_jobs = analytics_service.job_overview()["total_jobs"]
    top_metrics = st.columns(4, gap="medium")
    top_metrics[0].metric("Tracked jobs", total_jobs, border=True)
    top_metrics[1].metric("Companies", len(companies), border=True)
    top_metrics[2].metric("Saved searches", len(searches), border=True)
    top_metrics[3].metric("Applied", counts.get("Applied", 0), border=True)

    st.subheader("Workflow", anchor=False)
    stage_metrics = st.columns(len(WORKFLOW_STAGES), gap="small")
    for column, stage in zip(stage_metrics, WORKFLOW_STAGES, strict=True):
        column.metric(stage.value, counts.get(stage.value, 0), border=True)

    st.subheader("New listings", anchor=False)
    if trends["status"] == "error":
        st.error("Listing trends are temporarily unavailable.")
    elif trends["trends"]:
        trend_frame = pd.DataFrame(trends["trends"]).set_index("date")
        st.bar_chart(trend_frame["job_count"], color="#176b5b")
        st.caption("Active jobs by posted date over the past 30 days.")
    else:
        empty_state(
            "No trend yet",
            "Run a saved search to build a history of job listings.",
        )

    st.subheader("Compensation", anchor=False)
    salary_metrics = st.columns(3, gap="medium")
    salary_metrics[0].metric(
        "Jobs with salary data",
        salaries["jobs_with_salary"],
        border=True,
    )
    salary_metrics[1].metric(
        "Average minimum",
        _money(salaries["avg_min_salary"]),
        border=True,
    )
    salary_metrics[2].metric(
        "Average maximum",
        _money(salaries["avg_max_salary"]),
        border=True,
    )

    st.subheader("Work mode", anchor=False)
    distribution = remote["distribution"]
    if distribution:
        mode_frame = pd.DataFrame(
            [
                {"Work mode": mode, "Jobs": int(count)}
                for mode, count in distribution.items()
            ]
        )
        st.bar_chart(mode_frame.set_index("Work mode")["Jobs"], color="#176b5b")
        st.caption("Active jobs grouped by remote work mode.")
    else:
        empty_state(
            "No distribution yet",
            "Work mode breakdowns appear once jobs are collected.",
        )

    st.subheader("Most requested skills", anchor=False)
    if skills:
        skill_frame = pd.DataFrame(skills).set_index("skill")
        st.bar_chart(skill_frame["count"], color="#176b5b")
        st.caption("Skills are drawn from job analysis and persisted listings.")
    else:
        empty_state(
            "No skills yet",
            "Skill evidence appears once jobs have been analyzed.",
        )

    st.subheader("Company facets", anchor=False)
    if not companies:
        empty_state(
            "No companies yet",
            "Companies appear here automatically when a saved search finds jobs.",
        )
        return

    company_frame = pd.DataFrame(
        [
            {
                "Company": company.name,
                "Active jobs": company.active_jobs,
                "All jobs": company.total_jobs,
                "Latest listing": relative_time(company.last_job_posted),
                "Website": company.url,
            }
            for company in companies
        ]
    )
    st.dataframe(
        company_frame,
        hide_index=True,
        width="stretch",
        column_config={
            "Website": st.column_config.LinkColumn("Website", display_text="Open"),
        },
    )
    st.caption("Companies are derived from collected jobs and cannot be edited here.")


if __name__ == "__main__":
    render_insights_page()
