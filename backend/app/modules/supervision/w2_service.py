"""W2 — services for SupervisorProfile and the assignment-request workflow."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.person.models import Person
from app.modules.student_record.models import ResearchArea, Student
from app.modules.supervision.constants import SupervisorRole
from app.modules.supervision.repository import SupervisionRepository
from app.modules.supervision.service import SupervisionService
from app.modules.supervision.w2_models import (
    AssignmentRequestState,
    SupervisorAssignmentRequest,
    SupervisorAvailability,
    SupervisorProfile,
    SupervisorProfileArea,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- Profile

class SupervisorProfileService:
    """CRUD + the effective-capacity computation used by the assignment gate."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get(self, person_id: uuid.UUID) -> SupervisorProfile | None:
        return (await self.session.execute(
            select(SupervisorProfile).where(SupervisorProfile.person_id == person_id)
        )).scalar_one_or_none()

    async def _areas_for(self, profile_id: uuid.UUID) -> list[uuid.UUID]:
        rows = (await self.session.execute(
            select(SupervisorProfileArea.research_area_id)
            .where(SupervisorProfileArea.supervisor_profile_id == profile_id)
        )).scalars().all()
        return list(rows)

    async def get_or_none(self, person_id: uuid.UUID) -> dict | None:
        row = await self._get(person_id)
        if row is None:
            return None
        return {
            "personId": str(row.person_id),
            "maxStudents": row.max_students,
            "availability": row.availability.value,
            "acceptingNew": row.accepting_new,
            "sabbaticalFrom": row.sabbatical_from.isoformat() if row.sabbatical_from else None,
            "sabbaticalTo": row.sabbatical_to.isoformat() if row.sabbatical_to else None,
            "bio": row.bio,
            "researchAreaIds": [str(a) for a in await self._areas_for(row.id)],
        }

    async def upsert(
        self, person_id: uuid.UUID, *, max_students: int | None = None,
        availability: SupervisorAvailability | None = None, accepting_new: bool | None = None,
        sabbatical_from: date | None = None, sabbatical_to: date | None = None,
        bio: str | None = None, research_area_ids: list[uuid.UUID] | None = None,
    ) -> dict:
        # Existence check — a profile without a real person is nonsense.
        p = (await self.session.execute(
            select(Person).where(Person.id == person_id)
        )).scalar_one_or_none()
        if p is None:
            raise NotFoundError("Person not found")

        row = await self._get(person_id)
        created = row is None
        if created:
            row = SupervisorProfile(person_id=person_id)
            self.session.add(row)
            await self.session.flush()

        if max_students is not None:
            if max_students < 0:
                raise WorkflowError("max_students must be >= 0")
            row.max_students = max_students
        if availability is not None:
            row.availability = availability
        if accepting_new is not None:
            row.accepting_new = accepting_new
        if sabbatical_from is not None:
            row.sabbatical_from = sabbatical_from
        if sabbatical_to is not None:
            row.sabbatical_to = sabbatical_to
        if bio is not None:
            row.bio = bio

        if research_area_ids is not None:
            # Refuse unknown area ids so we don't silently drop what the caller passed.
            found = (await self.session.execute(
                select(ResearchArea.id).where(ResearchArea.id.in_(research_area_ids))
            )).scalars().all()
            missing = set(research_area_ids) - set(found)
            if missing:
                raise WorkflowError(
                    f"Unknown research area id(s): {', '.join(str(m) for m in missing)}"
                )
            # Replace the set. Small enough set that a delete + insert is clearer than a diff.
            existing = (await self.session.execute(
                select(SupervisorProfileArea)
                .where(SupervisorProfileArea.supervisor_profile_id == row.id)
            )).scalars().all()
            for e in existing:
                await self.session.delete(e)
            for aid in research_area_ids:
                self.session.add(SupervisorProfileArea(
                    supervisor_profile_id=row.id, research_area_id=aid,
                ))

        await self.session.commit()
        return await self.get_or_none(person_id)  # type: ignore[return-value]

    async def effective_cap(self, person_id: uuid.UUID) -> int:
        """The capacity ceiling for this supervisor.

        Profile.max_students wins when a profile exists. Otherwise falls back to the institution
        setting ``supervision.max_supervisees`` (the shipped default before W2).
        """
        row = await self._get(person_id)
        if row is not None:
            return row.max_students
        from app.modules.settings.service import setting_value
        return int(await setting_value(self.session, "supervision.max_supervisees"))

    async def is_available(self, person_id: uuid.UUID) -> bool:
        """A supervisor is unavailable if their profile marks them on_leave, not accepting_new,
        or if today falls inside a sabbatical window."""
        row = await self._get(person_id)
        if row is None:
            return True  # no profile = default available (falls back to setting cap)
        if row.availability is SupervisorAvailability.on_leave:
            return False
        if not row.accepting_new:
            return False
        today = date.today()
        if (row.sabbatical_from and row.sabbatical_to
                and row.sabbatical_from <= today <= row.sabbatical_to):
            return False
        return True


# --------------------------------------------------------------------------- Assignment

