"""SQLite pragma event listeners for database optimization."""

from __future__ import annotations

import logging

from jobpilot.config import Settings

logger = logging.getLogger(__name__)
_settings = Settings()


def apply_pragmas(conn, _):
    """Apply SQLite pragmas on each new connection."""
    cursor = conn.cursor()
    for pragma in _settings.sqlite_pragmas:
        try:
            cursor.execute(pragma)
            logger.debug("Applied SQLite pragma: %s", pragma)
        except Exception:
            logger.warning("Failed to apply pragma '%s'", pragma)
    cursor.close()
