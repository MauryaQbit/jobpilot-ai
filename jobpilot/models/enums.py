"""Enumerated domain values for JobPilot AI."""

from __future__ import annotations

from enum import StrEnum


class JobSite(StrEnum):
    """Supported job-board sources."""

    LINKEDIN = "linkedin"
    INDEED = "indeed"
    GLASSDOOR = "glassdoor"
    ZIP_RECRUITER = "zip_recruiter"
    GOOGLE = "google"

    @classmethod
    def normalize(cls, value: str | None) -> JobSite | None:
        if not value:
            return None
        normalized = value.lower().strip().replace("-", "_").replace(" ", "_")
        mapping = {
            "linkedin": cls.LINKEDIN,
            "indeed": cls.INDEED,
            "glassdoor": cls.GLASSDOOR,
            "zip_recruiter": cls.ZIP_RECRUITER,
            "ziprecruiter": cls.ZIP_RECRUITER,
            "google": cls.GOOGLE,
        }
        return mapping.get(normalized)


class EmploymentType(StrEnum):
    """Job employment types."""

    FULLTIME = "full_time"
    PARTTIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"

    @classmethod
    def normalize(cls, value: str | None) -> EmploymentType | None:
        if not value:
            return None
        normalized = (
            value.lower().strip().replace("-", "").replace("_", "").replace(" ", "")
        )
        mapping = {
            "fulltime": cls.FULLTIME,
            "full": cls.FULLTIME,
            "permanent": cls.FULLTIME,
            "parttime": cls.PARTTIME,
            "part": cls.PARTTIME,
            "contract": cls.CONTRACT,
            "contractor": cls.CONTRACT,
            "internship": cls.INTERNSHIP,
            "intern": cls.INTERNSHIP,
            "temporary": cls.TEMPORARY,
            "temp": cls.TEMPORARY,
        }
        return mapping.get(normalized)


class RemoteType(StrEnum):
    """Work location types."""

    REMOTE = "remote"
    ONSITE = "onsite"
    HYBRID = "hybrid"

    @classmethod
    def from_flags(
        cls, is_remote: bool | None, location: str | None = None
    ) -> RemoteType:
        if is_remote:
            return cls.REMOTE
        if location:
            lowered = location.lower()
            if "hybrid" in lowered:
                return cls.HYBRID
            if "remote" in lowered or "work from home" in lowered or "wfh" in lowered:
                return cls.REMOTE
        return cls.ONSITE

    @classmethod
    def normalize(cls, value: str | None) -> RemoteType | None:
        if not value:
            return None
        normalized = value.lower().strip()
        mapping = {
            "remote": cls.REMOTE,
            "fully remote": cls.REMOTE,
            "100% remote": cls.REMOTE,
            "hybrid": cls.HYBRID,
            "onsite": cls.ONSITE,
            "on-site": cls.ONSITE,
            "on site": cls.ONSITE,
            "in-office": cls.ONSITE,
        }
        return mapping.get(normalized)


class ApplicationStage(StrEnum):
    """Canonical application-tracking workflow for JobPilot AI."""

    INBOX = "Inbox"
    SAVED = "Saved"
    APPLIED = "Applied"
    SCREENING = "Screening"
    INTERVIEW = "Interview"
    OFFER = "Offer"
    REJECTED = "Rejected"

    @classmethod
    def is_terminal(cls, value: ApplicationStage) -> bool:
        return value in {cls.OFFER, cls.REJECTED}

    @classmethod
    def active_stages(cls) -> tuple[ApplicationStage, ...]:
        return (
            cls.INBOX,
            cls.SAVED,
            cls.APPLIED,
            cls.SCREENING,
            cls.INTERVIEW,
            cls.OFFER,
        )


class JobStatus(StrEnum):
    """Lifecycle state of a discovered job record."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class ScraperRunStatus(StrEnum):
    """Finite lifecycle states for one scraper run."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SavedSearchRunStatus(StrEnum):
    """Finite lifecycle states for one saved-search run."""

    NEVER = "never"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExperienceLevel(StrEnum):
    """Normalized seniority buckets used for matching."""

    ENTRY = "entry"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    LEAD = "lead"
    MANAGER = "manager"

    @classmethod
    def normalize(cls, value: str | None) -> ExperienceLevel | None:
        if not value:
            return None
        normalized = value.lower().strip()
        mapping = {
            "entry": cls.ENTRY,
            "entry level": cls.ENTRY,
            "junior": cls.JUNIOR,
            "jr": cls.JUNIOR,
            "mid": cls.MID,
            "mid level": cls.MID,
            "intermediate": cls.MID,
            "senior": cls.SENIOR,
            "sr": cls.SENIOR,
            "sr.": cls.SENIOR,
            "staff": cls.STAFF,
            "principal": cls.PRINCIPAL,
            "lead": cls.LEAD,
            "manager": cls.MANAGER,
            "director": cls.MANAGER,
        }
        return mapping.get(normalized)

    @classmethod
    def from_years(cls, years: float | int | None) -> ExperienceLevel:
        if years is None:
            return cls.MID
        if years < 2:
            return cls.JUNIOR
        if years < 5:
            return cls.MID
        if years < 8:
            return cls.SENIOR
        return cls.STAFF


class Currency(StrEnum):
    """Currencies recognized in salary normalization."""

    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    CAD = "CAD"
    AUD = "AUD"
    INR = "INR"
    JPY = "JPY"

    @classmethod
    def normalize(cls, value: str | None) -> Currency | None:
        if not value:
            return None
        normalized = value.strip().upper()
        mapping = {
            "USD": cls.USD,
            "$": cls.USD,
            "US$": cls.USD,
            "EUR": cls.EUR,
            "€": cls.EUR,
            "GBP": cls.GBP,
            "£": cls.GBP,
            "CAD": cls.CAD,
            "C$": cls.CAD,
            "AUD": cls.AUD,
            "A$": cls.AUD,
            "INR": cls.INR,
            "₹": cls.INR,
            "JPY": cls.JPY,
            "¥": cls.JPY,
        }
        return mapping.get(normalized)
