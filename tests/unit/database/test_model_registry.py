"""Regression tests for the application-owned SQLModel registry."""

import subprocess
import sys


def test_database_models_can_be_reloaded() -> None:
    """Keep Streamlit source reloads from redefining shared SQLModel tables."""
    script = """
from importlib import reload
from jobpilot.database import models

reload(models)
assert set(models.AppSQLModel.metadata.tables) == {
    "companies", "jobs", "job_analyses", "candidate_profiles", "job_matches",
    "applications", "saved_searches", "scraper_runs", "cost_entries",
}
"""

    completed = subprocess.run(
        [sys.executable, "-W", "error", "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
