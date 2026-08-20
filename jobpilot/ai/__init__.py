"""AI analysis layer for JobPilot AI."""

from __future__ import annotations

from jobpilot.ai.analyzer import JobAnalyzer, job_analyzer
from jobpilot.ai.offline import OfflineProvider
from jobpilot.ai.openai_compat import OpenAICompatProvider
from jobpilot.ai.provider import (
    AIProvider,
    AIProviderError,
    AITimeoutError,
    NullProvider,
    get_provider,
)

__all__ = [
    "AIProvider",
    "AIProviderError",
    "AITimeoutError",
    "JobAnalyzer",
    "NullProvider",
    "OfflineProvider",
    "OpenAICompatProvider",
    "get_provider",
    "job_analyzer",
]
