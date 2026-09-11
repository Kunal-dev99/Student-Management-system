"""CB-B — Write-action registry the assistant confirms then executes.

Each write action is:
- **stageable**: build a `Pending` from a router decision, with a human-readable diff for the
  confirm card.
- **executable**: given the staged args, call the same service methods the manual UI uses. No
  new mutation code lives here; every action is a thin adapter over an existing service.

Row-scoping is enforced at the underlying service, so an assistant action can never widen a
user's authority — the request is the user's request, just routed differently.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal
from app.modules.fuzzy.intents import Intent
from app.modules.fuzzy.router import RouteDecision


@dataclass
class StagePlan:
    action: str
    target: dict            # what will be acted on (label + id)
    args: dict              # what will be passed to the executor
    diff: dict              # before/after preview for the confirm card


class WriteRegistry:
    def __init__(self) -> None:
        self._staged: dict[str, Callable[[AsyncSession, Principal, RouteDecision], Awaitable[StagePlan | None]]] = {}
        self._exec: dict[str, Callable[[AsyncSession, Principal, dict], Awaitable[dict]]] = {}

    def register(self, action: str, *, stage, execute) -> None:
        self._staged[action] = stage
        self._exec[action] = execute

    async def stage(self, action: str, session: AsyncSession, principal: Principal,
                    decision: RouteDecision) -> StagePlan | None:
        fn = self._staged.get(action)
        if fn is None:
            return None
        return await fn(session, principal, decision)

    async def execute(self, action: str, session: AsyncSession, principal: Principal,
                      args: dict) -> dict:
        fn = self._exec[action]
        return await fn(session, principal, args)


registry = WriteRegistry()


# ---------------- approve_payment ----------------

async def _stage_approve_payment(session, principal, decision) -> StagePlan | None:
    """Approve the caller's next scheduled payment for the named student.

    The assistant is a shortcut, not a search tool — so it targets ONE row (the next scheduled
    instalment for the resolved student) rather than making the user pick. If the row cannot be
    identified unambiguously, stage returns None and the router falls back to clarify.
    """
    from app.modules.funding.constants import PaymentStatus
    from app.modules.funding.models import StipendPayment

    if not decision.entities:
        return None
    student_id = uuid.UUID(decision.entities[0].id)
    row = (await session.execute(
        select(StipendPayment)
        .where(StipendPayment.student_id == student_id,
               StipendPayment.status == PaymentStatus.scheduled)
        .order_by(StipendPayment.due_date.asc())
        .limit(1)
    )).scalar_one_or_none()
    if row is None:
        return None
    return StagePlan(
        action="approve_payment",
        target={"kind": "stipend_payment", "id": str(row.id),
                "label": f"Next scheduled payment for {decision.entities[0].name}"},
        args={"paymentId": str(row.id)},
        diff={"before": {"status": "scheduled"}, "after": {"status": "approved"},
              "amount": str(row.amount), "currency": row.currency,
              "dueDate": row.due_date.isoformat() if row.due_date else None},
    )


async def _execute_approve_payment(session, principal, args) -> dict:
    from app.modules.funding.repository import FundingRepository
    from app.modules.funding.service import FundingService
    payment_id = uuid.UUID(args["paymentId"])
    return await FundingService(FundingRepository(session)).approve_payment(payment_id)


registry.register("approve_payment", stage=_stage_approve_payment, execute=_execute_approve_payment)


# ---------------- hold_payment ----------------

async def _stage_hold_payment(session, principal, decision) -> StagePlan | None:
    from app.modules.funding.constants import PaymentStatus
    from app.modules.funding.models import StipendPayment
    if not decision.entities:
        return None
    student_id = uuid.UUID(decision.entities[0].id)
    # Target the next non-cancelled, non-paid instalment.
    row = (await session.execute(
        select(StipendPayment)
        .where(StipendPayment.student_id == student_id,
               StipendPayment.status.in_([PaymentStatus.scheduled, PaymentStatus.approved]))
        .order_by(StipendPayment.due_date.asc())
        .limit(1)
    )).scalar_one_or_none()
    if row is None:
        return None
    before = row.status.value if hasattr(row.status, "value") else str(row.status)
    return StagePlan(
        action="hold_payment",
        target={"kind": "stipend_payment", "id": str(row.id),
                "label": f"Next open payment for {decision.entities[0].name}"},
        args={"paymentId": str(row.id), "note": "Held via assistant"},
        diff={"before": {"status": before}, "after": {"status": "held"},
              "amount": str(row.amount), "currency": row.currency,
              "dueDate": row.due_date.isoformat() if row.due_date else None},
    )


async def _execute_hold_payment(session, principal, args) -> dict:
    from app.modules.funding.constants import PaymentStatus
    from app.modules.funding.repository import FundingRepository
    from app.modules.funding.service import FundingService
    payment_id = uuid.UUID(args["paymentId"])
    return await FundingService(FundingRepository(session)).set_payment_status(
        payment_id, PaymentStatus.held, note=args.get("note"),
    )


registry.register("hold_payment", stage=_stage_hold_payment, execute=_execute_hold_payment)


# ---------------- submit_signoff ----------------

async def _stage_submit_signoff(session, principal, decision) -> StagePlan | None:
    """Sign off the resolved student's statutory record. Uses whatever the existing service
    exposes — kept generic so the exact signoff surface can evolve without editing the assistant.
    """
    if not decision.entities:
        return None
    return StagePlan(
        action="submit_signoff",
        target={"kind": "student", "id": decision.entities[0].id,
                "label": f"Statutory sign-off for {decision.entities[0].name}"},
        args={"studentId": decision.entities[0].id},
        diff={"before": {"signoff": "pending"}, "after": {"signoff": "signed"}},
    )


async def _execute_submit_signoff(session, principal, args) -> dict:
    """Adapter over the statutory sign-off service. Kept behind a try/except so that if the
    signoff API changes shape, the assistant fails honestly rather than silently doing nothing."""
    try:
        from app.modules.statutory.service import StatutorySignOffService
        student_id = uuid.UUID(args["studentId"])
        return await StatutorySignOffService(session).submit_for_student(student_id, principal)
    except Exception as exc:                  # noqa: BLE001 — assistant must surface any failure
        return {"error": f"sign-off submission failed: {type(exc).__name__}: {exc}"}


registry.register("submit_signoff", stage=_stage_submit_signoff, execute=_execute_submit_signoff)


# ---------------- complete_task ----------------

async def _stage_complete_task(session, principal, decision) -> StagePlan | None:
    """Complete the caller's OLDEST open task.

    The assistant is a shortcut, so it targets the next task in the queue rather than
    making the user pick — if there are multiple, the user can ask again after the first.
    """
    from app.modules.workflow.repository import WorkflowRepository
    tasks = await WorkflowRepository(session).tasks_for(
        principal.user_id, principal.roles, only_open=True,
    )
    if not tasks:
        return None
    t = tasks[0]
    return StagePlan(
        action="complete_task",
        target={"kind": "task", "id": str(t.id),
                "label": f'Complete task "{t.title}"'},
        args={"taskId": str(t.id)},
        diff={"before": {"status": t.status.value if hasattr(t.status, "value") else str(t.status)},
              "after": {"status": "done"},
              "title": t.title},
    )


async def _execute_complete_task(session, principal, args) -> dict:
    from app.modules.workflow.repository import WorkflowRepository
    from app.modules.workflow.service import WorkflowService
    task = await WorkflowService(WorkflowRepository(session)).complete_task(
        uuid.UUID(args["taskId"]), principal,
    )
    return {"taskId": str(task.id), "title": task.title,
            "status": task.status.value if hasattr(task.status, "value") else str(task.status)}


registry.register("complete_task", stage=_stage_complete_task, execute=_execute_complete_task)


# ---------------- mark_notifications_read ----------------

async def _stage_mark_notifications_read(session, principal, decision) -> StagePlan | None:
    """Mark every unread notification in the caller's inbox as read."""
    from app.modules.workflow.constants import NotificationStatus
    from app.modules.workflow.repository import WorkflowRepository
    notifs = await WorkflowRepository(session).notifications_for(principal.user_id)
    unread = [n for n in notifs if n.status != NotificationStatus.read]
    if not unread:
        return None
    return StagePlan(
        action="mark_notifications_read",
        target={"kind": "notifications", "id": str(principal.user_id),
                "label": f"Mark {len(unread)} notification(s) as read"},
        args={"count": len(unread)},
        diff={"before": {"unread": len(unread)}, "after": {"unread": 0}},
    )


