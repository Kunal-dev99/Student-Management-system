"""Portal write endpoints — the student's own actions on their own record.

Every action here goes through the same principal-scoping the read endpoints use:
`principal.person_id` resolves to the student's own record, and each write verifies the
target entity belongs to that student before proceeding. A student cannot act on
another student's data because the URL doesn't carry an id they can tamper with —
the id in the URL is validated against the resolved student id.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_current_principal
from app.core.errors import NotFoundError, ValidationAppError
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.documents.repository import DocumentRepository
from app.modules.documents.service import DocumentService
from app.modules.student_record.repository import StudentRepository
from app.modules.supervision.models import SupervisionMeeting
from app.modules.supervision.repository import SupervisionRepository
from app.modules.supervision.service import SupervisionService
from app.modules.thesis.service import ThesisService
from app.modules.thesis.repository import ThesisRepository

router = APIRouter(prefix="/portal", tags=["portal"])


async def _resolve_student_id(session: AsyncSession, principal: Principal) -> uuid.UUID:
    """Turn the signed-in principal into the id of the student record they own.

    Refuses with 404 rather than 403 for anyone without a person link — a supervisor
    hitting these endpoints just doesn't have a student record; the answer is honest.
    """
    if principal.person_id is None:
        raise HTTPException(status_code=404, detail="No student record linked to this account")
    student = await StudentRepository(session).get_by_person(principal.person_id)
    if student is None:
        raise HTTPException(status_code=404, detail="No student record linked to this account")
    return student.id


# ---------------------------------------------------------------- confirm meeting

@router.post("/meetings/{meeting_id}/confirm", summary="Confirm a supervision meeting note")
async def confirm_meeting(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    """A student confirms the record of a supervision meeting they attended.

    The confirm is a signed act on the joint supervisory record — the platform stores who
    confirmed it and when. This endpoint refuses if the meeting isn't for the calling
    student.
    """
    student_id = await _resolve_student_id(session, principal)

    meeting = (await session.execute(
        select(SupervisionMeeting).where(SupervisionMeeting.id == meeting_id)
    )).scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting.student_id != student_id:
        # Never a scoped 403 — a student can't be told that another student has a meeting.
        raise HTTPException(status_code=404, detail="Meeting not found")

    try:
        return await SupervisionService(SupervisionRepository(session)).confirm_meeting(meeting_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------- intent to submit

class IntentToSubmitIn(BaseModel):
    """The student's own intent-to-submit signal.

    Title is optional at this point — students often signal intent before their working
    title is locked. The supervision team is expected to confirm the working title later.
    """
    title: str | None = Field(default=None, max_length=300)


@router.post("/thesis/intent-to-submit", summary="Record intent to submit a thesis")
async def declare_intent_to_submit(
    body: IntentToSubmitIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    """Student signals intent to submit. This kicks off the examiner-nomination workflow
    downstream — no admin has to remember to start it."""
    student_id = await _resolve_student_id(session, principal)

    svc = ThesisService(ThesisRepository(session))
    thesis = await svc.declare_intention(student_id, body.title)
    return {
        "status": thesis.status.value,
        "title": thesis.title,
        "intentionAt": thesis.intention_to_submit_at.isoformat()
            if thesis.intention_to_submit_at else None,
    }


# ---------------------------------------------------------------- documents

def _doc_out(d) -> dict:
    """Serialise a document plus its parsed category.

    Categories are stored inside `doc_type` as `student:<category>` for uploads from the
    portal, or `milestone_submission` for files that came in through the milestone submit
    endpoint. We surface both so the /documents page can group them cleanly.
    """
    doc_type = d.doc_type or ""
    if doc_type.startswith("student:"):
        category = doc_type.split(":", 1)[1] or "other"
    elif doc_type == "milestone_submission":
        category = "milestone"
    else:
        category = "other"
    return {
        "id": str(d.id),
        "ownerType": d.owner_type,
        "ownerId": str(d.owner_id),
        "docType": d.doc_type,
        "category": category,
        "filename": d.filename,
        "contentType": d.content_type,
        "sizeBytes": d.size_bytes,
        "scanStatus": d.scan_status,
        "createdAt": d.created_at.isoformat() if d.created_at else None,
    }


@router.get("/documents", summary="List documents on the student's own record")
async def list_own_documents(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> list[dict]:
    """Every document attached to the student's own record — chapter drafts, milestone
    submissions, evidence, correspondence. Scoped to the calling principal; no id in the
    URL. We include documents owned by the student's OWN milestones too, so the /documents
    page can show a unified library rather than splitting by owner.
    """
    from app.modules.progression.models import Milestone

    student_id = await _resolve_student_id(session, principal)
    svc = DocumentService(DocumentRepository(session))

    # Direct portal uploads on the student.
    docs = list(await svc.list_for_owner("student", student_id))

    # Milestone submissions belong to the student too — pull them by their milestones.
    milestone_ids = [
        m.id for m in (await session.execute(
            select(Milestone).where(Milestone.student_id == student_id)
        )).scalars().all()
    ]
    for mid in milestone_ids:
        docs.extend(await svc.list_for_owner("milestone", mid))

    # Newest first.
    docs.sort(key=lambda d: d.created_at or 0, reverse=True)
    return [_doc_out(d) for d in docs]


# Category vocabulary for student uploads — matches the sections on the /documents page.
# Kept as a closed set: if the model or a rogue caller sends anything else we snap to "other"
# so the library never grows an accidental category.
STUDENT_DOC_CATEGORIES = {
    "thesis",
    "milestone",
    "research",
    "training",
    "ethics",
    "meetings",
    "admin",
    "other",
}


def _normalise_category(value: str | None) -> str:
    if not value:
        return "other"
    v = value.strip().lower()
    return v if v in STUDENT_DOC_CATEGORIES else "other"


@router.post("/documents", status_code=201, summary="Upload a document to the student's own record")
async def upload_own_document(
    file: UploadFile = File(...),
    category: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    """Student uploads a document to their own record. The owner is inferred from the
    principal — there is no way to upload against another student.

    `category` places the file in one of the /documents page sections (thesis, milestone,
    research, training, ethics, meetings, admin, other). Anything else snaps to "other".
    """
    student_id = await _resolve_student_id(session, principal)
    data = await file.read()
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    if len(data) == 0:
        raise ValidationAppError("Empty file")
    if len(data) > max_bytes:
        raise ValidationAppError(f"File exceeds {get_settings().max_upload_mb} MB limit")

    cat = _normalise_category(category)
    svc = DocumentService(DocumentRepository(session))
    doc = await svc.create(
        owner_type="student", owner_id=student_id,
        # `doc_type` doubles as the category — `student:<category>` keeps the vocabulary
        # explicit and the tags easy to filter on the read path.
        doc_type=f"student:{cat}",
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        data=data, uploaded_by=principal.user_id,
    )
    return _doc_out(doc)


@router.get("/documents/{doc_id}/download", summary="Download a document from the student's own record")
async def download_own_document(
    doc_id,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> Response:
    """A student can only download documents attached to their own record."""
    import uuid as _uuid

    if not isinstance(doc_id, _uuid.UUID):
        try:
            doc_id = _uuid.UUID(str(doc_id))
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Document not found") from exc

    from app.modules.progression.models import Milestone

    student_id = await _resolve_student_id(session, principal)
    svc = DocumentService(DocumentRepository(session))
    try:
        doc = await svc.get(doc_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc

    # Allowed if it's owned by the student directly, OR by a milestone that belongs to
    # them. Never leak that another student's doc exists — same-404 for out-of-scope.
    owned = doc.owner_type == "student" and doc.owner_id == student_id
    if not owned and doc.owner_type == "milestone":
        milestone = (await session.execute(
            select(Milestone).where(Milestone.id == doc.owner_id)
        )).scalar_one_or_none()
        owned = milestone is not None and milestone.student_id == student_id
    if not owned:
        raise HTTPException(status_code=404, detail="Document not found")

    data = svc.read_bytes(doc)
    # Inline for previewable types (PDF, images, plain text); attachment for everything
    # else. The /documents page previews inline when it can and falls back to download.
    disposition = "inline" if (
        (doc.content_type or "").startswith(("image/", "text/"))
        or doc.content_type == "application/pdf"
    ) else "attachment"
    return Response(
        content=data,
        media_type=doc.content_type,
        headers={"Content-Disposition": f'{disposition}; filename="{doc.filename}"'},
    )


# ---------------------------------------------------------------- milestone submit

@router.post("/milestones/{milestone_id}/submit", status_code=201,
             summary="Attach a file to a milestone and mark it submitted")
async def submit_milestone(
    milestone_id: uuid.UUID,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    """Student uploads a file that IS the milestone submission — a chapter draft, a
    portfolio, whatever the milestone definition asks for. The document lands owned by
    the milestone, and the milestone state advances to `submitted` in one call so the
    supervisor's task inbox picks it up immediately.
    """
    from app.modules.progression.constants import MilestoneStatus
    from app.modules.progression.models import Milestone

    student_id = await _resolve_student_id(session, principal)

    milestone = (await session.execute(
        select(Milestone).where(Milestone.id == milestone_id)
    )).scalar_one_or_none()
    if milestone is None or milestone.student_id != student_id:
        raise HTTPException(status_code=404, detail="Milestone not found")

    data = await file.read()
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    if len(data) == 0:
        raise ValidationAppError("Empty file")
    if len(data) > max_bytes:
        raise ValidationAppError(f"File exceeds {get_settings().max_upload_mb} MB limit")

    svc = DocumentService(DocumentRepository(session))
    doc = await svc.create(
        owner_type="milestone", owner_id=milestone.id,
        doc_type="milestone_submission",
        filename=file.filename or "submission",
        content_type=file.content_type or "application/octet-stream",
        data=data, uploaded_by=principal.user_id,
    )

    # Advance the milestone state — only from "open" states, never regress.
    if milestone.status in {
        MilestoneStatus.not_started,
        MilestoneStatus.due,
        MilestoneStatus.overdue,
    }:
        milestone.status = MilestoneStatus.submitted
    await session.commit()
    await session.refresh(milestone)

    return {
        "document": _doc_out(doc),
        "milestone": {
            "id": str(milestone.id),
            "status": milestone.status.value,
        },
    }


# ---------------------------------------------------------------- messaging

class SendMessageIn(BaseModel):
    """Student sends a message to one of their current supervisors."""
    supervisorPersonId: uuid.UUID
    body: str = Field(min_length=1, max_length=4000)


@router.get("/messages", summary="Message threads with the student's current supervisors")
async def list_message_threads(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> list[dict]:
    """One thread per current supervisor. Each carries the last message preview, unread
    count, supervisor name — enough for the portal to render a list without a second
    round-trip."""
    from app.modules.person.models import Person
    from app.modules.portal.models import PortalMessage
    from app.modules.supervision.repository import SupervisionRepository

    student_id = await _resolve_student_id(session, principal)

    # Current supervisors — one thread per active relationship.
    relationships = await SupervisionRepository(session).active_for_student(student_id)
    if not relationships:
        return []

    supervisor_ids = [r.supervisor_person_id for r in relationships]
    persons = {
        p.id: p for p in (await session.execute(
            select(Person).where(Person.id.in_(supervisor_ids))
        )).scalars().all()
    }

    threads = []
    for r in relationships:
        p = persons.get(r.supervisor_person_id)
        if p is None:
            continue
        messages = (await session.execute(
            select(PortalMessage)
            .where(PortalMessage.student_id == student_id,
                   PortalMessage.supervisor_person_id == r.supervisor_person_id)
            .order_by(PortalMessage.created_at.desc())
        )).scalars().all()
        last = messages[0] if messages else None
        unread = sum(
            1 for m in messages
            if m.author_role == "supervisor" and m.read_at is None
        )
        threads.append({
            "supervisorPersonId": str(r.supervisor_person_id),
            "supervisorName": f"{p.given_name} {p.family_name}",
            "role": r.role,
            "lastMessage": {
                "body": last.body[:120] if last else None,
                "authorRole": last.author_role if last else None,
                "createdAt": last.created_at.isoformat() if last else None,
            } if last else None,
            "unreadCount": unread,
            "totalMessages": len(messages),
        })
    return threads


@router.get("/messages/{supervisor_person_id}", summary="Messages in one thread")
async def list_thread_messages(
    supervisor_person_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> list[dict]:
    from app.modules.portal.models import PortalMessage

    student_id = await _resolve_student_id(session, principal)

    messages = (await session.execute(
        select(PortalMessage)
        .where(PortalMessage.student_id == student_id,
               PortalMessage.supervisor_person_id == supervisor_person_id)
        .order_by(PortalMessage.created_at.asc())
    )).scalars().all()

    # Mark supervisor-authored messages as read now that the student is looking.
    from datetime import datetime, timezone as _tz
    now = datetime.now(_tz.utc)
    for m in messages:
        if m.author_role == "supervisor" and m.read_at is None:
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


@router.post("/messages", status_code=201, summary="Send a message to a current supervisor")
async def send_message(
    body: SendMessageIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    from app.modules.portal.models import PortalMessage
    from app.modules.supervision.repository import SupervisionRepository

    student_id = await _resolve_student_id(session, principal)

    # Guard: recipient must be one of my current supervisors.
    relationships = await SupervisionRepository(session).active_for_student(student_id)
    if not any(r.supervisor_person_id == body.supervisorPersonId for r in relationships):
        raise HTTPException(
            status_code=404,
            detail="Not one of your current supervisors",
        )

    message = PortalMessage(
        student_id=student_id,
        supervisor_person_id=body.supervisorPersonId,
        author_user_id=principal.user_id,
        author_role="student",
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
