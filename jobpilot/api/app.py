"""FastAPI application for JobPilot AI.

Exposes the service layer over HTTP: jobs, analysis, matching,
recommendations, candidate profiles, application tracking, saved searches,
scraper-run observability, and cost/budget health.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from jobpilot import APP_NAME, __version__
from jobpilot.api.routes_applications import router as applications_router
from jobpilot.api.routes_jobs import router as jobs_router
from jobpilot.api.routes_meta import router as meta_router
from jobpilot.api.routes_profiles import router as profiles_router
from jobpilot.api.routes_searches import router as searches_router
from jobpilot.config import configure_logging, get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Apply pending schema migrations before serving traffic."""
    configure_logging(get_settings())
    from jobpilot.database.migrations import run_migrations

    run_migrations()
    yield


settings = get_settings()
app = FastAPI(
    title=APP_NAME,
    version=__version__,
    description="AI-powered job discovery, matching and application intelligence.",
    lifespan=lifespan,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(meta_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(profiles_router, prefix="/api")
app.include_router(applications_router, prefix="/api")
app.include_router(searches_router, prefix="/api")


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    """Return a tiny identity banner."""
    return {"app": APP_NAME, "version": __version__, "docs": "/docs"}
