"""Candidate profile HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from jobpilot.api.schemas import ProfileCreateRequest, ProfileResponse
from jobpilot.models.candidate import CandidateProfile
from jobpilot.services.candidate_service import candidate_service

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfileResponse])
def list_profiles() -> list[ProfileResponse]:
    """List candidate profiles."""
    return [
        _to_response(profile)
        for profile in candidate_service.list(include_inactive=True)
    ]


@router.post("", response_model=ProfileResponse, status_code=201)
def create_profile(data: ProfileCreateRequest) -> ProfileResponse:
    """Create a candidate profile."""
    profile = candidate_service.create(_to_model(data))
    return _to_response(profile)


@router.get("/active", response_model=ProfileResponse)
def get_active_profile() -> ProfileResponse:
    """Return the active candidate profile."""
    profile = candidate_service.get_active()
    if profile is None:
        raise HTTPException(status_code=404, detail="No active profile")
    return _to_response(profile)


@router.get("/{profile_id}", response_model=ProfileResponse)
def get_profile(profile_id: int) -> ProfileResponse:
    """Return one candidate profile."""
    profile = candidate_service.get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return _to_response(profile)


@router.put("/{profile_id}", response_model=ProfileResponse)
def update_profile(profile_id: int, data: ProfileCreateRequest) -> ProfileResponse:
    """Replace a candidate profile's fields."""
    updated = candidate_service.update(profile_id, _to_model(data))
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return _to_response(updated)


@router.post("/{profile_id}/activate", response_model=ProfileResponse)
def activate_profile(profile_id: int) -> ProfileResponse:
    """Make one profile the active matching profile."""
    activated = candidate_service.set_active(profile_id)
    if activated is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return _to_response(activated)


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: int) -> Response:
    """Delete a candidate profile."""
    if not candidate_service.delete(profile_id):
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return Response(status_code=204)


def _to_model(data: ProfileCreateRequest) -> CandidateProfile:
    return CandidateProfile(
        name=data.name,
        skills=data.skills,
        years_experience=data.years_experience,
        education=data.education,
        preferred_locations=data.preferred_locations,
        remote_preference=data.remote_preference,
        preferred_roles=data.preferred_roles,
        preferred_companies=data.preferred_companies,
        salary_expectation_min=data.salary_expectation_min,
        salary_expectation_max=data.salary_expectation_max,
        salary_currency=data.salary_currency,
    )


def _to_response(profile: CandidateProfile) -> ProfileResponse:
    return ProfileResponse(
        id=profile.id,
        name=profile.name,
        skills=profile.skills,
        years_experience=profile.years_experience,
        education=profile.education,
        preferred_locations=profile.preferred_locations,
        remote_preference=profile.remote_preference,
        preferred_roles=profile.preferred_roles,
        preferred_companies=profile.preferred_companies,
        salary_expectation_min=profile.salary_expectation_min,
        salary_expectation_max=profile.salary_expectation_max,
        salary_currency=profile.salary_currency,
        is_active=profile.is_active,
    )
