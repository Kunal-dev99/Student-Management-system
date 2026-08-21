"""Supervision business rules (arch §8.7). History-preserving assignments."""
from __future__ import annotations

import uuid
from datetime import date

from app.core.errors import ConflictError, NotFoundError
from app.modules.person.repository import PersonRepository
from app.modules.person.service import PersonService
from app.modules.student_record.repository import StudentRepository
from app.modules.supervision.constants import SupervisionStatus, SupervisorRole
from app.modules.supervision.models import SupervisorRelationship
from app.modules.supervision.repository import SupervisionRepository


class SupervisionService:
    def __init__(self, repo: SupervisionRepository) -> None:
        self.repo = repo
        self.session = repo.session

    def _person_service(self) -> PersonService:
        return PersonService(PersonRepository(self.session))

    async def _person_name(self, person_id: uuid.UUID) -> str:
        p = await self._person_service().get_person(person_id)
        return f"{p.given_name} {p.family_name}"

    async def supervisors_for_student(self, student_id: uuid.UUID) -> list[dict]:
        rels = await self.repo.list_for_student(student_id)
        out = []
        for r in rels:
            out.append({
                "id": r.id,
                "supervisorPersonId": r.supervisor_person_id,
                "supervisorName": await self._person_name(r.supervisor_person_id),
                "role": r.role,
                "status": r.status,
                "validFrom": r.valid_from,
                "validTo": r.valid_to,
            })
        return out

    async def assign(
        self, student_id: uuid.UUID, supervisor_person_id: uuid.UUID, role: SupervisorRole
    ) -> SupervisorRelationship:
        # Both the student and the supervising person must exist (service boundary).
        student = await StudentRepository(self.session).get(student_id)
        if student is None:
            raise NotFoundError("Student not found")
        await self._person_service().get_person(supervisor_person_id)

        # No duplicate active relationship for the same supervisor on the same student.
        for r in await self.repo.list_for_student(student_id):
            if r.supervisor_person_id == supervisor_person_id and r.valid_to is None:
                raise ConflictError("This supervisor is already active for the student")

        rel = SupervisorRelationship(
            student_id=student_id, supervisor_person_id=supervisor_person_id,
            role=role, status=SupervisionStatus.active, valid_from=date.today(), valid_to=None,
        )
        self.repo.add(rel)
        await self.session.commit()
        await self.session.refresh(rel)
        return rel

    async def end(self, rel_id: uuid.UUID) -> SupervisorRelationship:
        rel = await self.repo.get(rel_id)
        if rel is None:
            raise NotFoundError("Supervisor relationship not found")
        if rel.valid_to is None:
            rel.valid_to = date.today()
            rel.status = SupervisionStatus.ended
            await self.session.commit()
            await self.session.refresh(rel)
        return rel

    async def caseload(self, person_id: uuid.UUID) -> list[dict]:
        rels = await self.repo.active_for_supervisor(person_id)
        student_repo = StudentRepository(self.session)
        out = []
        for r in rels:
            student = await student_repo.get(r.student_id)
            if student is None:
                continue
            out.append({
                "relationshipId": r.id,
                "studentId": student.id,
                "studentRef": student.student_ref,
                "personName": await self._person_name(student.person_id),
                "role": r.role,
            })
        return out

    async def supervised_student_ids(self, person_id: uuid.UUID) -> list[uuid.UUID]:
        """For row-scoping: the students this supervisor may currently see (arch §12.3)."""
        return await self.repo.active_student_ids_for_supervisor(person_id)
