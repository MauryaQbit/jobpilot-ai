"""Starter saved-search seeding."""

from jobpilot.cli.seed import STARTER_SEARCHES, app, seed
from jobpilot.database.models import SavedSearch
from sqlmodel import Session, select
from typer.testing import CliRunner


def test_seed_creates_starter_searches(session: Session) -> None:
    seed()

    searches = session.exec(select(SavedSearch)).all()
    assert {(search.name, search.query) for search in searches} == set(STARTER_SEARCHES)
    assert all(search.enabled for search in searches)


def test_seed_is_idempotent(session: Session) -> None:
    seed()
    seed()

    assert len(session.exec(select(SavedSearch)).all()) == len(STARTER_SEARCHES)


def test_seed_cli(session: Session) -> None:
    result = CliRunner().invoke(app, [])

    assert result.exit_code == 0
    assert "Seeded" in result.output
