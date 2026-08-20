# Application API reference

**Content type:** Reference

This reference documents the maintained Python contracts used by the discovery
pipeline, service layer, Streamlit pages, and the FastAPI HTTP API. All Python
entry points live in the `jobpilot` package.

## Enumerations

`jobpilot/models/enums.py` defines the domain values accepted by saved
searches, provider requests, and the application workflow.

### `JobSite`

Supported values are `linkedin`, `indeed`, `glassdoor`, `zip_recruiter`, and
`google`. `JobSite.normalize(value)` accepts common case, space, and hyphen
variants and returns `None` for an unknown site.

### `EmploymentType`

Supported values are `full_time`, `part_time`, `contract`, `internship`, and
`temporary`. `EmploymentType.normalize(value)` also accepts `fulltime`,
`permanent`, `contractor`, `intern`, and `temp`.

### `RemoteType`

Supported values are `remote`, `onsite`, and `hybrid`.
`RemoteType.from_flags(is_remote, location)` derives a value from a boolean
remote flag plus a free-text location; `RemoteType.normalize(value)` accepts
variants such as `fully remote` and `in-office`.

### `ApplicationStage`

The workflow stages are `Inbox`, `Saved`, `Applied`, `Screening`, `Interview`,
`Offer`, and `Rejected`. `is_terminal()` treats `Offer` and `Rejected` as
terminal; `active_stages()` returns every non-terminal stage.

### `SavedSearchRunStatus`

The finite run states are `never`, `running`, `succeeded`, `partial`, `failed`,
and `cancelled`. `ScraperRunStatus` mirrors these states for raw scraper runs.

### Other enums

`JobStatus` (`active` / `archived`), `ExperienceLevel`, and `Currency` support
normalization and matching; each exposes a `normalize()` helper.

## Provider contracts

`jobpilot/models/job_posting.py` models raw job-board output before
normalization. These are the input contracts of the discovery pipeline.

### `JobScrapeRequest`

The request accepts sites, search term, location, distance, remote flag, job
type, easy-apply flag, result limit, country, offset, posting age, annual-salary
enforcement, and description options. Sites and job type normalize from strings.

### `JobPosting`

A posting requires `title`, `company`, and a direct or listing URL. Provider
list fields normalize scalar strings to one-item lists, and a numeric field that
cannot convert becomes `None`. `location_type` derives from `is_remote` and
`location` when not supplied.

### `JobScrapeResult`

The result contains validated `jobs`, `total_found`, the originating
`request_params`, and `metadata`. `from_pandas(df, request)` builds a result
from a JobSpy DataFrame; `filter_by_location_type()` and `filter_by_job_type()`
return copies with only matching jobs.

## Discovery pipeline

`jobpilot/services/runner.py` orchestrates saved-search runs end-to-end.

```text
async run_saved_search(search_id: int) -> RunOutcome
async run_all_enabled() -> list[RunOutcome]
run_all_enabled_sync() -> list[RunOutcome]
class SavedSearchRunInProgressError(RuntimeError)
```

A run claims the search, executes the discovery source and pipeline (discovery,
normalization, deduplication, enrichment, AI analysis, and matching), persists
the result and its terminal health in one transaction, and releases the claim.

`RunOutcome` exposes the refreshed `search`, the `pipeline` result, `run_id`,
`status`, `error`, `jobs_new`, `jobs_analyzed`, and `jobs_matched`, plus
properties `jobs_seen`, `jobs_duplicates`, `jobs_rejected`, and `duration_ms`.

## Saved-search schemas

`jobpilot/services/saved_search_service.py` owns detached saved-search
contracts.

### `SavedSearchCreate`

| Field | Type | Default |
| --- | --- | --- |
| `name` | `str` | Required |
| `query` | `str` | Required |
| `location` | `str` | `United States` |
| `sites` | `list[JobSite]` | LinkedIn and Indeed |
| `remote_only` | `bool` | `False` |
| `job_type` | `EmploymentType | None` | `None` |
| `results_limit` | `int` | `50`, range 1 through 1000 |
| `enabled` | `bool` | `True` |

Name, query, and location are stripped and cannot be blank.

### `SavedSearchUpdate`

Every editable `SavedSearchCreate` field is optional. `model_dump(exclude_unset=True)`
distinguishes an omitted field from an explicit `None` job type.

### `SavedSearchDTO`

Combines the definition, database identifier, and run health: `last_run_at`,
`last_run_status`, `jobs_seen`, `jobs_new`, `jobs_duplicates`, `duration_ms`,
and `last_error`. The dashboard re-reads this DTO after each run.

## Database API

`jobpilot/database/engine.py` owns every application connection.

### `get_engine(database_url: str | None = None) -> Engine`

Returns the lazily created process engine. In-memory SQLite uses `StaticPool`;
file SQLite uses the normal SQLAlchemy pool with the configured pragmas.

### `db_session(bind=None)`

Commits after a successful context and rolls back after an exception.

### `db_session_no_autocommit(bind=None)`

