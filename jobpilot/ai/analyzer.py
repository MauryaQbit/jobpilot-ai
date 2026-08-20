"""Job analysis service - structured extraction from job descriptions.

The analyzer uses the configured AI provider to extract structured job
attributes. Output is validated against the :class:`JobAnalysis` schema; any
provider failure degrades gracefully to deterministic offline analysis so the
pipeline always produces a schema-valid result.
"""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from jobpilot.ai.offline import OfflineProvider
from jobpilot.ai.provider import AIProvider, AIProviderError, get_provider
from jobpilot.config import Settings, get_settings
from jobpilot.models.analysis import JobAnalysis
from jobpilot.models.normalized_job import NormalizedJob

logger = logging.getLogger(__name__)

_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "required_skills": {"type": "array", "items": {"type": "string"}},
        "preferred_skills": {"type": "array", "items": {"type": "string"}},
        "programming_languages": {"type": "array", "items": {"type": "string"}},
        "frameworks": {"type": "array", "items": {"type": "string"}},
        "cloud": {"type": "array", "items": {"type": "string"}},
        "databases": {"type": "array", "items": {"type": "string"}},
        "years_experience": {"type": ["integer", "null"]},
        "education": {"type": ["string", "null"]},
        "seniority": {
            "type": "string",
            "enum": [
                "entry",
                "junior",
                "mid",
                "senior",
                "staff",
                "principal",
                "lead",
                "manager",
            ],
        },
        "employment_type": {
            "type": "string",
            "enum": ["full_time", "part_time", "contract", "internship", "temporary"],
        },
        "remote_type": {"type": "string", "enum": ["remote", "onsite", "hybrid"]},
        "salary_min": {"type": ["integer", "null"]},
        "salary_max": {"type": ["integer", "null"]},
        "salary_currency": {
            "type": "string",
            "enum": ["USD", "EUR", "GBP", "CAD", "AUD", "INR", "JPY"],
        },
        "responsibilities": {"type": "array", "items": {"type": "string"}},
        "preferred_qualifications": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
    "required": ["summary", "required_skills", "preferred_skills"],
    "additionalProperties": True,
}

_SYSTEM_PROMPT = (
    "You are a meticulous job-analysis engine. Extract structured data from the "
    "job posting exactly. Return ONLY valid JSON matching this schema: "
    f"{json.dumps(_ANALYSIS_SCHEMA)}. "
    "Use lowercase strings for skills, languages, frameworks, cloud, and databases. "
    "Set salary_min/salary_max as annualized USD numbers when stated. "
    "If a field is unknown, use null or an empty array. Never invent data."
)


class JobAnalyzer:
    """Produce structured :class:`JobAnalysis` for normalized jobs."""

    def __init__(
        self, settings: Settings | None = None, provider: AIProvider | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = provider or get_provider(self.settings)
        self._offline = OfflineProvider()

    def analyze(self, job: NormalizedJob) -> JobAnalysis:
        if self.provider.name == "offline":
            return self._offline.analyze(job)
        return self._analyze_with_llm(job)

    def _analyze_with_llm(self, job: NormalizedJob) -> JobAnalysis:
        user_prompt = self._build_user_prompt(job)
        try:
            raw = self.provider.complete_json(
                _SYSTEM_PROMPT,
                user_prompt,
                max_tokens=self.settings.ai_max_tokens,
            )
            raw.setdefault("provider", self.provider.name)
            raw.setdefault("model", self.settings.ai_model)
            analysis = JobAnalysis.model_validate(raw)
            logger.info(
                "AI analysis succeeded for job %r with provider %s",
                job.title,
                self.provider.name,
            )
            return analysis
        except (AIProviderError, ValidationError, ValueError, TypeError) as error:
            logger.warning(
                "AI analysis failed for job %r (%s); falling back to offline analysis",
                job.title,
                error,
            )
            return self._offline.analyze(job)

    @staticmethod
    def _build_user_prompt(job: NormalizedJob) -> str:
        return (
            "Analyze this job posting and return the structured JSON.\n\n"
            f"Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Location: {job.location}\n"
            f"Employment type: {job.employment_type.value if job.employment_type else 'unknown'}\n"
            f"Remote: {job.remote_type.value}\n"
            f"Salary range: {job.salary_min} - {job.salary_max} {job.salary_currency.value if job.salary_currency else ''}\n"
            f"Description:\n{job.description or '(no description available)'}"
        )


job_analyzer = JobAnalyzer()

__all__ = ["AIProvider", "JobAnalyzer", "get_provider", "job_analyzer"]
