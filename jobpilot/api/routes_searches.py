"""Saved-search HTTP routes, including end-to-end run triggering."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response

from jobpilot.api.schemas import (
    RunOutcomeResponse,
    SavedSearchCreateRequest,
    SavedSearchResponse,
    SavedSearchUpdateRequest,
)
from jobpilot.services.runner import run_saved_search
from jobpilot.services.saved_search_service import (
    SavedSearchCreate,
    SavedSearchUpdate,
    saved_search_service,
)

router = APIRouter(prefix="/searches", tags=["searches"])


@router.get("", response_model=list[SavedSearchResponse])
def list_searches(enabled_only: bool = False) -> list[SavedSearchResponse]:
    """List saved searches and their latest run health."""
    return [
        SavedSearchResponse.from_dto(search)
        for search in saved_search_service.list(enabled_only=enabled_only)
    ]


@router.post("", response_model=SavedSearchResponse, status_code=201)
def create_search(data: SavedSearchCreateRequest) -> SavedSearchResponse:
    """Create a saved search definition."""
    search = saved_search_service.create(
        SavedSearchCreate.model_validate(data.model_dump())
    )
    return SavedSearchResponse.from_dto(search)


@router.get("/{search_id}", response_model=SavedSearchResponse)
def get_search(search_id: int) -> SavedSearchResponse:
    """Return one saved search."""
    search = saved_search_service.get(search_id)
    if search is None:
        raise HTTPException(
            status_code=404, detail=f"Saved search {search_id} not found"
        )
    return SavedSearchResponse.from_dto(search)


@router.put("/{search_id}", response_model=SavedSearchResponse)
def update_search(
    search_id: int, data: SavedSearchUpdateRequest
) -> SavedSearchResponse:
    """Update a saved search definition (partial)."""
    search = saved_search_service.update(
        search_id,
        SavedSearchUpdate.model_validate(data.model_dump(exclude_unset=True)),
    )
    if search is None:
        raise HTTPException(
            status_code=404, detail=f"Saved search {search_id} not found"
        )
    return SavedSearchResponse.from_dto(search)


@router.delete("/{search_id}", status_code=204)
def delete_search(search_id: int) -> Response:
    """Delete a saved search definition (persisted jobs remain)."""
    if not saved_search_service.delete(search_id):
        raise HTTPException(
            status_code=404, detail=f"Saved search {search_id} not found"
        )
    return Response(status_code=204)


@router.post("/{search_id}/run", response_model=RunOutcomeResponse, status_code=202)
def run_search(search_id: int, background_tasks: BackgroundTasks) -> RunOutcomeResponse:
    """Trigger an end-to-end discovery run for one saved search.

    The run executes in a background task; check the search's run health for
    the terminal result.
    """
    search = saved_search_service.get(search_id)
    if search is None:
        raise HTTPException(
            status_code=404, detail=f"Saved search {search_id} not found"
        )
    background_tasks.add_task(_run_search_in_background, search_id)
    return RunOutcomeResponse(
        search_id=search_id,
        search_name=search.name,
        status="queued",
    )


@router.post("/run-all", response_model=list[RunOutcomeResponse], status_code=202)
def run_all_searches(background_tasks: BackgroundTasks) -> list[RunOutcomeResponse]:
    """Trigger discovery runs for every enabled saved search."""
    searches = saved_search_service.list(enabled_only=True)
    for search in searches:
        background_tasks.add_task(_run_search_in_background, search.id)
    return [
        RunOutcomeResponse(
            search_id=search.id, search_name=search.name, status="queued"
        )
        for search in searches
    ]


def _run_search_in_background(search_id: int) -> None:
    asyncio.run(run_saved_search(search_id))
