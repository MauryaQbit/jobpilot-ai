"""Utility helpers for the JobPilot AI application."""

from __future__ import annotations

from jobpilot.utils.formatters import (
    SalaryParser,
    format_salary_range,
    parse_salary,
    relative_time,
)
from jobpilot.utils.text import (
    dedupe_keep_order,
    job_fingerprint,
    normalize_company_name,
    parse_domain_from_url,
    safe_int,
    similarity,
    slugify,
    url_fingerprint,
)

__all__ = [
    "SalaryParser",
    "dedupe_keep_order",
    "format_salary_range",
    "job_fingerprint",
    "normalize_company_name",
    "parse_domain_from_url",
    "parse_salary",
    "relative_time",
    "safe_int",
    "similarity",
    "slugify",
    "url_fingerprint",
]
