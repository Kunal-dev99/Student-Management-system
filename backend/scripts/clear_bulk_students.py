"""Remove the old test-format bulk seed (student_ref LIKE 'BULK-%') before reseeding
with the real system-format version.

One-shot cleanup — safe to run even if nothing matches (prints and exits). Deletes,
per matching student: documents (by owner_type/owner_id), milestones, funding
arrangements, supervisor relationships, research projects, thesis, completion,
award, the student row itself, and the student's person_relationship + person
rows (only when that person has no other student row, so shared PI/co-supervisor
people are left untouched).

    python -m scripts.clear_bulk_students
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select, delete

from app.core.database import SessionFactory
from app.core.storage import get_object_store
from app.db import registry as _registry  # noqa: F401
from app.modules.completion.models import Award, Completion
from app.modules.documents.models import Document
from app.modules.funding.models import FundingArrangement
from app.modules.person.models import Person, PersonRelationship
from app.modules.progression.models import Milestone
from app.modules.student_record.models import ResearchProject, Student
from app.modules.supervision.models import SupervisorRelationship
from app.modules.thesis.models import Thesis

OLD_REF_PREFIX = "BULK-"


async def main() -> None:
    store = get_object_store()
    async with SessionFactory() as s:
        students = (await s.execute(
            select(Student).where(Student.student_ref.like(f"{OLD_REF_PREFIX}%"))
        )).scalars().all()

        if not students:
            print("  = no BULK-* students found - nothing to clean up")
            return

        print(f"  found {len(students)} BULK-* students - removing...")
        deleted_docs = 0
        deleted_persons = 0

        for student in students:
            docs = (await s.execute(
                select(Document).where(Document.owner_type == "student", Document.owner_id == student.id)
            )).scalars().all()
            for d in docs:
                try:
                    store.delete(d.storage_key)
                except Exception:
                    pass
                await s.delete(d)
                deleted_docs += 1

            await s.execute(delete(Milestone).where(Milestone.student_id == student.id))
            await s.execute(delete(FundingArrangement).where(FundingArrangement.student_id == student.id))
            await s.execute(delete(SupervisorRelationship).where(SupervisorRelationship.student_id == student.id))
            await s.execute(delete(ResearchProject).where(ResearchProject.student_id == student.id))
            await s.execute(delete(Thesis).where(Thesis.student_id == student.id))
            await s.execute(delete(Completion).where(Completion.student_id == student.id))
            await s.execute(delete(Award).where(Award.student_id == student.id))

            person_id = student.person_id
            await s.delete(student)
            await s.flush()

            other_student = (await s.execute(
                select(Student).where(Student.person_id == person_id)
            )).scalars().first()
            if other_student is None:
                await s.execute(delete(PersonRelationship).where(PersonRelationship.person_id == person_id))
                person = await s.get(Person, person_id)
                if person is not None:
                    await s.delete(person)
                    deleted_persons += 1

        await s.commit()
        print(f"  removed {len(students)} students, {deleted_docs} documents, "
              f"{deleted_persons} person records.")


if __name__ == "__main__":
    asyncio.run(main())
