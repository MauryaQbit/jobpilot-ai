"""Seed useful starter searches without inventing company records."""

from __future__ import annotations

import typer

from jobpilot.services.saved_search_service import (
    SavedSearchCreate,
    saved_search_service,
)

app = typer.Typer(add_completion=False)

STARTER_SEARCHES = (
    ("AI Engineering", "AI engineer"),
    ("Machine Learning", "machine learning engineer"),
    ("Data Science", "data scientist"),
    ("MLOps", "MLOps engineer"),
    ("AI Product", "AI product manager"),
)


def run_seed() -> int:
    """Create idempotent starter saved searches; return the number added."""
    existing_names = {search.name for search in saved_search_service.list()}
    added = 0
    for name, query in STARTER_SEARCHES:
        if name in existing_names:
            continue
        saved_search_service.create(SavedSearchCreate(name=name, query=query))
        added += 1
    return added


@app.command()
def seed() -> None:
    """Create idempotent starter saved searches."""
    added = run_seed()
    typer.echo(f"Seeded {added} saved searches.")


if __name__ == "__main__":
    app()