async def _execute_mark_notifications_read(session, principal, args) -> dict:
    from app.modules.workflow.constants import NotificationStatus
    from app.modules.workflow.repository import WorkflowRepository
    notifs = await WorkflowRepository(session).notifications_for(principal.user_id)
    marked = 0
    for n in notifs:
        if n.status != NotificationStatus.read:
            n.status = NotificationStatus.read
            marked += 1
    await session.commit()
    return {"marked": marked}


registry.register(
    "mark_notifications_read",
    stage=_stage_mark_notifications_read, execute=_execute_mark_notifications_read,
)


# ---------------- transition_opportunity ----------------

async def _stage_transition_opportunity(session, principal, decision) -> StagePlan | None:
    """Advance an opportunity to its next reasonable status.

    Draft → Approved → Open. If the resolved token set names a status word ("approve",
    "open", "publish"), that word decides; otherwise we pick the natural next state.
    """
    from app.modules.recruitment.constants import OPPORTUNITY_TRANSITIONS, OpportunityStatus
    from app.modules.recruitment.models import ResearchOpportunity

    # Find opportunity by name mention in tokens — fallback to first draft.
    opp = None
    tokens = " ".join(decision.tokens)
    all_opps = (await session.execute(
        select(ResearchOpportunity).order_by(ResearchOpportunity.created_at.desc()).limit(50)
    )).scalars().all()
    for o in all_opps:
        if o.title and o.title.lower() in tokens.lower():
            opp = o
            break
    if opp is None:
        # Fall back to the newest draft in scope.
        opp = next((o for o in all_opps if o.status == OpportunityStatus.draft), None)
    if opp is None:
        return None

    # Choose target state — prefer next allowed forward step, unless a status word is present.
    allowed = OPPORTUNITY_TRANSITIONS.get(opp.status, set())
    preferred_by_word = {
        "approve": OpportunityStatus.approved,
        "open": OpportunityStatus.open,
        "publish": OpportunityStatus.open,
        "recruit": OpportunityStatus.recruiting,
        "recruiting": OpportunityStatus.recruiting,
        "pause": OpportunityStatus.paused,
        "close": OpportunityStatus.closed,
        "fill": OpportunityStatus.filled,
        "filled": OpportunityStatus.filled,
    }
    target = None
    for word, state in preferred_by_word.items():
        if word in tokens.lower() and state in allowed:
            target = state
            break
    if target is None:
        forward_order = [OpportunityStatus.approved, OpportunityStatus.open,
                         OpportunityStatus.recruiting, OpportunityStatus.filled,
                         OpportunityStatus.closed]
        target = next((s for s in forward_order if s in allowed), None)
    if target is None:
        return None

    return StagePlan(
        action="transition_opportunity",
        target={"kind": "opportunity", "id": str(opp.id),
                "label": f'Move "{opp.title}" to {target.value}'},
        args={"opportunityId": str(opp.id), "toStatus": target.value},
        diff={"before": {"status": opp.status.value}, "after": {"status": target.value},
              "title": opp.title},
    )


