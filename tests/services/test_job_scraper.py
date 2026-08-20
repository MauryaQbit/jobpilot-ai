"""Focused unit tests for the JobSpy adapter."""

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest
from jobpilot.models.enums import EmploymentType, JobSite, RemoteType
from jobpilot.models.job_posting import JobPosting, JobScrapeRequest
from jobpilot.scrapers.jobspy_source import JobSpySource, jobspy_source


def _request(**updates):
    values = {
        "site_name": [JobSite.LINKEDIN, JobSite.INDEED],
        "search_term": "AI engineer",
        "location": "Denver",
        "is_remote": True,
        "results_wanted": 20,
    }
    values.update(updates)
    return JobScrapeRequest(**values)


def test_global_scraper_and_defaults_are_ready():
    assert isinstance(jobspy_source, JobSpySource)
    assert jobspy_source.default_settings["results_wanted"] == 100
    assert jobspy_source.default_settings["description_format"] == "markdown"


def test_build_scrape_params_maps_typed_contract():
    params = JobSpySource()._build_scrape_params(
        _request(job_type=EmploymentType.FULLTIME, easy_apply=True)
    )

    assert params["site_name"] == ["linkedin", "indeed"]
    assert params["search_term"] == "AI engineer"
    assert params["location"] == "Denver"
    assert params["is_remote"] is True
    assert params["results_wanted"] == 20
    assert params["job_type"] == "full_time"
    assert params["easy_apply"] is True
    assert all(value is not None for value in params.values())


def test_build_scrape_params_accepts_single_site():
    params = JobSpySource()._build_scrape_params(_request(site_name=JobSite.GLASSDOOR))
    assert params["site_name"] == ["glassdoor"]


@pytest.mark.parametrize(
    ("is_remote", "location", "expected"),
    [
        (True, "Denver", RemoteType.REMOTE),
        (False, "Hybrid — Denver", RemoteType.HYBRID),
        (False, "Denver", RemoteType.ONSITE),
    ],
)
def test_posting_derives_omitted_location_type(is_remote, location, expected):
    posting = JobPosting(
        id="one",
        site=JobSite.LINKEDIN,
        title="AI Engineer",
        company="Acme",
        job_url="https://example.com/one",
        is_remote=is_remote,
        location=location,
    )

    assert posting.location_type is expected


def test_posting_preserves_explicit_location_type():
    posting = JobPosting(
        id="one",
        site=JobSite.LINKEDIN,
        title="AI Engineer",
        company="Acme",
        job_url="https://example.com/one",
        is_remote=True,
        location="Remote",
        location_type=RemoteType.ONSITE,
    )

    assert posting.location_type is RemoteType.ONSITE


def test_sync_scrape_converts_valid_rows_and_reports_raw_count():
    frame = pd.DataFrame(
        [
            {
                "id": "one",
                "site": "linkedin",
                "title": "AI Engineer",
                "company": "Acme",
                "job_url": "https://example.com/one",
                "date_posted": date.today(),
            },
            {
                "id": "invalid",
                "site": "linkedin",
                "title": "Missing URL",
                "company": "Acme",
            },
        ]
    )
    with patch("jobpilot.scrapers.jobspy_source.scrape_jobs", return_value=frame):
        result = JobSpySource().fetch_jobs(_request())

    assert [job.id for job in result.jobs] == ["one"]
    assert result.total_found == 1
    assert result.metadata == {
        "scraping_method": "jobspy",
        "success": True,
        "raw_found": 2,
        "valid_rows": 1,
        "invalid_rows": 1,
        "warning": "1 of 2 provider rows failed validation",
    }


@pytest.mark.parametrize("provider_value", [None, pd.DataFrame()])
def test_empty_provider_result_is_a_successful_zero_result(provider_value):
    with patch(
        "jobpilot.scrapers.jobspy_source.scrape_jobs", return_value=provider_value
    ):
        result = JobSpySource().fetch_jobs(_request())

    assert result.jobs == []
    assert result.total_found == 0
    assert result.metadata == {
        "scraping_method": "jobspy",
        "success": True,
        "raw_found": 0,
        "valid_rows": 0,
        "invalid_rows": 0,
    }


def test_provider_exception_returns_failed_result():
    with patch(
        "jobpilot.scrapers.jobspy_source.scrape_jobs",
        side_effect=TimeoutError("timed out"),
    ):
        result = JobSpySource().fetch_jobs(_request())

    assert result.jobs == []
    assert result.total_found == 0
    assert result.metadata == {
        "scraping_method": "jobspy",
        "success": False,
        "raw_found": 0,
        "valid_rows": 0,
        "invalid_rows": 0,
        "error": "Scraping operation failed",
    }


def test_all_invalid_provider_rows_are_an_explicit_failure():
    frame = pd.DataFrame(
        [
            {
                "id": "invalid",
                "site": "linkedin",
                "title": "Missing URL",
                "company": "Acme",
            }
        ]
    )
    with patch("jobpilot.scrapers.jobspy_source.scrape_jobs", return_value=frame):
        result = JobSpySource().fetch_jobs(_request())

    assert result.jobs == []
    assert result.total_found == 0
    assert result.metadata == {
        "scraping_method": "jobspy",
        "success": False,
        "raw_found": 1,
        "valid_rows": 0,
        "invalid_rows": 1,
        "error": "1 of 1 provider row failed validation",
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("120000.50", 120000.5),
        (120000, 120000.0),
        (None, None),
        ("", None),
        ("not-a-number", None),
    ],
)
def test_safe_float(value, expected):
    assert JobSpySource()._safe_float(value) == expected
