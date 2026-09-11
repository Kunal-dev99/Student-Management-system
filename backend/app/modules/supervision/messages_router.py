"""Supervisor-side messaging — the mirror of `portal/writes.py`'s message endpoints.

A supervisor sees one thread per student they currently supervise. The tables and rows
are the same (`portal_message`); only the query axis flips: supervisor_person_id is the
principal, and every action is scoped so a supervisor can never touch messages for a
student they don't currently supervise.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_principal
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.person.models import Person
from app.modules.portal.models import PortalMessage
from app.modules.student_record.models import Student
from app.modules.supervision.repository import SupervisionRepository

router = APIRouter(prefix="/supervision", tags=["supervision-messages"])


def _refuse_without_person(principal: Principal) -> uuid.UUID:
    """Refuse with 404 for principals who aren't linked to a person (which every
    supervisor should be)."""
    if principal.person_id is None:
        raise HTTPException(status_code=404, detail="No supervisor record linked to this account")
    return principal.person_id


class SendSupervisorMessageIn(BaseModel):
    """Supervisor sends a message to one of their current students."""
    studentId: uuid.UUID
    body: str = Field(min_length=1, max_length=4000)


@router.get("/messages", summary="Message threads with the supervisor's current students")
async def list_supervisor_threads(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> list[dict]:
    """One thread per current student. Same shape as the portal endpoint, so a single UI
    can render for either side."""
    person_id = _refuse_without_person(principal)

    relationships = await SupervisionRepository(session).active_for_supervisor(person_id)
    if not relationships:
        return []

    student_ids = [r.student_id for r in relationships]
    # Bulk-load the student rows + their people for name/ref display.
    students = {
        s.id: s for s in (await session.execute(
            select(Student).where(Student.id.in_(student_ids))
        )).scalars().all()
    }
    person_ids = [s.person_id for s in students.values()]
    persons = {
        p.id: p for p in (await session.execute(
            select(Person).where(Person.id.in_(person_ids))
        )).scalars().all()
    }

    threads: list[dict] = []
    for r in relationships:
        student = students.get(r.student_id)
        if student is None:
            continue
        person = persons.get(student.person_id)
        student_name = f"{person.given_name} {person.family_name}" if person else "Unknown"

        messages = (await session.execute(
            select(PortalMessage)
            .where(PortalMessage.student_id == r.student_id,
                   PortalMessage.supervisor_person_id == person_id)
            .order_by(PortalMessage.created_at.desc())
        )).scalars().all()
        last = messages[0] if messages else None
        # From the supervisor's side, unread = messages the student authored that the
        # supervisor hasn't read yet.
        unread = sum(
            1 for m in messages
            if m.author_role == "student" and m.read_at is None
        )
        threads.append({
            "studentId": str(r.student_id),
            "studentName": student_name,
            "studentRef": student.student_ref,
            "role": r.role,
            "lastMessage": {
                "body": last.body[:120] if last else None,
                "authorRole": last.author_role if last else None,
                "createdAt": last.created_at.isoformat() if last else None,
            } if last else None,
            "unreadCount": unread,
            "totalMessages": len(messages),
        })
    # Threads with unread first, then by last-message time descending.
    threads.sort(key=lambda t: (
        t["unreadCount"] == 0,
        -(datetime.fromisoformat(t["lastMessage"]["createdAt"]).timestamp()
          if t["lastMessage"] and t["lastMessage"]["createdAt"] else 0),
    ))
    return threads


@router.get("/messages/{student_id}", summary="Messages in one supervisor-side thread")
async def list_supervisor_thread_messages(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> list[dict]:
    person_id = _refuse_without_person(principal)

    # Refuse cleanly if the student isn't one this supervisor currently supervises.
    relationships = await SupervisionRepository(session).active_for_supervisor(person_id)
    if not any(r.student_id == student_id for r in relationships):
        raise HTTPException(status_code=404, detail="Student not in your caseload")

    messages = (await session.execute(
        select(PortalMessage)
        .where(PortalMessage.student_id == student_id,
               PortalMessage.supervisor_person_id == person_id)
        .order_by(PortalMessage.created_at.asc())
    )).scalars().all()

    # Mark student-authored messages as read now that the supervisor is looking at them.
    now = datetime.now(timezone.utc)
    for m in messages:
        if m.author_role == "student" and m.read_at is None:
            m.read_at = now
    await session.commit()

    return [
        {
            "id": str(m.id),
            "authorRole": m.author_role,
            "body": m.body,
            "createdAt": m.created_at.isoformat() if m.created_at else None,
            "readAt": m.read_at.isoformat() if m.read_at else None,
        }
        for m in messages
    ]


@router.post("/messages", status_code=201, summary="Send a message to a current student")
async def send_supervisor_message(
    body: SendSupervisorMessageIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    person_id = _refuse_without_person(principal)

    # Guard: recipient must be one of my current students.
    relationships = await SupervisionRepository(session).active_for_supervisor(person_id)
    if not any(r.student_id == body.studentId for r in relationships):
        raise HTTPException(status_code=404, detail="Student not in your caseload")

    message = PortalMessage(
        student_id=body.studentId,
        supervisor_person_id=person_id,
        author_user_id=principal.user_id,
        author_role="supervisor",
        body=body.body,
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)

    return {
        "id": str(message.id),
        "authorRole": message.author_role,
        "body": message.body,
        "createdAt": message.created_at.isoformat() if message.created_at else None,
    }