async def _execute_transition_opportunity(session, principal, args) -> dict:
    from app.modules.recruitment.constants import OpportunityStatus
    from app.modules.recruitment.repository import RecruitmentRepository
    from app.modules.recruitment.service import RecruitmentService
    svc = RecruitmentService(RecruitmentRepository(session))
    opp = await svc.transition_opportunity(
        uuid.UUID(args["opportunityId"]), OpportunityStatus(args["toStatus"]),
    )
    return {"opportunityId": str(opp.id), "title": opp.title,
            "status": opp.status.value if hasattr(opp.status, "value") else str(opp.status)}


registry.register(
    "transition_opportunity",
    stage=_stage_transition_opportunity, execute=_execute_transition_opportunity,
)


# ---------------- add_supervision_meeting_note ----------------

def _extract_note_text(query: str, student_name: str | None = None) -> str:
    """Trim command words + the student's name off so the note reads like the user meant.

    'add a note for alice: discussed timeline' → 'discussed timeline'
    'log a supervision meeting with Marcus Bell'   → '' (no explicit note)
    'log a note for Marcus Bell about the timeline' → 'the timeline'
    """
    import re
    q = query.strip()
    # If there's a colon, everything after it is the note.
    if ":" in q:
        return q.split(":", 1)[1].strip() or ""
    q = re.sub(
        r"^(add|log|record|note|write)\s+(a\s+)?(supervision\s+)?"
        r"(meeting\s+)?(note|meeting)?\s*(for|with|about|on)?\s*",
        "", q, flags=re.IGNORECASE,
    )
    # Strip the student's name from the tail — if what's left IS just the name
    # (or empty), there's no genuine note to record.
    if student_name:
        pattern = re.escape(student_name)
        q = re.sub(pattern, "", q, flags=re.IGNORECASE).strip(" ,.-")
    return q.strip()


