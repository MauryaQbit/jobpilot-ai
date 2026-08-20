"""JobSpy-backed job source.

This source wraps the ``jobspy`` library and converts its DataFrame output into
validated :class:`JobPosting` models. It preserves the validation and error
handling behavior of the derived ``ai-job-scraper`` project while exposing it
through the :class:`JobSource` interface.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pandas as pd
from jobspy import scrape_jobs

from jobpilot.models.enums import JobSite
from jobpilot.models.job_posting import JobPosting, JobScrapeRequest, JobScrapeResult
from jobpilot.scrapers.base import SourceHealth

logger = logging.getLogger(__name__)

_NAME = "jobspy"


class JobSpySource:
    """Job-source adapter around the JobSpy library."""

    name: str = _NAME

    def __init__(self) -> None:
        self.default_settings = {
            "results_wanted": 100,
            "country_indeed": "USA",
            "linkedin_fetch_description": True,
            "linkedin_company_fetch_description": True,
            "description_format": "markdown",
        }

    async def fetch_jobs_async(self, request: JobScrapeRequest) -> JobScrapeResult:
        """Scrape jobs asynchronously using JobSpy."""
        return await asyncio.to_thread(self.fetch_jobs, request)

    def fetch_jobs(self, request: JobScrapeRequest) -> JobScrapeResult:
        """Scrape jobs synchronously and convert them to validated postings."""
        try:
            scrape_params = self._build_scrape_params(request)
            logger.info("Starting JobSpy scraping with params: %s", scrape_params)
            jobs_df = scrape_jobs(**scrape_params)

            if jobs_df is None or jobs_df.empty:
                logger.warning("JobSpy returned empty or None DataFrame")
                return self._empty_result(request)

            logger.info("JobSpy found %d jobs", len(jobs_df))
            jobs, invalid_rows = self._dataframe_to_models(jobs_df, request.site_name)
            raw_found = len(jobs_df)
            metadata: dict[str, Any] = {
                "scraping_method": _NAME,
                "success": bool(jobs),
                "raw_found": raw_found,
                "valid_rows": len(jobs),
                "invalid_rows": invalid_rows,
            }
            if invalid_rows:
                row_label = "row" if raw_found == 1 else "rows"
                message = f"{invalid_rows} of {raw_found} provider {row_label} failed validation"
                metadata["warning" if jobs else "error"] = message

            return JobScrapeResult(
                jobs=jobs,
                total_found=len(jobs),
                request_params=request,
                metadata=metadata,
            )
        except Exception:
            logger.exception("JobSpy scraping failed")
            return self._empty_result(request, error="Scraping operation failed")

    def health_check(self) -> SourceHealth:
        """Report availability based on importability and a quick probe."""
        error: str | None = None
        available = False
        try:
            scrape_jobs  # noqa: B018 - import availability probe
            available = True
        except Exception as exc:  # pragma: no cover - defensive
            error = str(exc)
        return SourceHealth(
            source=self.name,
            available=available,
            last_error=error,
            metadata={"library": "jobspy"},
        )

    def _build_scrape_params(self, request: JobScrapeRequest) -> dict[str, Any]:
        params = self.default_settings.copy()
        if isinstance(request.site_name, list):
            params["site_name"] = [site.value for site in request.site_name]
        else:
            params["site_name"] = [request.site_name.value]

        params.update(
            {
                "search_term": request.search_term,
                "google_search_term": request.google_search_term,
                "location": request.location,
                "distance": request.distance,
                "is_remote": request.is_remote,
                "results_wanted": request.results_wanted,
                "country_indeed": request.country_indeed,
                "offset": request.offset,
                "hours_old": request.hours_old,
                "enforce_annual_salary": request.enforce_annual_salary,
                "linkedin_fetch_description": request.linkedin_fetch_description,
                "description_format": request.description_format,
            }
        )
        if request.job_type:
            params["job_type"] = request.job_type.value
        if request.easy_apply is not None:
            params["easy_apply"] = request.easy_apply
        return {k: v for k, v in params.items() if v is not None}

    def _dataframe_to_models(
        self,
        jobs_df: pd.DataFrame,
        requested_sites: list[JobSite] | JobSite,
    ) -> tuple[list[JobPosting], int]:
        jobs: list[JobPosting] = []
        default_site = (
            requested_sites
            if isinstance(requested_sites, JobSite)
            else requested_sites[0]
        )

        for _, row in jobs_df.iterrows():
            try:
                job_data: dict[str, Any] = {}
                for col, value in row.items():
                    if (pd.api.types.is_scalar(value) and pd.isna(value)) or (
                        isinstance(value, str) and not value.strip()
                    ):
                        job_data[col] = None
                    elif isinstance(value, pd.Timestamp):
                        job_data[col] = value.date() if hasattr(value, "date") else None
                    else:
                        job_data[col] = value

                if "id" not in job_data or not job_data["id"]:
                    job_data["id"] = (
                        job_data.get("job_url_direct") or job_data.get("job_url") or ""
                    )
                if "site" not in job_data or not job_data["site"]:
                    job_data["site"] = default_site

                job_data["min_amount"] = self._safe_float(job_data.get("min_amount"))
                job_data["max_amount"] = self._safe_float(job_data.get("max_amount"))
                job_data["company_rating"] = self._safe_float(
                    job_data.get("company_rating")
                )

                jobs.append(JobPosting.model_validate(job_data))
            except (TypeError, ValueError) as error:
                logger.warning("Skipped invalid job row: %s", error)
                continue

        invalid_rows = len(jobs_df) - len(jobs)
        logger.info(
            "Converted %d provider rows; %d failed validation",
            len(jobs),
            invalid_rows,
        )
        return jobs, invalid_rows

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _empty_result(
        self, request: JobScrapeRequest, error: str | None = None
    ) -> JobScrapeResult:
        metadata: dict[str, Any] = {
            "scraping_method": _NAME,
            "success": error is None,
            "raw_found": 0,
            "valid_rows": 0,
            "invalid_rows": 0,
        }
        if error:
            metadata["error"] = error
        return JobScrapeResult(
            jobs=[],
            total_found=0,
            request_params=request,
            metadata=metadata,
        )


jobspy_source = JobSpySource()