Lets the caller control commits and rolls back any remaining transaction on
exit.

### `get_connection_pool_status(bind=None) -> dict[str, Any]`

Returns bounded pool diagnostics and a password-hidden engine URL.

`jobpilot/database/migrations.py` applies pending Alembic migrations at every
process entry point (CLI, API lifespan, and dashboard).

## Service layer

All services are singletons exported from `jobpilot.services` and share the
`db_session()` transaction boundary.

### `job_service`

```text
persist_pipeline_result(pipeline: PipelineResult) -> PersistCounts
list_jobs(filters: JobFilters, *, limit, offset, order_by, profile_id) -> list[tuple[Job, str]]
get_job(job_id: int) -> Job | None
get_job_with_company(job_id: int) -> tuple[Job, str] | None
```

`persist_pipeline_result` inserts, updates, or skips each job, creates company
facets on demand, and reports exact counts. `JobFilters` (from
`jobpilot/models/filters.py`) carries query text, keyword, company list,
location, remote, and `include_archived`.

### `application_service`

```text
save_job(job_id: int, *, stage, profile_id) -> Application
set_status(job_id: int, stage, *, profile_id, notes) -> Application
list_applications(...) -> list[Application]
count_by_status(profile_id: int | None = None) -> dict[str, int]
list_recent_activity(limit: int = 20) -> list[tuple[Application, Job]]
```

Application records own the workflow stage, star, notes, application date, and
archive state that survive repeated scrapes.

### `analytics_service`

```text
get_dashboard() -> dict[str, Any]
job_overview() / application_overview() / matching_overview()
application_by_status() -> dict[str, int]
application_trends(days: int = 30) -> list[dict[str, Any]]
job_trends(days: int = 30) -> dict[str, Any]
salary_stats(days: int = 90) -> dict[str, Any]
status_report() -> dict[str, Any]
top_skills(limit: int = 10) / top_companies(limit: int = 10)
remote_distribution() -> dict[str, Any]
```

### `matching_service` and `recommendation_service`

`matching_service.match_jobs(jobs, profile, *, minimum_score)` computes
explainable match results and caches them as `JobMatchRow` rows.
`recommendation_service.recommend(profile, *, limit, minimum_score,
exclude_applied)` returns ranked, explainable recommendations with reasons and
warnings.

### `candidate_service`

```text
list(*, include_inactive: bool = False) -> list[CandidateProfile]
get(profile_id) / get_active() / create(profile) / update(profile_id, data)
set_active(profile_id) / delete(profile_id)
```

### `analysis_service`

`unanalyzed_jobs(limit)` returns jobs without a cached analysis;
`analyze_jobs(jobs)` runs the configured AI provider (or the deterministic
offline fallback) and persists structured `JobAnalysisRow` results.

### `cost_monitor`

`track_ai_cost`, `track_proxy_cost`, and `track_scraping_cost` record `CostEntry`
rows. `get_monthly_summary()` returns `budget_status`, `total_cost`, and
`monthly_budget`; `get_cost_alerts()` returns actionable budget alerts.

## HTTP API

The FastAPI application (`jobpilot/api/app.py`) serves all routes under
`/api`. It runs schema migrations during lifespan, applies CORS from
`JOBPILOT_CORS_ORIGINS`, and documents itself at `/docs`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/jobs` | List jobs with filtering, ordering, and paging |
| GET | `/api/jobs/{job_id}` | One job with its company name |
| GET | `/api/jobs/{job_id}/analysis` | Cached structured analysis |
| GET | `/api/jobs/{job_id}/match` | Cached match for a profile |
| GET | `/api/profiles` | List candidate profiles |
| POST | `/api/profiles` | Create a profile |
| GET | `/api/profiles/active` | The active profile |
| GET | `/api/profiles/{profile_id}` | One profile |
| PUT | `/api/profiles/{profile_id}` | Update a profile |
| POST | `/api/profiles/{profile_id}/activate` | Set the active profile |
| DELETE | `/api/profiles/{profile_id}` | Delete a profile |
| GET | `/api/applications` | List applications |
| POST | `/api/applications/{job_id}/save` | Save a job to the pipeline |
| POST | `/api/applications/{job_id}/status` | Set stage and notes |
| GET | `/api/applications/status-counts` | Per-stage counts |
| GET | `/api/searches` | List saved searches |
| POST | `/api/searches` | Create a saved search |
| GET | `/api/searches/{search_id}` | One saved search |
| PUT | `/api/searches/{search_id}` | Update a saved search |
| DELETE | `/api/searches/{search_id}` | Delete a saved search |
| POST | `/api/searches/{search_id}/run` | Run one saved search (202) |
| POST | `/api/searches/run-all` | Run all enabled searches (202) |
| GET | `/api/recommendations` | Top ranked recommendations |
| GET | `/api/stats` | Aggregated analytics |
| GET | `/api/companies` | Job-derived company facets |
| GET | `/api/runs` | Scraper-run observability |
| GET | `/api/budget` | Cost and budget health |
| GET | `/api/health` | Service health |