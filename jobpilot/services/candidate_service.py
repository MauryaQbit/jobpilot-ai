"""Candidate profile service - CRUD for the matching engine's inputs."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import col, select

from jobpilot.database.engine import db_session
from jobpilot.database.models import CandidateProfileRow
from jobpilot.models.candidate import CandidateProfile


class CandidateService:
    """Create, read, update, and delete candidate profiles."""

    @staticmethod
    def _to_model(row: CandidateProfileRow) -> CandidateProfile:
        return CandidateProfile(
            id=row.id,
            name=row.name,
            skills=row.skills,
            years_experience=row.years_experience,
            education=row.education,
            preferred_locations=row.preferred_locations,
            remote_preference=row.remote_preference,
            preferred_roles=row.preferred_roles,
            preferred_companies=row.preferred_companies,
            salary_expectation_min=row.salary_expectation_min,
            salary_expectation_max=row.salary_expectation_max,
            salary_currency=row.salary_currency,
            is_active=row.is_active,
        )

    def list(self, *, include_inactive: bool = False) -> list[CandidateProfile]:
        with db_session() as session:
            statement = select(CandidateProfileRow)
            if not include_inactive:
                statement = statement.where(
                    col(CandidateProfileRow.is_active).is_(True)
                )
            rows = session.exec(
                statement.order_by(CandidateProfileRow.updated_at.desc())
            ).all()
            return [self._to_model(row) for row in rows]

    def get(self, profile_id: int) -> CandidateProfile | None:
        with db_session() as session:
            row = session.get(CandidateProfileRow, profile_id)
            return self._to_model(row) if row else None

    def get_active(self) -> CandidateProfile | None:
        with db_session() as session:
            row = session.exec(
                select(CandidateProfileRow)
                .where(col(CandidateProfileRow.is_active).is_(True))
                .order_by(CandidateProfileRow.updated_at.desc())
            ).first()
            return self._to_model(row) if row else None

    def create(self, profile: CandidateProfile) -> CandidateProfile:
        with db_session() as session:
            active_exists = (
                session.exec(
                    select(CandidateProfileRow.id).where(
                        col(CandidateProfileRow.is_active).is_(True)
                    )
                ).first()
                is not None
            )
            now = datetime.now(UTC)
            row = CandidateProfileRow(
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
                is_active=not active_exists,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            return self._to_model(row)

    def update(
        self, profile_id: int, profile: CandidateProfile
    ) -> CandidateProfile | None:
        with db_session() as session:
            row = session.get(CandidateProfileRow, profile_id)
            if row is None:
                return None
            row.name = profile.name
            row.skills = profile.skills
            row.years_experience = profile.years_experience
            row.education = profile.education
            row.preferred_locations = profile.preferred_locations
            row.remote_preference = profile.remote_preference
            row.preferred_roles = profile.preferred_roles
            row.preferred_companies = profile.preferred_companies
            row.salary_expectation_min = profile.salary_expectation_min
            row.salary_expectation_max = profile.salary_expectation_max
            row.salary_currency = profile.salary_currency
            row.updated_at = datetime.now(UTC)
            session.flush()
            return self._to_model(row)

    def set_active(self, profile_id: int) -> CandidateProfile | None:
        with db_session() as session:
            row = session.get(CandidateProfileRow, profile_id)
            if row is None:
                return None
            session.exec(CandidateProfileRow.__table__.update().values(is_active=False))
            row.is_active = True
            row.updated_at = datetime.now(UTC)
            session.flush()
            return self._to_model(row)

    def delete(self, profile_id: int) -> bool:
        with db_session() as session:
            row = session.get(CandidateProfileRow, profile_id)
            if row is None:
                return False
            session.delete(row)
            return True


candidate_service = CandidateService()
