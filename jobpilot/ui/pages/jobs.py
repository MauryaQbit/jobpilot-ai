"""Jobs workspace - filter, review, and move opportunities forward."""

from __future__ import annotations

import logging
import math

import streamlit as st
from jobpilot.database.models import Job
from jobpilot.models.enums import ApplicationStage, RemoteType
from jobpilot.models.filters import JobFilters
from jobpilot.services import (
    analysis_service,
    application_service,
    candidate_service,
    company_service,
    job_service,
    matching_service,
)
from jobpilot.ui.design import (
    WORKFLOW_STAGES,
    empty_state,
    page_intro,
    relative_time,
    sentence_case,
)

logger = logging.getLogger(__name__)


def _load_matches(profile_id: int | None, jobs: list[Job]) -> dict[int, object]:
    if profile_id is None:
        return {}
    job_ids = [job.id for job in jobs if job.id]
    return matching_service.get_match_map(profile_id, job_ids)


def _render_job(job: Job, company_name: str, match_row) -> None:
    with st.container(border=True, key=f"job-card-{job.id}"):
        title_meta = job.title
        if match_row is not None:
            title_meta = f"{title_meta} — {match_row.score:.0f}% match"
        st.subheader(title_meta, anchor=False)
        st.markdown(f"**{company_name}** · {job.location or 'Location not listed'}")
        details = []
        if job.salary_min is not None or job.salary_max is not None:
            salary = []
            if job.salary_min is not None:
                salary.append(f"${job.salary_min:,}")
            if job.salary_max is not None:
                salary.append(f"${job.salary_max:,}")
            details.append("-".join(salary))
        details.append(sentence_case(str(job.remote_type)))
        if job.employment_type:
            details.append(sentence_case(str(job.employment_type)))
        if job.posted_at:
            details.append(f"posted {relative_time(job.posted_at)}")
        st.caption(" · ".join(details))

        analysis = analysis_service.get_analysis(job.id)
        if analysis:
            if analysis.summary:
                st.markdown(analysis.summary)
            if analysis.required_skills:
                st.caption("Required skills: " + ", ".join(analysis.required_skills))
        elif job.skills:
            st.caption("Skills: " + ", ".join(job.skills))

        if match_row is not None:
            if match_row.missing_skills:
                st.caption("Missing: " + ", ".join(sorted(match_row.missing_skills)))
            if match_row.reasons:
                with st.expander("Why this match"):
                    for reason in match_row.reasons:
                        st.markdown(f"- {reason}")
                    if match_row.warnings:
                        for warning in match_row.warnings:
                            st.markdown(f"- {warning}")

        with st.expander("Review and update"):
            with st.form(f"job-form-{job.id}"):
                existing = application_service.get_application(job.id)
                current_stage = existing.status if existing else ApplicationStage.INBOX
                stage = st.selectbox(
                    "Stage",
                    WORKFLOW_STAGES,
                    index=WORKFLOW_STAGES.index(current_stage),
                    format_func=lambda value: value.value,
                )
                notes = st.text_area(
                    "Notes",
                    value=existing.notes if existing else "",
                    placeholder="Record context for your next decision.",
                )
                if st.form_submit_button("Save changes", type="primary"):
                    try:
                        application_service.set_status(job.id, stage, notes=notes)
                    except Exception:
                        logger.exception("Could not update job %s", job.id)
                        st.error("This job could not be updated. Try again.")
                    else:
                        st.session_state["jobs-notice"] = "Job updated."
                        st.rerun()

            if job.application_url or job.url:
                posting_url = job.application_url or job.url
                if posting_url.startswith(("http://", "https://")):
                    st.markdown(f"[Open original posting]({posting_url})")
                else:
                    st.caption("Original posting unavailable")
            if job.description:
                st.markdown("#### Description")
                st.markdown(job.description)


