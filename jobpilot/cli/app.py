"""The ``jobpilot`` command-line interface.

Commands:

- ``dashboard``  run the Streamlit dashboard
- ``scrape``     run saved searches through the discovery pipeline
- ``analyze``    run AI analysis over unanalyzed jobs
- ``match``      compute job/profile matches for the active profile
- ``recommend``  print the top ranked recommendations
- ``stats``      print aggregated analytics
- ``health``     verify database, schema, provider, and budget health
- ``api``        run the FastAPI HTTP API
- ``seed``       create idempotent starter saved searches
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from jobpilot.cli.seed import run_seed
from jobpilot.config import Settings, configure_logging, get_settings
from jobpilot.database.migrations import run_migrations
from jobpilot.models.enums import ApplicationStage
from jobpilot.services import (
    analysis_service,
    analytics_service,
    candidate_service,
    cost_monitor,
    job_service,
    matching_service,
    recommendation_service,
    run_all_enabled_sync,
    run_saved_search,
)

app = typer.Typer(add_completion=False)


@app.callback()
def _configure_runtime() -> None:
    """Apply logging configuration before any command runs."""
    configure_logging(get_settings())


def _echo_settings(settings: Settings) -> None:
    typer.echo(f"APP: {settings.app_name}")
    typer.echo(f"ENV: {settings.app_env}")


@app.command()
def dashboard(
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8501,
    address: Annotated[str, typer.Option()] = "127.0.0.1",
) -> None:
    """Run the Streamlit dashboard."""
    run_migrations()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(Path(__file__).resolve().parent.parent / "ui" / "main.py"),
            f"--server.port={port}",
            f"--server.address={address}",
        ],
        check=False,
    )
    if result.returncode:
        raise typer.Exit(result.returncode)


@app.command()
def scrape(
    search_id: Annotated[
        int | None, typer.Option(help="Run a single saved search by id")
    ] = None,
) -> None:
    """Run saved searches through the discovery pipeline end-to-end."""
    run_migrations()
    if search_id is not None:
        outcome = _run_sync_single(search_id)
        _print_outcome(outcome)
        return
    outcomes = run_all_enabled_sync()
    if not outcomes:
        typer.echo(
            "No enabled saved searches found. Run `jobpilot seed` to create starter searches."
        )
        return
    for outcome in outcomes:
        _print_outcome(outcome)


def _run_sync_single(search_id: int):
    """Run one saved search from a synchronous CLI context."""
    import asyncio

    return asyncio.run(run_saved_search(search_id))


def _print_outcome(outcome) -> None:
    search = outcome.search
    name = search.name if search else "?"
    status = (
        outcome.status.value if hasattr(outcome.status, "value") else outcome.status
    )
    typer.echo(
        f"{name}: {status} | seen={outcome.jobs_seen} new={outcome.jobs_new} "
        f"dup={outcome.jobs_duplicates} rejected={outcome.jobs_rejected} "
        f"analyzed={outcome.jobs_analyzed} matched={outcome.jobs_matched} "
        f"({outcome.duration_ms}ms)"
    )
    if outcome.error:
        typer.echo(f"  error: {outcome.error}")


@app.command()
def analyze(
    limit: Annotated[int, typer.Option(min=1, max=10000)] = 500,
) -> None:
    """Run AI analysis over jobs that have no cached analysis yet."""
    jobs = analysis_service.unanalyzed_jobs(limit=limit)
    stats = analysis_service.analyze_jobs(jobs)
    typer.echo(
        f"Analyzed {stats['analyzed']} jobs (failed={stats['failed']}, "
        f"remaining={len(jobs) - stats['analyzed']})"
    )


@app.command()
def match(
    profile_id: Annotated[
        int | None, typer.Option(help="Profile to match against (default: active)")
    ] = None,
    limit: Annotated[int, typer.Option(min=1, max=10000)] = 500,
    minimum_score: Annotated[float, typer.Option(min=0, max=100)] = 0.0,
) -> None:
    """Compute and cache job/profile matches for the active profile."""
    profile = (
        candidate_service.get(profile_id)
        if profile_id is not None
        else candidate_service.get_active()
    )
    if profile is None:
        typer.echo("No candidate profile found. Create one in the dashboard first.")
        raise typer.Exit(1)
    jobs = [job for job, _ in job_service.list_jobs(limit=limit)]
    results = matching_service.match_jobs(jobs, profile, minimum_score=minimum_score)
    typer.echo(f"Matched {len(results)} jobs against profile '{profile.name}'.")
    if results:
        ranked = sorted(results, key=lambda r: r.score, reverse=True)[:5]
        for result in ranked:
            typer.echo(
                f"  {result.score:6.1f}  {result.job.title}  ({result.job.company})"
            )


@app.command()
def recommend(
    limit: Annotated[int, typer.Option(min=1, max=100)] = 10,
    minimum_score: Annotated[float, typer.Option(min=0, max=100)] = 60.0,
) -> None:
    """Print the top ranked, explainable recommendations."""
    profile = candidate_service.get_active()
    if profile is None:
        typer.echo("No candidate profile found. Create one in the dashboard first.")
        raise typer.Exit(1)
    ranked = recommendation_service.recommend(
        profile, limit=limit, minimum_score=minimum_score, exclude_applied=True
    )
    if not ranked:
        typer.echo("No recommendations clear the minimum score.")
        return
    for ranked_job in ranked:
        typer.echo(
            f"{ranked_job.score:6.1f}  {ranked_job.job.title}  ({ranked_job.job.company})"
        )
        for reason in ranked_job.match.reasons:
            typer.echo(f"         - {reason}")
        if ranked_job.match.warnings:
            typer.echo(f"         ! {'; '.join(ranked_job.match.warnings)}")


@app.command()
def stats() -> None:
    """Print aggregated analytics about the application database."""
    dashboard = analytics_service.get_dashboard()
    typer.echo(json.dumps(dashboard, indent=2, default=str))


@app.command()
def health() -> None:
    """Verify database, schema, provider, and budget health."""
    _echo_settings(get_settings())
    try:
        from jobpilot.database.engine import get_engine

        with get_engine().connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        typer.echo("database: ok")
    except Exception as error:
        typer.echo(f"database: FAILED ({error})")
        raise typer.Exit(1) from error

    try:
        from jobpilot.config import get_settings as _get_settings

        settings = _get_settings()
        if settings.ai_provider == "openai_compatible" and settings.ai_api_key:
            typer.echo(f"ai_provider: openai_compatible (model {settings.ai_model})")
        else:
            typer.echo("ai_provider: offline (no API key configured)")
    except Exception as error:
        typer.echo(f"ai_provider: FAILED ({error})")

    budget = cost_monitor.get_monthly_summary()
    typer.echo(
        f"budget: {budget['budget_status']} "
        f"(${budget['total_cost']:.2f} / ${budget['monthly_budget']:.2f})"
    )

    counts = application_service_count_by_status()
    total_apps = sum(counts.values())
    typer.echo(f"applications: {total_apps} tracked")
    for stage in ApplicationStage:
        if counts.get(stage.value, 0):
            typer.echo(f"  {stage.value}: {counts[stage.value]}")


def application_service_count_by_status() -> dict[str, int]:
    from jobpilot.services.application_service import application_service

    return application_service.count_by_status()


@app.command()
def api(
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8000,
) -> None:
    """Run the FastAPI HTTP API with uvicorn."""
    run_migrations()
    import uvicorn

    uvicorn.run("jobpilot.api.app:app", host=host, port=port, reload=False)


@app.command()
def seed() -> None:
    """Create idempotent starter saved searches."""
    added = run_seed()
    typer.echo(f"Seeded {added} saved searches.")


if __name__ == "__main__":
    app()
