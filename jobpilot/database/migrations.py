"""Database migration utilities for JobPilot AI.

Runs Alembic migrations to the head revision. The migration chain begins with
the legacy ``ai-job-scraper`` schema (so existing databases can be upgraded)
and continues with the JobPilot schema revision.
"""

from __future__ import annotations

import logging
from functools import cache
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


@cache
def run_migrations() -> None:
    """Run Alembic database migrations to the head revision (idempotent)."""
    try:
        logger.info("Starting database migrations...")
        alembic_cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully")
    except (CommandError, SQLAlchemyError) as error:
        logger.exception(
            "Failed to run database migrations [%s]",
            type(error).__name__,
        )
        raise
