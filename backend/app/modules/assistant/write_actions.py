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
