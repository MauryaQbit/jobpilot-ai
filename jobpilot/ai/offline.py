"""Deterministic (offline) AI analysis provider.

When no LLM is configured, JobPilot AI still produces structured analysis using
lexicon matching and description heuristics. This provider never touches the
network and always returns a schema-valid payload.
"""

from __future__ import annotations

import re
from typing import Any

from jobpilot.constants import SKILLS_LEXICON
from jobpilot.models.analysis import JobAnalysis
from jobpilot.models.normalized_job import NormalizedJob
from jobpilot.pipeline.enricher import Enricher

_YEARS_RE = re.compile(r"(\d+)\+?\s*(?:-|\s+to\s+)?\s*(\d+)?\s*years?", re.IGNORECASE)

_EDUCATION_TERMS = {
    "ph.d": "PhD",
    "phd": "PhD",
    "doctorate": "Doctorate",
    "master's": "Master's degree",
    "masters": "Master's degree",
    "msc": "Master's degree",
    "m.s.": "Master's degree",
    "bachelor's": "Bachelor's degree",
    "bachelors": "Bachelor's degree",
    "b.s.": "Bachelor's degree",
    "bs": "Bachelor's degree",
    "associate": "Associate degree",
}

_CLOUD = ["aws", "gcp", "azure", "sagemaker", "vertex ai", "azure ml", "cloud"]
_DATABASES = [
    "postgres",
    "postgresql",
    "mysql",
    "mongodb",
    "redis",
    "elasticsearch",
    "dynamodb",
    "snowflake",
    "bigquery",
    "redshift",
    "databricks",
    "kafka",
    "sql",
]


class OfflineProvider:
    """Deterministic analysis used when no LLM provider is configured."""

    name = "offline"

    def complete_json(
        self, system: str, user: str, max_tokens: int = 2000
    ) -> dict[str, Any]:
        raise RuntimeError(
            "The offline provider does not answer prompts; use JobAnalyzer.analyze()."
        )

    def analyze(self, job: NormalizedJob) -> JobAnalysis:
        description = job.description or ""
        enricher = Enricher()

        skills = [
            skill
            for skill in SKILLS_LEXICON
            if re.search(rf"(?i)\b{re.escape(skill)}\b", description)
        ]
        programming = [
            skill
            for skill in (
                "python",
                "java",
                "javascript",
                "typescript",
                "golang",
                "go",
                "rust",
                "c++",
                "c#",
                "ruby",
                "php",
                "swift",
                "kotlin",
                "scala",
                "r",
            )
            if re.search(rf"(?i)\b{re.escape(skill)}\b", description)
        ]
        frameworks = [
            skill
            for skill in (
                "pytorch",
                "tensorflow",
                "keras",
                "scikit-learn",
                "pandas",
                "numpy",
                "huggingface",
                "transformers",
                "langchain",
                "spark",
                "airflow",
                "dbt",
                "mlflow",
                "fastapi",
                "flask",
                "django",
                "react",
                "vue",
                "angular",
            )
            if re.search(rf"(?i)\b{re.escape(skill)}\b", description)
        ]
        cloud = [
            term
            for term in _CLOUD
            if re.search(rf"(?i)\b{re.escape(term)}\b", description)
        ]
        databases = [
            db
            for db in _DATABASES
            if re.search(rf"(?i)\b{re.escape(db)}\b", description)
        ]

        years = self._extract_years(description)
        education = self._extract_education(description)
        seniority = enricher._extract_experience_level(description)

        responsibilities = enricher._extract_responsibilities(description)
        if not responsibilities:
            responsibilities = enricher._extract_bullets(description)

        summary = self._build_summary(job)

        return JobAnalysis(
            summary=summary,
            required_skills=[
                skill
                for skill in skills
                if skill not in (programming + frameworks + cloud + databases)
            ][:12],
            preferred_skills=[],
            programming_languages=programming,
            frameworks=frameworks,
            cloud=cloud,
            databases=databases,
            years_experience=years,
            education=education,
            seniority=seniority,
            employment_type=job.employment_type,
            remote_type=job.remote_type,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            salary_currency=job.salary_currency,
            responsibilities=responsibilities[:10],
            preferred_qualifications=[],
            confidence=0.5,
            provider=self.name,
            model=None,
        )

    @staticmethod
    def _extract_years(description: str) -> int | None:
        match = _YEARS_RE.search(description)
        if not match:
            return None
        try:
            return int(match.group(1))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _extract_education(description: str) -> str | None:
        lowered = description.lower()
        for term, label in sorted(
            _EDUCATION_TERMS.items(), key=lambda item: -len(item[0])
        ):
            if term in lowered:
                return label
        return None

    @staticmethod
    def _build_summary(job: NormalizedJob) -> str:
        parts = [f"Opportunity for a {job.title} at {job.company}."]
        if job.remote_type.value != "onsite":
            parts.append(f"Offers {job.remote_type.value} work.")
        if job.salary_min or job.salary_max:
            parts.append("Includes stated compensation.")
        return " ".join(parts)
