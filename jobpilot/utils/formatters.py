"""Salary parsing and formatting helpers for JobPilot AI."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from price_parser import Price

type SalaryTuple = tuple[int | None, int | None]

_UP_TO_PATTERN = re.compile(
    r"\b(?:up\s+to|maximum\s+of|max\s+of|not\s+more\s+than)\b", re.IGNORECASE
)
_FROM_PATTERN = re.compile(
    r"\b(?:from|starting\s+at|minimum\s+of|min\s+of|at\s+least)\b", re.IGNORECASE
)
_CURRENCY_PATTERN = re.compile(r"[£$€¥¢₹]")
_RANGE_K_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*([kK])")
_BOTH_K_PATTERN = re.compile(r"(\d+(?:\.\d+)?)([kK])\s*-\s*(\d+(?:\.\d+)?)([kK])")
_ONE_SIDED_K_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)([kK])\s*-\s*(\d+(?:\.\d+)?)(?!\s*[kK])"
)
_HOURLY_PATTERN = re.compile(r"\b(?:per\s+hour|hourly|/hour|/hr)\b", re.IGNORECASE)
_MONTHLY_PATTERN = re.compile(r"\b(?:per\s+month|monthly|/month|/mo)\b", re.IGNORECASE)

_PHRASES_TO_REMOVE = [
    r"\b(?:per\s+year|per\s+annum|annually|yearly|p\.?a\.?|/year|/yr)\b",
    r"\b(?:gross|net|before\s+tax|after\s+tax)\b",
    r"\b(?:plus\s+benefits?|\+\s*benefits?)\b",
    r"\b(?:negotiable|neg\.?|ono|o\.?n\.?o\.?)\b",
    r"\b(?:depending\s+on\s+experience|doe)\b",
]

DEFAULT_WEEKLY_HOURS = 40
DEFAULT_WORKING_WEEKS_PER_YEAR = 52
DEFAULT_MONTHS_PER_YEAR = 12


@dataclass(frozen=True)
class _SalaryContext:
    is_up_to: bool = False
    is_from: bool = False
    is_hourly: bool = False
    is_monthly: bool = False


@dataclass(frozen=True)
class _SimplePrice:
    amount: object


class SalaryParser:
    """Robust salary text parser normalizing to an annual ``(min, max)`` pair.

    This is an evolution of the original ``LibrarySalaryParser`` from the
    derived ``ai-job-scraper`` project, retaining the library-first strategy
    while simplifying conversion helpers and adding currency capture.
    """

    @staticmethod
    def parse_salary_text(text: str) -> SalaryTuple:
        if not text or not text.strip():
            return (None, None)

        original = text.strip()
        context = SalaryParser._detect_context(original)
        result = SalaryParser._parse_range(original, context)
        if result != (None, None):
            return result
        return SalaryParser._parse_single(original, context)

    @staticmethod
    def _detect_context(text: str) -> _SalaryContext:
        return _SalaryContext(
            is_up_to=bool(_UP_TO_PATTERN.search(text)),
            is_from=bool(_FROM_PATTERN.search(text)),
            is_hourly=bool(_HOURLY_PATTERN.search(text)),
            is_monthly=bool(_MONTHLY_PATTERN.search(text)),
        )

    @staticmethod
    def _parse_range(text: str, context: _SalaryContext) -> SalaryTuple:
        k_range = SalaryParser._parse_k_suffix_ranges(text)
        if k_range:
            minimum, maximum = k_range
            converted = SalaryParser._convert_time_based(
                [minimum, maximum], context.is_hourly, context.is_monthly
            )
            return (converted[0], converted[1])

        prices = SalaryParser._extract_multiple_prices(text)
        if len(prices) >= 2:
            values = [int(price.amount) for price in prices if price.amount]
            if values:
                converted = SalaryParser._convert_time_based(
                    values, context.is_hourly, context.is_monthly
                )
                return (min(converted), max(converted))
        return (None, None)

    @staticmethod
    def _parse_single(text: str, context: _SalaryContext) -> SalaryTuple:
        k_match = re.search(r"(\d+(?:\.\d+)?)\s*[kK]\b", text)
        if k_match:
            try:
                value = int(float(k_match.group(1)) * 1000)
                converted = SalaryParser._convert_time_based(
                    [value], context.is_hourly, context.is_monthly
                )
                return SalaryParser._apply_context(converted[0], context)
            except (ValueError, TypeError):
                pass

        try:
            price = Price.fromstring(text)
            if price.amount:
                value = int(price.amount)
                converted = SalaryParser._convert_time_based(
                    [value], context.is_hourly, context.is_monthly
                )
                return SalaryParser._apply_context(converted[0], context)
        except (ValueError, TypeError, AttributeError):
            pass

        return SalaryParser._parse_fallback(text, context)

    @staticmethod
    def _parse_fallback(text: str, context: _SalaryContext) -> SalaryTuple:
        cleaned = _CURRENCY_PATTERN.sub("", text)
        for pattern in _PHRASES_TO_REMOVE:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        cleaned = _UP_TO_PATTERN.sub("", cleaned)
        cleaned = _FROM_PATTERN.sub("", cleaned)
        cleaned = _HOURLY_PATTERN.sub("", cleaned)
        cleaned = _MONTHLY_PATTERN.sub("", cleaned)

        numbers = re.findall(r"\d+(?:\.\d+)?", cleaned)
        if not numbers:
            return (None, None)
        try:
            value = int(float(numbers[0]))
            if re.search(r"\d+(?:\.\d+)?\s*[kK]\b", text):
                value *= 1000
            converted = SalaryParser._convert_time_based(
                [value], context.is_hourly, context.is_monthly
            )
            return SalaryParser._apply_context(converted[0], context)
        except (ValueError, TypeError):
            return (None, None)

    @staticmethod
    def _apply_context(value: int, context: _SalaryContext) -> SalaryTuple:
        if context.is_up_to:
            return (None, value)
        if context.is_from:
            return (value, None)
        return (value, value)

    @staticmethod
    def _extract_multiple_prices(text: str) -> list[Price]:
        prices: list[Price] = []
        has_range = bool(
            re.search(r"range|to|between|from|up to", text, re.IGNORECASE)
            or re.search(r"[-\u2013\u2014]", text)
        )
        if not has_range:
            return prices

        parts = re.split(
            r"\s*[-\u2013\u2014]\s*|\s+to\s+|\s+between\s+", text, flags=re.IGNORECASE
        )
        valid_parts: list[str] = []
        for raw_part in parts:
            part = raw_part.strip()
            if len(part) < 2 or not re.search(r"\d", part):
                continue
            if re.search(
                r"\b(bonus|equity|stock|rsu)\b.*\d|\d.*\b(bonus|equity|stock|rsu)\b",
                part,
                re.IGNORECASE,
            ):
                continue
            valid_parts.append(part)

        if not 2 <= len(valid_parts) <= 3:
            return prices

        for part in valid_parts:
            k_match = re.search(r"(\d+(?:\.\d+)?)\s*[kK]\b", part)
            if k_match:
                try:
                    amount = float(k_match.group(1)) * 1000
                    prices.append(_SimplePrice(amount=amount))  # type: ignore[arg-type]
                    continue
                except (ValueError, TypeError):
                    continue
            try:
                price = Price.fromstring(part)
                if price.amount and price.amount >= 10:
                    prices.append(price)
            except (ValueError, TypeError, AttributeError):
                continue
        return prices

    @staticmethod
    def _parse_k_suffix_ranges(text: str) -> tuple[int, int] | None:
        to_pattern = re.search(
            r"(\d+(?:\.\d+)?)\s*[kK]\s+to\s+(\d+(?:\.\d+)?)\s*[kK]",
            text,
            re.IGNORECASE,
        )
        if to_pattern:
            try:
                val1 = int(float(to_pattern.group(1)) * 1000)
                val2 = int(float(to_pattern.group(2)) * 1000)
                return (min(val1, val2), max(val1, val2))
            except (ValueError, TypeError):
                pass

        for pattern in (_BOTH_K_PATTERN, _RANGE_K_PATTERN, _ONE_SIDED_K_PATTERN):
            match = pattern.search(text)
            if not match:
                continue
            try:
                numeric = [
                    group
                    for group in match.groups()
                    if group and re.fullmatch(r"\d+(?:\.\d+)?", group)
                ]
                if len(numeric) < 2:
                    continue
                values = [int(float(number) * 1000) for number in numeric[:2]]
                return (min(values), max(values))
            except (ValueError, TypeError):
                continue
        return None

    @staticmethod
    def _convert_time_based(
        values: Sequence[int],
        is_hourly: bool,
        is_monthly: bool,
        *,
        weekly_hours: int = DEFAULT_WEEKLY_HOURS,
        working_weeks: int = DEFAULT_WORKING_WEEKS_PER_YEAR,
    ) -> list[int]:
        if is_hourly:
            return [int(value * weekly_hours * working_weeks) for value in values]
        if is_monthly:
            return [int(value * DEFAULT_MONTHS_PER_YEAR) for value in values]
        return list(values)


def parse_salary(value: object) -> SalaryTuple:
    """Parse a string, tuple, or list into a ``(min, max)`` salary pair."""
    if isinstance(value, tuple | list) and len(value) == 2:
        minimum, maximum = value
        return (
            None if minimum is None else int(minimum),
            None if maximum is None else int(maximum),
        )
    if value is None or not isinstance(value, str) or not value.strip():
        return (None, None)
    return SalaryParser.parse_salary_text(value.strip())


def format_salary_range(salary: SalaryTuple | None) -> str:
    """Format an optional minimum and maximum salary for display."""
    if not salary or salary == (None, None):
        return "Not specified"

    minimum, maximum = salary
    if minimum and maximum:
        if minimum == maximum:
            return f"${minimum:,}"
        return f"${minimum:,} - ${maximum:,}"
    if minimum:
        return f"${minimum:,}+"
    if maximum:
        return f"Up to ${maximum:,}"
    return "Not specified"


def relative_time(value: datetime | None) -> str:
    """Format a timestamp for compact UI copy without extra dependencies."""
    if value is None:
        return "Never"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - value
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 604800:
        return f"{seconds // 86400}d ago"
    return value.strftime("%b %d, %Y")