class SupervisorAssignmentService:
    """Small state machine on top of ``SupervisorAssignmentRequest``.

    States: recommended → requested → academic_review → approved | rejected | withdrawn.
    ``approve`` re-runs the capacity + availability gate at the moment of decision — the
    situation may have changed since the recommendation.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.profiles = SupervisorProfileService(session)

    async def request(
        self, *, student_id: uuid.UUID, supervisor_person_id: uuid.UUID,
        role: SupervisorRole, requested_by_user_id: uuid.UUID | None = None,
        match_score: int | None = None, match_reasons: list[dict] | None = None,
        note: str | None = None,
    ) -> SupervisorAssignmentRequest:
        # Both aggregates must exist.
        if (await self.session.execute(
            select(Student).where(Student.id == student_id)
        )).scalar_one_or_none() is None:
            raise NotFoundError("Student not found")
        if (await self.session.execute(
            select(Person).where(Person.id == supervisor_person_id)
        )).scalar_one_or_none() is None:
            raise NotFoundError("Supervisor person not found")
        row = SupervisorAssignmentRequest(
            student_id=student_id, proposed_supervisor_person_id=supervisor_person_id,
            proposed_role=role, state=AssignmentRequestState.requested,
            match_score=match_score, match_reasons=match_reasons,
            requested_by_user_id=requested_by_user_id, note=note,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def _get(self, request_id: uuid.UUID) -> SupervisorAssignmentRequest:
        row = (await self.session.execute(
            select(SupervisorAssignmentRequest).where(SupervisorAssignmentRequest.id == request_id)
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Assignment request not found")
        return row

    async def review(
        self, request_id: uuid.UUID, *, reviewed_by_user_id: uuid.UUID | None = None,
    ) -> SupervisorAssignmentRequest:
        row = await self._get(request_id)
        if row.state != AssignmentRequestState.requested:
            raise WorkflowError(f"Only a 'requested' assignment can be moved to review "
                                f"(currently {row.state.value})")
        row.state = AssignmentRequestState.academic_review
        row.reviewed_by_user_id = reviewed_by_user_id
        row.reviewed_at = _now()
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def approve(
        self, request_id: uuid.UUID, *, decided_by_user_id: uuid.UUID | None = None,
    ) -> tuple[SupervisorAssignmentRequest, Any]:
        row = await self._get(request_id)
        if row.state not in (AssignmentRequestState.academic_review, AssignmentRequestState.requested):
            raise WorkflowError(f"Only 'requested' or 'academic_review' can be approved "
                                f"(currently {row.state.value})")

        # Re-check availability + capacity right now — the world may have moved since request.
        if not await self.profiles.is_available(row.proposed_supervisor_person_id):
            raise WorkflowError("Supervisor is no longer available (on leave / not accepting new).")
        cap = await self.profiles.effective_cap(row.proposed_supervisor_person_id)
        # Delegate the actual insert to the existing SupervisionService — one code path for the
        # relationship itself, so the capacity guard, duplicate-check and audit all still fire.
        sup_service = SupervisionService(SupervisionRepository(self.session))
        rel = await sup_service.assign(
            row.student_id, row.proposed_supervisor_person_id, row.proposed_role,
            max_supervisees=cap,
        )
        row.state = AssignmentRequestState.approved
        row.decided_by_user_id = decided_by_user_id
        row.decided_at = _now()
        await self.session.commit()
        await self.session.refresh(row)
        return row, rel

    async def reject(
        self, request_id: uuid.UUID, *, reason: str,
        decided_by_user_id: uuid.UUID | None = None,
    ) -> SupervisorAssignmentRequest:
        if not (reason or "").strip():
            raise WorkflowError("A rejection reason is required.")
        row = await self._get(request_id)
        if row.state in (AssignmentRequestState.approved, AssignmentRequestState.rejected,
                         AssignmentRequestState.withdrawn):
            raise WorkflowError(f"Assignment already {row.state.value}")
        row.state = AssignmentRequestState.rejected
        row.rejection_reason = reason.strip()
        row.decided_by_user_id = decided_by_user_id
        row.decided_at = _now()
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def withdraw(self, request_id: uuid.UUID) -> SupervisorAssignmentRequest:
        row = await self._get(request_id)
        if row.state in (AssignmentRequestState.approved, AssignmentRequestState.rejected,
                         AssignmentRequestState.withdrawn):
            raise WorkflowError(f"Assignment already {row.state.value}")
        row.state = AssignmentRequestState.withdrawn
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_for_student(self, student_id: uuid.UUID) -> list[SupervisorAssignmentRequest]:
        return list((await self.session.execute(
            select(SupervisorAssignmentRequest)
            .where(SupervisorAssignmentRequest.student_id == student_id)
            .order_by(SupervisorAssignmentRequest.created_at.desc())
        )).scalars().all())

    async def list_by_state(self, state: AssignmentRequestState | None = None) -> list[SupervisorAssignmentRequest]:
        stmt = select(SupervisorAssignmentRequest).order_by(SupervisorAssignmentRequest.created_at.desc())
        if state is not None:
            stmt = stmt.where(SupervisorAssignmentRequest.state == state)
        return list((await self.session.execute(stmt)).scalars().all())
