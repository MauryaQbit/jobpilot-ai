# Integrate saved-search collection

**Content type:** Conceptual

JobPilot AI collects jobs only through saved searches. This page explains the provider call, persistence transaction, and run-health update.

## Collection flow

The **Searches** page calls `run_saved_search()` after you select **Run now**.

```mermaid
flowchart LR
    UI[Searches page] --> Runner[run_saved_search]
    Runner --> Source[JobSpySource]
    Source --> Pipeline[Pipeline: normalize + dedup]
    Pipeline --> Service[JobService]
    Service --> Transaction[Job persistence transaction]
    Transaction --> Health[Saved-search run health]
```

## Implementation files

The collection path uses these files:

- `jobpilot/ui/pages/searches.py`: saved-search forms and **Run now** action
- `jobpilot/services/runner.py`: run lifecycle and health recording
- `jobpilot/scrapers/jobspy_source.py`: JobSpy parameters and row conversion
- `jobpilot/pipeline/`: normalization, deduplication, enrichment, and orchestration
- `jobpilot/services/job_service.py`: transactional persistence
- `jobpilot/services/saved_search_service.py`: saved definitions and latest run health

## Run-health behavior

The runner records `running` and its lease start before calling the provider. A terminal write replaces that lease timestamp with the completion time and records `succeeded`, `partial`, `failed`, or `cancelled` with duration and result counts.

An empty provider response is successful when no provider error exists. A mixed response stores valid jobs and reports `partial` with raw, valid, and invalid row counts. A nonempty response with no valid rows reports `failed`. A database failure rolls back both the provider result and terminal run health.

## Persistence behavior

The job URL identifies a repeated posting. Existing jobs receive nonempty provider-owned updates while preserving richer stored values when a repeated response omits optional fields. Stage, star, notes, and archive state always remain user-owned.

Job and company upserts commit in the same transaction as the saved search's terminal health. The initial `running` lease is a separate atomic claim because provider network work happens outside a database transaction.

Companies are created only for valid jobs. They become read-only facets under **Insights** and job filters.

## Verify collection

Run the provider, runner, and service tests:

```bash
uv run --locked pytest -q tests/services/test_job_scraper.py
uv run --locked pytest -q tests/scraping/test_scrape_all.py
uv run --locked pytest -q tests/integration/test_scraping_workflow.py
```
