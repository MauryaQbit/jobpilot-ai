"""JobPilot AI schema: normalized jobs, analysis, matching, applications.

Revision ID: a1b2c3d4e5f6
Revises: c91e7a4d2b6f
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "c91e7a4d2b6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json():
    return sa.JSON()


def upgrade() -> None:
    """Create the JobPilot AI schema and migrate legacy rows where present."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    # ------------------------------------------------------------------ companies
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("domain", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("companies") as batch_op:
        batch_op.create_index("ix_companies_domain", ["domain"])
        batch_op.create_index("ix_companies_name", ["name"], unique=True)

    # ----------------------------------------------------------------------- jobs
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_job_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=False),
        sa.Column("remote_type", sa.String(), nullable=False),
        sa.Column("employment_type", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("requirements", _json(), nullable=False),
        sa.Column("responsibilities", _json(), nullable=False),
        sa.Column("skills", _json(), nullable=False),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(), nullable=True),
        sa.Column("experience_level", sa.String(), nullable=True),
        sa.Column("education", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("application_url", sa.String(), nullable=True),
        sa.Column("company_domain", sa.String(), nullable=True),
        sa.Column("job_hash", sa.String(), nullable=False),
        sa.Column("metadata", _json(), nullable=False),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("discovered_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(trim(title)) > 0", name="title_not_blank"),
        sa.CheckConstraint("length(trim(url)) > 0", name="url_not_blank"),
        sa.CheckConstraint(
            "salary_min IS NULL OR salary_min >= 0",
            name="salary_min_nonnegative",
        ),
        sa.CheckConstraint(
            "salary_max IS NULL OR salary_max >= 0",
            name="salary_max_nonnegative",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.create_index("ix_jobs_company_domain", ["company_domain"])
        batch_op.create_index("ix_jobs_company_id", ["company_id"])
        batch_op.create_index("ix_jobs_discovered_at", ["discovered_at"])
        batch_op.create_index("ix_jobs_employment_type", ["employment_type"])
        batch_op.create_index("ix_jobs_experience_level", ["experience_level"])
        batch_op.create_index("ix_jobs_job_hash", ["job_hash"])
        batch_op.create_index("ix_jobs_last_seen", ["last_seen"])
        batch_op.create_index("ix_jobs_location", ["location"])
        batch_op.create_index("ix_jobs_posted_at", ["posted_at"])
        batch_op.create_index("ix_jobs_remote_type", ["remote_type"])
        batch_op.create_index("ix_jobs_salary_max", ["salary_max"])
        batch_op.create_index("ix_jobs_salary_min", ["salary_min"])
        batch_op.create_index("ix_jobs_source", ["source"])
        batch_op.create_index("ix_jobs_source_job_id", ["source_job_id"])
        batch_op.create_index("ix_jobs_status", ["status"])
        batch_op.create_index("ix_jobs_title", ["title"])

    # ------------------------------------------------------------- job analyses
    op.create_table(
        "job_analyses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("required_skills", _json(), nullable=False),
        sa.Column("preferred_skills", _json(), nullable=False),
        sa.Column("programming_languages", _json(), nullable=False),
        sa.Column("frameworks", _json(), nullable=False),
        sa.Column("cloud", _json(), nullable=False),
        sa.Column("databases", _json(), nullable=False),
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column("education", sa.String(), nullable=True),
        sa.Column("seniority", sa.String(), nullable=True),
        sa.Column("employment_type", sa.String(), nullable=True),
        sa.Column("remote_type", sa.String(), nullable=True),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(), nullable=True),
        sa.Column("responsibilities", _json(), nullable=False),
        sa.Column("preferred_qualifications", _json(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(), nullable=False),
        sa.Column("raw", _json(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    with op.batch_alter_table("job_analyses") as batch_op:
        batch_op.create_index("ix_job_analyses_analyzed_at", ["analyzed_at"])
        batch_op.create_index("ix_job_analyses_job_id", ["job_id"], unique=True)

    # -------------------------------------------------------- candidate profiles
    op.create_table(
        "candidate_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("skills", _json(), nullable=False),
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column("education", sa.String(), nullable=True),
        sa.Column("preferred_locations", _json(), nullable=False),
        sa.Column("remote_preference", sa.String(), nullable=True),
        sa.Column("preferred_roles", _json(), nullable=False),
        sa.Column("preferred_companies", _json(), nullable=False),
        sa.Column("salary_expectation_min", sa.Integer(), nullable=True),
        sa.Column("salary_expectation_max", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("candidate_profiles") as batch_op:
        batch_op.create_index("ix_candidate_profiles_is_active", ["is_active"])

    # ------------------------------------------------------------- job matches
    op.create_table(
        "job_matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("skill_match", sa.Float(), nullable=False),
        sa.Column("experience_match", sa.Float(), nullable=False),
        sa.Column("role_match", sa.Float(), nullable=False),
        sa.Column("location_match", sa.Float(), nullable=False),
        sa.Column("remote_match", sa.Float(), nullable=False),
        sa.Column("salary_match", sa.Float(), nullable=False),
        sa.Column("seniority_match", sa.Float(), nullable=False),
        sa.Column("matched_skills", _json(), nullable=False),
        sa.Column("missing_skills", _json(), nullable=False),
        sa.Column("reasons", _json(), nullable=False),
        sa.Column("warnings", _json(), nullable=False),
        sa.Column("scored_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="score_bounds"),
        sa.CheckConstraint("scored_at IS NOT NULL", name="scored_at_present"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["candidate_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("job_matches") as batch_op:
        batch_op.create_index("ix_job_matches_job_id", ["job_id"])
        batch_op.create_index("ix_job_matches_profile_id", ["profile_id"])
        batch_op.create_index("ix_job_matches_score", ["score"])
        batch_op.create_index("ix_job_matches_scored_at", ["scored_at"])

    # ------------------------------------------------------------ applications
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("saved_at", sa.DateTime(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("notes", sa.String(), nullable=False),
        sa.CheckConstraint(
            "status IN ('Inbox', 'Saved', 'Applied', 'Screening', "
            "'Interview', 'Offer', 'Rejected')",
            name="application_stage",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["candidate_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("applications") as batch_op:
        batch_op.create_index("ix_applications_job_id", ["job_id"])
        batch_op.create_index("ix_applications_profile_id", ["profile_id"])
        batch_op.create_index("ix_applications_saved_at", ["saved_at"])
        batch_op.create_index("ix_applications_status", ["status"])
        batch_op.create_index("ix_applications_updated_at", ["updated_at"])

    # ---------------------------------------------------------- saved searches
    op.create_table(
        "saved_searches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("query", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=False),
        sa.Column("sites", _json(), nullable=False),
        sa.Column("remote_only", sa.Boolean(), nullable=False),
        sa.Column("job_type", sa.String(), nullable=True),
        sa.Column("results_limit", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_status", sa.String(), nullable=False),
        sa.Column("jobs_seen", sa.Integer(), nullable=False),
        sa.Column("jobs_new", sa.Integer(), nullable=False),
        sa.Column("jobs_duplicates", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        sa.CheckConstraint("length(trim(query)) > 0", name="query_not_blank"),
        sa.CheckConstraint("results_limit BETWEEN 1 AND 1000", name="results_limit"),
        sa.CheckConstraint("jobs_seen >= 0", name="jobs_seen_nonnegative"),
        sa.CheckConstraint("jobs_new >= 0", name="jobs_new_nonnegative"),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="duration_ms_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("saved_searches") as batch_op:
        batch_op.create_index("ix_saved_searches_enabled", ["enabled"])
        batch_op.create_index("ix_saved_searches_last_run_status", ["last_run_status"])
        batch_op.create_index("ix_saved_searches_name", ["name"], unique=True)

    # ------------------------------------------------------------ scraper runs
    op.create_table(
        "scraper_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("search_term", sa.String(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("remote_only", sa.Boolean(), nullable=False),
        sa.Column("job_type", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("jobs_seen", sa.Integer(), nullable=False),
        sa.Column("jobs_new", sa.Integer(), nullable=False),
        sa.Column("jobs_duplicates", sa.Integer(), nullable=False),
        sa.Column("jobs_rejected", sa.Integer(), nullable=False),
        sa.Column("jobs_analyzed", sa.Integer(), nullable=False),
        sa.Column("jobs_matched", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("metadata", _json(), nullable=False),
        sa.CheckConstraint("jobs_seen >= 0", name="jobs_seen_nonnegative"),
        sa.CheckConstraint("jobs_new >= 0", name="jobs_new_nonnegative"),
        sa.CheckConstraint("jobs_duplicates >= 0", name="jobs_duplicates_nonnegative"),
        sa.CheckConstraint("jobs_rejected >= 0", name="jobs_rejected_nonnegative"),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="duration_ms_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("scraper_runs") as batch_op:
        batch_op.create_index("ix_scraper_runs_source", ["source"])
        batch_op.create_index("ix_scraper_runs_started_at", ["started_at"])
        batch_op.create_index("ix_scraper_runs_status", ["status"])

    # ------------------------------------------------- legacy data migration
    if "companysql" in existing:
        op.execute(
            "INSERT OR IGNORE INTO companies (name, url, created_at) "
            "SELECT name, url, CURRENT_TIMESTAMP FROM companysql "
            "WHERE name IS NOT NULL AND trim(name) != ''"
        )

    if "jobsql" in existing:
        op.execute(
            "INSERT OR IGNORE INTO jobs "
            "(company_id, source, source_job_id, title, location, remote_type, "
            "employment_type, description, requirements, responsibilities, skills, "
            "salary_min, salary_max, salary_currency, experience_level, education, "
            "url, application_url, company_domain, job_hash, metadata, posted_at, "
            "discovered_at, last_seen, status, created_at) "
            "SELECT "
            "COALESCE((SELECT c.id FROM companies c WHERE c.name = jc.name), 1), "
            "'linkedin', j.id, j.title, j.location, 'onsite', "
            "NULL, j.description, '[]', '[]', '[]', "
            "CAST(json_extract(j.salary, '$[0]') AS INTEGER), "
            "CAST(json_extract(j.salary, '$[1]') AS INTEGER), NULL, NULL, NULL, "
            "j.link, NULL, NULL, j.content_hash, '{}', j.posted_date, "
            "CURRENT_TIMESTAMP, j.last_seen, "
            "CASE WHEN j.archived THEN 'archived' ELSE 'active' END, "
            "CURRENT_TIMESTAMP "
            "FROM jobsql j LEFT JOIN companysql jc ON jc.id = j.company_id"
        )

    if "savedsearchsql" in existing:
        op.execute(
            "INSERT OR IGNORE INTO saved_searches "
            "(name, query, location, sites, remote_only, job_type, results_limit, "
            "enabled, last_run_at, last_run_status, jobs_seen, jobs_new, "
            "jobs_duplicates, duration_ms, last_error) "
            "SELECT name, query, location, sites, remote_only, job_type, "
            "results_limit, enabled, last_run_at, last_run_status, jobs_seen, "
            "jobs_new, 0, duration_ms, last_error "
            "FROM savedsearchsql"
        )

    # Preserve existing application tracking where a legacy job maps cleanly.
    if "jobsql" in existing:
        op.execute(
            "INSERT INTO applications "
            "(job_id, profile_id, status, saved_at, applied_at, updated_at, notes) "
            "SELECT nj.id, NULL, "
            "CASE j.application_status "
            "  WHEN 'Inbox' THEN 'Inbox' "
            "  WHEN 'Saved' THEN 'Saved' "
            "  WHEN 'Applied' THEN 'Applied' "
            "  WHEN 'Interviews' THEN 'Interview' "
            "  WHEN 'Closed' THEN 'Rejected' "
            "  ELSE 'Saved' END, "
            "j.last_seen, j.application_date, CURRENT_TIMESTAMP, j.notes "
            "FROM jobsql j JOIN jobs nj ON nj.url = j.link "
            "WHERE j.favorite OR j.application_status != 'Inbox' "
            "OR j.application_date IS NOT NULL "
            "OR trim(j.notes) != ''"
        )


def downgrade() -> None:
    """Drop the JobPilot schema tables (legacy tables remain untouched)."""
    for table in (
        "applications",
        "scraper_runs",
        "saved_searches",
        "job_matches",
        "candidate_profiles",
        "job_analyses",
        "jobs",
        "companies",
    ):
        op.drop_table(table)
