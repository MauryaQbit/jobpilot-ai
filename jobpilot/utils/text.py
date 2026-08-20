"""Utility helpers shared across JobPilot AI modules."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from difflib import SequenceMatcher

_WORD_RE = re.compile(r"[a-z0-9]+")


def slugify(value: str) -> str:
    """Return a lowercase, word-only slug suitable for fingerprinting."""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(_WORD_RE.findall(value.lower()))


def normalize_company_name(value: str) -> str:
    """Normalize a company name for duplicate detection."""
    slug = slugify(value)
    slug = re.sub(r"\b(inc|llc|ltd|limited|corp|corporation|gmbh|sarl|sa)\b", "", slug)
    return re.sub(r"\s+", " ", slug).strip()


def similarity(a: str, b: str) -> float:
    """Return a 0.0-1.0 text similarity score between two normalized strings."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def job_fingerprint(
    *, title: str, company: str, location: str, description: str
) -> str:
    """Build a deterministic content fingerprint for deduplication."""
    content = "|".join(
        [
            slugify(title),
            normalize_company_name(company),
            slugify(location),
            slugify(description or "")[:4000],
        ]
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def url_fingerprint(url: str) -> str:
    """Hash a canonicalized URL for deduplication."""
    normalized = re.sub(r"[?#].*$", "", (url or "").strip().rstrip("/"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def safe_int(value: object, default: int | None = None) -> int | None:
    """Convert a value to int, returning the default on failure."""
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return default


def parse_domain_from_url(url: str | None) -> str | None:
    """Extract a bare domain (no scheme, no www) from a URL."""
    if not url:
        return None
    match = re.search(r"(?:https?://)?(?:www\.)?([^/]+)", url.strip())
    if not match:
        return None
    domain = match.group(1).lower()
    return domain.split(":")[0] if domain else None


def dedupe_keep_order(values: list[str]) -> list[str]:
    """Remove duplicates from a list while preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(value.strip())
    return result
