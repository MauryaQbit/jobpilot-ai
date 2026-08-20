"""Job enrichment - add derived signals before analysis and persistence.

Enrichment is deterministic and provider-independent. It extracts requirement
and responsibility bullets from description headings, mines skills from a
lexicon, and normalizes remote/location signals.
"""

from __future__ import annotations

import logging
import re

from jobpilot.constants import (
    SKILLS_LEXICON,
)
from jobpilot.models.enums import ExperienceLevel
from jobpilot.models.normalized_job import NormalizedJob
from jobpilot.utils.text import dedupe_keep_order, parse_domain_from_url

logger = logging.getLogger(__name__)

_SECTION_RE = re.compile(
    r"(?im)^\s*(?:requirements?|qualifications?|what\s+you(\'|\u2019)ll\s+need"
    r"|what\s+we(\'|\u2019)re\s+looking\s+for|you\s+have|about\s+you|must\s+have"
    r"|required|responsibilities?|what\s+you(\'|\u2019)ll\s+do|the\s+role|key\s+responsibilities"
    r"|duties?|you\s+will)\s*[:\-]?\s*$",
)

_YEARS_RE = re.compile(r"(\d+)\+?\s*(?:-|\s+to\s+)?\s*(\d+)?\s*years?", re.IGNORECASE)


class Enricher:
    """Enrich normalized jobs with deterministic derived signals."""

    def __init__(self, skills_lexicon: list[str] | None = None) -> None:
        self.skills_lexicon = skills_lexicon or SKILLS_LEXICON

    def enrich(self, job: NormalizedJob) -> NormalizedJob:
        description = job.description or ""
        job.requirements = dedupe_keep_order(
            job.requirements or self._extract_requirements(description)
        )
        job.responsibilities = dedupe_keep_order(
            job.responsibilities or self._extract_responsibilities(description)
        )
        mined_skills = self._mine_skills(description)
        job.skills = dedupe_keep_order([*job.skills, *mined_skills])
        job.experience_level = job.experience_level or self._extract_experience_level(
            description
        )
        job.company_domain = job.company_domain or parse_domain_from_url(job.url)
        return job

    def _split_sections(self, description: str) -> tuple[str, str]:
        """Split description into (requirements text, responsibilities text)."""
        lines = [line.strip() for line in description.splitlines() if line.strip()]
        requirement_lines: list[str] = []
        responsibility_lines: list[str] = []
        current: str | None = None
        for line in lines:
            if _SECTION_RE.match(line):
                current = (
                    "requirements"
                    if any(
                        token in line.lower()
                        for token in (
                            "requirement",
                            "qualification",
                            "need",
                            "looking",
                            "have",
                            "must",
                            "required",
                        )
                    )
                    else "responsibilities"
                )
                continue
            if current == "requirements":
                requirement_lines.append(line)
            elif current == "responsibilities":
                responsibility_lines.append(line)
        return " ".join(requirement_lines), " ".join(responsibility_lines)

    def _extract_requirements(self, description: str) -> list[str]:
        requirements_text, _ = self._split_sections(description)
        bullets = self._extract_bullets(requirements_text)
        if not bullets and requirements_text:
            bullets = self._extract_bullets(description)
        return bullets

    def _extract_responsibilities(self, description: str) -> list[str]:
        _, responsibilities_text = self._split_sections(description)
        return self._extract_bullets(responsibilities_text)

    @staticmethod
    def _extract_bullets(text: str) -> list[str]:
        bullets: list[str] = []
        for line in text.splitlines():
            candidate = re.sub(r"^\s*[\u2022\-\*\d+\.\)\s]+", "", line).strip()
            if len(candidate) >= 12 and not _SECTION_RE.match(candidate):
                bullets.append(candidate)
        return dedupe_keep_order(bullets)[:25]

    def _mine_skills(self, description: str) -> list[str]:
        lowered = description.lower()
        return [
            skill
            for skill in self.skills_lexicon
            if re.search(rf"(?i)\b{re.escape(skill)}\b", description)
            or skill in lowered
        ]

    @staticmethod
    def _extract_experience_level(description: str) -> ExperienceLevel | None:
        lowered = description.lower()
        level = ExperienceLevel.normalize(
            next(
                (
                    word
                    for word in (
                        "principal",
                        "staff",
                        "senior",
                        "junior",
                        "entry",
                        "lead",
                        "manager",
                    )
                    if word in lowered
                ),
                None,
            )
        )
        if level is not None:
            return level
        match = _YEARS_RE.search(description)
        if match:
            try:
                years = int(match.group(1))
                return ExperienceLevel.from_years(years)
            except (ValueError, TypeError):
                return None
        return None


enricher = Enricher()
