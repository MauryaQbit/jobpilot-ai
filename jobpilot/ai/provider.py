"""AI provider abstraction for JobPilot AI.

Providers are configured through environment variables (never hard-coded keys).
The :func:`get_provider` factory returns a provider based on
``AI_PROVIDER``:

- ``offline``: deterministic extraction with no network access.
- ``openai_compatible``: any OpenAI-compatible chat completions endpoint
  (OpenAI, vLLM, Ollama, LM Studio, ...) configured via ``AI_BASE_URL``,
  ``AI_API_KEY`` and ``AI_MODEL``.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from jobpilot.config import Settings, get_settings

logger = logging.getLogger(__name__)


class AIProviderError(RuntimeError):
    """Raised when an AI provider cannot complete a request."""


class AITimeoutError(AIProviderError):
    """Raised when an AI provider request exceeds its timeout."""


@runtime_checkable
class AIProvider(Protocol):
    """Protocol for services that return structured JSON from a prompt."""

    name: str

    def complete_json(
        self, system: str, user: str, max_tokens: int = 2000
    ) -> dict[str, Any]:
        """Return a parsed JSON object for the given prompt."""
        ...


class NullProvider:
    """Provider that always raises - used as a safe default that never hits the network."""

    name = "null"

    def complete_json(
        self, system: str, user: str, max_tokens: int = 2000
    ) -> dict[str, Any]:
        raise AIProviderError("No AI provider configured")


def get_provider(settings: Settings | None = None) -> AIProvider:
    """Return the configured AI provider instance."""
    settings = settings or get_settings()
    provider_name = settings.ai_provider
    if provider_name == "openai_compatible":
        from jobpilot.ai.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(settings=settings)
    if provider_name == "offline":
        from jobpilot.ai.offline import OfflineProvider

        return OfflineProvider()
    raise AIProviderError(f"Unknown AI provider configured: {provider_name!r}")


def safe_schema_dict(model: BaseModel) -> dict[str, Any]:
    """Serialise a schema to JSON-compatible data for prompt embedding."""
    return model.model_dump(mode="json")
