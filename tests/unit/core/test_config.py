"""Tests for the maintained runtime settings."""

import logging

import pytest
from jobpilot.config import Settings, configure_logging
from pydantic import ValidationError


def test_settings_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DB_URL", raising=False)
    monkeypatch.delenv("JOBPILOT_LOG_LEVEL", raising=False)

    settings = Settings()

    assert settings.db_url == "sqlite:///jobpilot.db"
    assert settings.log_level == "INFO"
    assert "PRAGMA journal_mode = WAL" in settings.sqlite_pragmas
    assert "PRAGMA foreign_keys = ON" in settings.sqlite_pragmas


def test_dotenv_and_environment_precedence(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "DB_URL=sqlite:///dotenv.db\nJOBPILOT_LOG_LEVEL=warning\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DB_URL", raising=False)
    monkeypatch.delenv("JOBPILOT_LOG_LEVEL", raising=False)

    dotenv_settings = Settings()
    assert dotenv_settings.db_url == "sqlite:///dotenv.db"
    assert dotenv_settings.log_level == "WARNING"

    monkeypatch.setenv("DB_URL", "sqlite:///environment.db")
    assert Settings().db_url == "sqlite:///environment.db"


def test_settings_validate_database_and_log_level(monkeypatch):
    assert Settings(db_url="relative.db").db_url == "sqlite:///relative.db"

    with pytest.raises(ValidationError, match="Database URL configuration"):
        Settings(db_url="")
    with pytest.raises(ValidationError, match="Only SQLite"):
        Settings(db_url="postgresql://localhost/jobs")
    with pytest.raises(ValidationError, match="Invalid SQLite"):
        Settings(db_url="sqlite:garbage")
    with pytest.raises(ValidationError, match="Invalid SQLite"):
        Settings(db_url="sqlite://host/jobs.db")
    monkeypatch.setenv("JOBPILOT_LOG_LEVEL", "verbose")
    with pytest.raises(ValidationError, match="Invalid logging configuration"):
        Settings()


def test_cors_origins_parse_from_comma_separated_text():
    settings = Settings(cors_origins="http://localhost:3000, https://example.com")
    assert settings.cors_origins == ["http://localhost:3000", "https://example.com"]


def test_cors_origins_empty_list_disables_middleware():
    assert Settings(cors_origins=[]).cors_origins == []


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError, match="Wildcard CORS"):
        Settings(app_env="production")
    with pytest.raises(ValidationError, match="Wildcard CORS"):
        Settings(app_env="production", cors_origins=["*", "https://example.com"])
    settings = Settings(app_env="production", cors_origins=["https://example.com"])
    assert settings.is_production
    assert settings.cors_origins == ["https://example.com"]


def test_configure_logging_applies_level_and_format(monkeypatch):
    monkeypatch.setattr(logging.getLogger(), "handlers", [])
    configure_logging(Settings(log_level="warning"))
    assert logging.getLogger().level == logging.WARNING
    formatters = [
        handler.formatter
        for handler in logging.getLogger().handlers
        if handler.formatter
    ]
    assert formatters, "configure_logging should install a formatter"
    assert formatters[0]._fmt == " ".join(
        ["%(asctime)s", "%(levelname)s", "%(name)s:", "%(message)s"]
    )


def test_configure_logging_is_idempotent():
    root = logging.getLogger()
    handler_count = len(root.handlers)
    configure_logging(Settings())
    assert len(root.handlers) == max(handler_count, 1)