async def _stage_add_supervision_meeting(session, principal, decision) -> StagePlan | None:
    from datetime import date as _date

    if not decision.entities:
        return None
    student = decision.entities[0]
    note = _extract_note_text(decision.query, student.name)
    diff = {"before": {"meeting": "—"},
            "after": {"meeting": _date.today().isoformat()},
            "student": student.name}
    if note:
        diff["notes"] = note[:120] + ("…" if len(note) > 120 else "")
    return StagePlan(
        action="add_supervision_meeting",
        target={"kind": "student", "id": student.id,
                "label": f"Log supervision meeting with {student.name}"},
        args={
            "studentId": student.id,
            "metOn": _date.today().isoformat(),
            "notes": note or None,
        },
        diff=diff,
    )


async def _execute_add_supervision_meeting(session, principal, args) -> dict:
    from datetime import date as _date
    from app.modules.supervision.constants import MeetingFormat
    from app.modules.supervision.repository import SupervisionRepository
    from app.modules.supervision.service import SupervisionService
    svc = SupervisionService(SupervisionRepository(session))
    return await svc.record_meeting(
        uuid.UUID(args["studentId"]),
        supervisor_person_id=principal.person_id,
        met_on=_date.fromisoformat(args["metOn"]),
        format=MeetingFormat.online,
        duration_minutes=None,
        notes=args.get("notes"),
        actions=None,
        next_meeting_on=None,
        recorded_by_user_id=principal.user_id,
    )


registry.register(
    "add_supervision_meeting",
    stage=_stage_add_supervision_meeting, execute=_execute_add_supervision_meeting,
)


# ---------------- assign_supervisor ----------------

async def _stage_assign_supervisor(session, principal, decision) -> StagePlan | None:
    """Assign the caller as primary supervisor to the resolved student.

    Simple, safe default: the caller (must have a person record) becomes primary. A future
    version can also parse "assign Elena Ford to Alice" by matching a second person name.
    """
    if not decision.entities:
        return None
    if principal.person_id is None:
        return None
    student = decision.entities[0]
    # Decide role by verb in query.
    tokens = " ".join(decision.tokens).lower()
    role_str = "co_supervisor" if any(w in tokens for w in ("co", "co-supervisor", "second")) \
        else "primary"
    return StagePlan(
        action="assign_supervisor",
        target={"kind": "student", "id": student.id,
                "label": f"Assign you as {role_str.replace('_', ' ')} of {student.name}"},
        args={"studentId": student.id,
              "supervisorPersonId": str(principal.person_id),
              "role": role_str},
        diff={"before": {"role": "—"},
              "after": {"role": role_str},
              "student": student.name},
    )


async def _execute_assign_supervisor(session, principal, args) -> dict:
    from app.modules.supervision.constants import SupervisorRole
    from app.modules.supervision.repository import SupervisionRepository
    from app.modules.supervision.service import SupervisionService
    svc = SupervisionService(SupervisionRepository(session))
    rel = await svc.assign(
        student_id=uuid.UUID(args["studentId"]),
        supervisor_person_id=uuid.UUID(args["supervisorPersonId"]),
        role=SupervisorRole(args["role"]),
    )
    return {
        "relationshipId": str(rel.id),
        "studentId": str(rel.student_id),
        "supervisorPersonId": str(rel.supervisor_person_id),
        "role": rel.role.value if hasattr(rel.role, "value") else str(rel.role),
        "status": rel.status.value if hasattr(rel.status, "value") else str(rel.status),
    }


registry.register(
    "assign_supervisor",
    stage=_stage_assign_supervisor, execute=_execute_assign_supervisor,
)
