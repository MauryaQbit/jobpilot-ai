"""Application settings for JobPilot AI.

All configuration is environment driven. Secrets are never embedded in source
code and never logged. The canonical env file is ``.env`` (see ``.env.example``).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from jobpilot import APP_NAME, __version__


class ConfigurationError(ValueError):
    """Raised when the runtime configuration is invalid."""


class LogLevelError(ValueError):
    """Raised when an invalid log level is configured."""


def normalize_sqlite_url(value: str) -> str:
    """Return one canonical SQLAlchemy SQLite URL or reject it."""
    value = value.strip()
    if not value:
        raise ConfigurationError(
            "Database URL configuration is missing or invalid. "
            "Please provide a valid SQLite database URL.",
        )

    candidate = value if ":" in value else f"sqlite:///{value}"
    try:
        url = make_url(candidate)
        has_authority = any((url.username, url.password, url.host, url.port))
    except (ArgumentError, ValueError) as error:
        raise ConfigurationError("Invalid SQLite database URL.") from error

    if url.drivername != "sqlite":
        raise ConfigurationError("Only SQLite database URLs are supported.")
    if has_authority or url.database == "":
        raise ConfigurationError("Invalid SQLite database URL.")
    return url.render_as_string(hide_password=False)


# Default scoring weights for the candidate matching engine. They sum to 1.0.
DEFAULT_MATCH_WEIGHTS: dict[str, float] = {
    "skill_match": 0.40,
    "experience_match": 0.20,
    "role_match": 0.15,
    "location_match": 0.10,
    "remote_match": 0.10,
    "salary_match": 0.05,
}

VALID_WEIGHT_KEYS = set(DEFAULT_MATCH_WEIGHTS)


def parse_match_weights(value: str | dict[str, float]) -> dict[str, float]:
    """Parse matching weights from env text like ``skill_match=0.4,role_match=0.2``."""
    if isinstance(value, dict):
        weights = value
    else:
        weights = {}
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                raise ConfigurationError(
                    f"Invalid match weight segment: {part!r}. "
                    "Expected comma-separated key=value pairs."
                )
            key, raw = part.split("=", 1)
            weights[key.strip()] = float(raw.strip())

    unknown = set(weights) - VALID_WEIGHT_KEYS
    if unknown:
        raise ConfigurationError(
            f"Unknown match weight keys: {', '.join(sorted(unknown))}. "
            f"Supported keys: {', '.join(sorted(VALID_WEIGHT_KEYS))}."
        )
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise ConfigurationError(f"Match weights must sum to 1.0, got {total:.4f}.")
    return weights


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or ``.env``.

    Environment variables use the ``JOBPILOT_`` prefix for JobPilot-specific
    settings. ``DB_URL`` remains the canonical database connection variable.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
        validate_by_name=True,
    )

    # ------------------------------------------------------------------ core
    app_env: str = Field(default="development", validation_alias="JOBPILOT_ENV")
    app_name: str = Field(default=APP_NAME, validation_alias="JOBPILOT_APP_NAME")
    app_version: str = __version__

    # -------------------------------------------------------------- database
    db_url: str = "sqlite:///jobpilot.db"

    sqlite_pragmas: list[str] = [
        "PRAGMA journal_mode = WAL",
        "PRAGMA synchronous = NORMAL",
        "PRAGMA cache_size = 64000",
        "PRAGMA temp_store = MEMORY",
        "PRAGMA mmap_size = 134217728",
        "PRAGMA foreign_keys = ON",
        "PRAGMA optimize",
    ]

    # ---------------------------------------------------------------- logging
    log_level: str = Field(default="INFO", validation_alias="JOBPILOT_LOG_LEVEL")

    # ------------------------------------------------------------------- API
    #: Comma-separated origins allowed by the HTTP API. In development the
    #: default wildcard mirrors the local-first deployment; production requires
    #: explicit origins (see :meth:`validate_runtime`).
    cors_origins: list[str] = Field(
        default_factory=lambda: ["*"],
        validation_alias="JOBPILOT_CORS_ORIGINS",
    )

    # ---------------------------------------------------------------- AI layer
    #: ``offline`` (deterministic fallback) or ``openai_compatible``.
    ai_provider: str = Field(default="offline", validation_alias="AI_PROVIDER")
    ai_base_url: str | None = Field(default=None, validation_alias="AI_BASE_URL")
    ai_api_key: str | None = Field(default=None, validation_alias="AI_API_KEY")
    ai_model: str = Field(default="gpt-4o-mini", validation_alias="AI_MODEL")
    ai_timeout_seconds: float = Field(
        default=60.0, validation_alias="AI_TIMEOUT_SECONDS"
    )
    ai_max_tokens: int = Field(default=2000, validation_alias="AI_MAX_TOKENS")
    ai_temperature: float = Field(default=0.0, validation_alias="AI_TEMPERATURE")
    ai_retries: int = Field(default=2, validation_alias="AI_RETRIES")

    # ------------------------------------------------------------ matching
    match_weights: dict[str, float] = Field(
        default_factory=lambda: dict(DEFAULT_MATCH_WEIGHTS),
        validation_alias="MATCH_WEIGHTS",
    )
    match_minimum_score: float = Field(
        default=50.0,
        validation_alias="MATCH_MINIMUM_SCORE",
    )

    # ------------------------------------------------------------- scraping
    scraper_default_results: int = Field(
        default=50,
        validation_alias="SCRAPER_DEFAULT_RESULTS",
    )
    scraper_fetch_descriptions: bool = Field(
        default=True,
        validation_alias="SCRAPER_FETCH_DESCRIPTIONS",
    )
    scraper_country: str = Field(default="USA", validation_alias="SCRAPER_COUNTRY")

    # --------------------------------------------------------- notifications
    notify_enabled: bool = Field(default=False, validation_alias="NOTIFY_ENABLED")
    notify_webhook_url: str | None = Field(
        default=None,
        validation_alias="NOTIFY_WEBHOOK_URL",
    )

    # ---------------------------------------------------------- applications
    application_statuses: tuple[str, ...] = (
        "Inbox",
        "Saved",
        "Applied",
        "Screening",
        "Interview",
        "Offer",
        "Rejected",
    )

    @field_validator("db_url")
    @classmethod
    def validate_db_url(cls, value: str) -> str:
        """Normalize the supported SQLite database URL."""
        return normalize_sqlite_url(value)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Validate the logging level and normalize it to uppercase."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = value.upper()
        if normalized not in valid_levels:
            raise LogLevelError(
                f"Invalid logging configuration: '{value}' is not a valid log "
                f"level. Supported levels are: {', '.join(sorted(valid_levels))}.",
            )
        return normalized

    @field_validator("ai_provider")
    @classmethod
    def validate_ai_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"offline", "openai_compatible"}:
            raise ConfigurationError(
                f"Unsupported AI provider: {value!r}. "
                "Supported providers: offline, openai_compatible."
            )
        return normalized

    @field_validator("match_weights", mode="before")
    @classmethod
    def validate_match_weights(cls, value: Any) -> dict[str, float]:
        if isinstance(value, str):
            return parse_match_weights(value)
        if isinstance(value, dict):
            return parse_match_weights(value)
        raise ConfigurationError("match_weights must be a dict or key=value text.")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def validate_cors_origins(cls, value: Any) -> Any:
        """Accept a comma-separated string or a list of origins."""
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",") if part.strip()]
            if not parts:
                raise ConfigurationError(
                    "JOBPILOT_CORS_ORIGINS must not be empty when set."
                )
            return parts
        return value

    @model_validator(mode="after")
    def validate_runtime(self) -> Settings:
        """Reject provider configurations that cannot operate honestly."""
        if self.ai_provider == "openai_compatible" and not self.ai_api_key:
            raise ConfigurationError(
                "AI_PROVIDER=openai_compatible requires AI_API_KEY to be set."
            )
        if self.is_production and "*" in self.cors_origins:
            raise ConfigurationError(
                "Wildcard CORS origins are not allowed in production. "
                "Set JOBPILOT_CORS_ORIGINS to explicit origins."
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def get_settings() -> Settings:
    """Return the process-owned settings instance."""
    return Settings()


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(settings: Settings) -> None:
    """Apply the configured level and format to the root logger.

    Call once at every process entry point (CLI, API, dashboard). Existing
    handlers are respected so test runners and process managers that install
    their own handler keep control. Secrets are never written to logs.
    """
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(handler)
    logging.captureWarnings(True)
