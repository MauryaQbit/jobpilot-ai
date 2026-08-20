"""Job normalization - convert raw postings into canonical jobs."""

from __future__ import annotations

import logging

from jobpilot.models.job_posting import JobPosting
from jobpilot.models.normalized_job import NormalizedJob
from jobpilot.scrapers.base import JobSource

logger = logging.getLogger(__name__)


class Normalizer:
    """Convert provider postings into validated :class:`NormalizedJob` objects.

    Any posting that fails validation is reported so the pipeline can track
    rejected rows instead of silently dropping them.
    """

    @staticmethod
    def normalize_posting(
        posting: JobPosting, source: JobSource | None = None
    ) -> NormalizedJob:
        return NormalizedJob.from_posting(posting, source=source)

    def normalize_batch(
        self,
        postings: list[JobPosting],
        source: JobSource | None = None,
    ) -> tuple[list[NormalizedJob], int]:
        """Normalize a batch, returning (valid jobs, rejected count)."""
        normalized: list[NormalizedJob] = []
        rejected = 0
        for posting in postings:
            try:
                normalized.append(self.normalize_posting(posting, source=source))
            except (ValueError, TypeError) as error:
                rejected += 1
                logger.warning(
                    "Rejected posting %r: %s", getattr(posting, "id", None), error
                )
        return normalized, rejected


normalizer = Normalizer()
