"""Multi-signal job deduplication.

Duplicates are detected with layered signals so the same position advertised on
multiple boards is stored once:

1. Deterministic content hash over normalized title/company/location/description.
2. Canonical URL fingerprint.
3. Provider (source, source_job_id) pair.
4. Fuzzy similarity of normalized company + title + location + description.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from pydantic import BaseModel, Field

from jobpilot.models.normalized_job import NormalizedJob
from jobpilot.utils.text import similarity, slugify, url_fingerprint

DESCRIPTION_SIMILARITY_THRESHOLD = 0.85


class DedupResult(BaseModel):
    """Outcome of a deduplication pass over a batch of jobs."""

    unique_jobs: list[NormalizedJob]
    duplicates: list[NormalizedJob] = Field(default_factory=list)
    groups: list[list[NormalizedJob]] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)


@dataclass
class _Group:
    """Working group of jobs that represent the same position."""

    jobs: list[NormalizedJob] = field(default_factory=list)

    @property
    def canonical(self) -> NormalizedJob:
        """Pick the richest job as the group representative."""
        return max(
            self.jobs,
            key=lambda job: (
                len(job.description or ""),
                len(job.skills),
                job.salary_min is not None,
                len(job.requirements),
            ),
        )


class Deduplicator:
    """Deduplicate jobs using deterministic and fuzzy signals."""

    def __init__(
        self, *, fuzzy_threshold: float = DESCRIPTION_SIMILARITY_THRESHOLD
    ) -> None:
        if not 0.0 <= fuzzy_threshold <= 1.0:
            raise ValueError("fuzzy_threshold must be between 0 and 1")
        self.fuzzy_threshold = fuzzy_threshold

    def deduplicate(self, jobs: list[NormalizedJob]) -> DedupResult:
        groups: list[_Group] = []
        used_signals: set[str] = set()

        for job in jobs:
            placed = self._match_into_groups(job, groups, used_signals)
            if placed is None:
                groups.append(_Group(jobs=[job]))

        unique_jobs = [group.canonical for group in groups]
        duplicates = [
            job for group in groups for job in group.jobs if job is not group.canonical
        ]
        duplicate_groups = [group.jobs for group in groups if len(group.jobs) > 1]
        return DedupResult(
            unique_jobs=unique_jobs,
            duplicates=duplicates,
            groups=duplicate_groups,
            signals=sorted(used_signals),
        )

    def _match_into_groups(
        self,
        job: NormalizedJob,
        groups: list[_Group],
        used_signals: set[str],
    ) -> _Group | None:
        # Exact signals first.
        url_key = url_fingerprint(job.url)
        provider_key = f"{job.source.value}:{job.source_job_id}".strip(":")
        for group in groups:
            for existing in group.jobs:
                if url_key == url_fingerprint(existing.url):
                    used_signals.add("url")
                    group.jobs.append(job)
                    return group
                if (
                    job.job_hash
                    and existing.job_hash
                    and job.job_hash == existing.job_hash
                ):
                    used_signals.add("job_hash")
                    group.jobs.append(job)
                    return group
                if (
                    provider_key
                    and provider_key
                    == f"{existing.source.value}:{existing.source_job_id}".strip(":")
                ):
                    used_signals.add("source_job_id")
                    group.jobs.append(job)
                    return group

        # Fuzzy signal: same normalized company and similar title/location/description.
        for group in groups:
            for existing in group.jobs:
                if self._fuzzy_equivalent(job, existing):
                    used_signals.add("fuzzy")
                    group.jobs.append(job)
                    return group
        return None

    def _fuzzy_equivalent(self, a: NormalizedJob, b: NormalizedJob) -> bool:
        if slugify(a.company) != slugify(b.company):
            return False
        title_similarity = similarity(slugify(a.title), slugify(b.title))
        if title_similarity < 0.75:
            return False
        location_similarity = similarity(slugify(a.location), slugify(b.location))
        if location_similarity < 0.5 and a.location and b.location:
            return False
        desc_a = slugify(a.description)
        desc_b = slugify(b.description)
        if desc_a and desc_b:
            desc_similarity = SequenceMatcher(None, desc_a, desc_b).ratio()
            if desc_similarity < self.fuzzy_threshold:
                return False
        return True


deduplicator = Deduplicator()