def render_jobs_page() -> None:
    """Render filters, stage counts, and job review controls."""
    page_intro(
        "Working set",
        "Jobs",
        "Move each opportunity through one clear workflow, from first review to a final decision.",
    )
    if notice := st.session_state.pop("jobs-notice", None):
        st.success(notice)

    try:
        counts = application_service.count_by_status()
        companies = company_service.list_companies(limit=500)
        active_profile = candidate_service.get_active()
    except Exception:
        logger.exception("Could not load job filters")
        st.error("Jobs could not be loaded. Check the database and try again.")
        return

    stage = st.radio(
        "Workflow stage",
        (None, *WORKFLOW_STAGES),
        index=0,
        format_func=lambda value: (
            "All" if value is None else f"{value.value}  {counts.get(value.value, 0)}"
        ),
        key="jobs-stage",
        horizontal=True,
    )

    filter_left, filter_right = st.columns([3, 2], gap="medium")
    with filter_left:
        query = st.text_input(
            "Search jobs",
            placeholder="Role, company, location, or keyword",
            key="jobs-query",
        )
    with filter_right:
        selected_companies = st.multiselect(
            "Companies",
            [company.name for company in companies],
            placeholder="All companies",
            key="jobs-companies",
        )
    second_left, second_right = st.columns([3, 2], gap="medium")
    with second_left:
        remote_filter = st.selectbox(
            "Remote",
            (None, RemoteType.REMOTE, RemoteType.HYBRID, RemoteType.ONSITE),
            format_func=lambda value: (
                "Any work mode" if value is None else sentence_case(value.value)
            ),
            key="jobs-remote",
        )
    with second_right:
        profile_options = candidate_service.list(include_inactive=True)
        profile_names = {profile.id: profile.name for profile in profile_options}
        option_ids = [profile.id for profile in profile_options]
        active_id = active_profile.id if active_profile else None
        if option_ids:
            default_index = (
                option_ids.index(active_id) if active_id in option_ids else 0
            )
            selected_profile = st.selectbox(
                "Match profile",
                option_ids,
                index=default_index,
                format_func=lambda profile_id: profile_names.get(profile_id, "None"),
                key="jobs-profile",
            )
            profile_id = selected_profile
        else:
            st.caption("Create a candidate profile to see match scores.")
            profile_id = None

    filter_signature = (
        stage,
        query or "",
        tuple(sorted(selected_companies or [])),
        remote_filter.value if remote_filter else None,
        profile_id,
    )
    if st.session_state.get("jobs-filter-sig") != filter_signature:
        st.session_state["jobs-page"] = 1
        st.session_state["jobs-filter-sig"] = filter_signature

    filters = JobFilters(
        query=query,
        company=selected_companies,
        remote=remote_filter,
        status=stage,
    )
    try:
        total_jobs = job_service.count_jobs(filters)
    except Exception:
        logger.exception("Could not query jobs")
        st.error(
            "The current job view could not be loaded. Adjust the filters or retry."
        )
        return

    if total_jobs == 0:
        empty_state(
            "Nothing here yet",
            "Run a saved search to collect jobs, or choose another workflow stage.",
        )
        return

    pagination_left, pagination_right = st.columns([1, 1], gap="medium")
    with pagination_left:
        jobs_per_page = st.selectbox(
            "Jobs per page", (10, 25, 50), index=1, key="jobs-per-page"
        )
    page_count = math.ceil(total_jobs / jobs_per_page)
    with pagination_right:
        page = st.selectbox(
            "Page",
            range(1, page_count + 1),
            format_func=lambda value: f"{value} of {page_count}",
            key="jobs-page",
        )

    start = (page - 1) * jobs_per_page
    end = min(start + jobs_per_page, total_jobs)
    try:
        rows = job_service.list_jobs(
            filters,
            limit=jobs_per_page,
            offset=start,
            order_by="posted_at",
            profile_id=profile_id,
        )
    except Exception:
        logger.exception("Could not load the requested job page")
        st.error("The requested job page could not be loaded. Try again.")
        return

    st.caption(f"Showing {start + 1} to {end} of {total_jobs} jobs")
    jobs = [job for job, _ in rows]
    matches = _load_matches(profile_id, jobs)
    for job, company_name in rows:
        _render_job(job, company_name, matches.get(job.id))


if __name__ == "__main__":
    render_jobs_page()
