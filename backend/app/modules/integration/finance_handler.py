"""W3 — Inbound handler for Finance.

Two event types from the Finance system:

- ``payment.confirmed``  Finance settled the stipend we approved. Map to
                         ``FundingService.mark_paid(paidOn, financeReference)``.
- ``payment.rejected``   Finance refused to pay. Map to ``set_payment_status(HELD, note=reason)``
                         so the row is visible on the funding-integrity screen for triage.

Payload shape (kept small on purpose — the platform is not Finance's system of record):

    {
      "paymentId": "<uuid>",         # our platform's stipend_payment.id (preferred)
      "financeReference": "FIN-...", # or Finance's own id, resolved via a lookup
      "paidOn":       "2026-08-31",  # for payment.confirmed
      "reason":       "...",         # for payment.rejected
    }

At least one of ``paymentId`` / ``financeReference`` is required. When both are present,
``paymentId`` wins.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.funding.constants import PaymentStatus
from app.modules.funding.models import StipendPayment
from app.modules.funding.repository import FundingRepository
from app.modules.funding.service import FundingService


async def _resolve_payment(session: AsyncSession, payload: dict) -> StipendPayment:
    """Locate the StipendPayment row named by the payload.

    Raises ValueError with a diagnostic message when the payload can't identify a row —
    the caller converts that into ``logged_with_error`` on the integration log.
    """
    pid = payload.get("paymentId")
    if pid:
        try:
            u = uuid.UUID(str(pid))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"paymentId is not a valid UUID: {pid!r}") from exc
        row = (await session.execute(
            select(StipendPayment).where(StipendPayment.id == u)
        )).scalar_one_or_none()
        if row is None:
            raise ValueError(f"No stipend_payment with id {u}")
        return row

    ref = payload.get("financeReference")
    if ref:
        row = (await session.execute(
            select(StipendPayment).where(StipendPayment.finance_reference == str(ref))
        )).scalar_one_or_none()
        if row is None:
            raise ValueError(f"No stipend_payment with finance_reference {ref!r}")
        return row

    raise ValueError("Payload must carry paymentId or financeReference")


async def apply_finance_event(session: AsyncSession, event_type: str, payload: dict) -> dict:
    """Dispatch a finance/* inbound event. Returns a dict for the integration log."""
    event = (event_type or "").lower()

    if event == "payment.confirmed":
        row = await _resolve_payment(session, payload)
        # Idempotency: an already-paid row should NOT explode when Finance re-sends.
        if row.status == PaymentStatus.paid:
            return {"handler": "finance_payment", "action": "already_paid",
                    "paymentId": str(row.id)}
        if row.status == PaymentStatus.cancelled:
            raise ValueError(
                f"Payment {row.id} is cancelled — cannot mark paid without reactivating first"
            )

        paid_on_raw = payload.get("paidOn")
        paid_on: date | None
        if paid_on_raw:
            try:
                paid_on = date.fromisoformat(str(paid_on_raw))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"paidOn is not a valid ISO date: {paid_on_raw!r}") from exc
        else:
            paid_on = date.today()

        finance_ref = payload.get("financeReference") or row.finance_reference
        result = await FundingService(FundingRepository(session)).mark_paid(
            row.id, paid_on=paid_on, finance_reference=finance_ref,
        )
        return {"handler": "finance_payment", "action": "marked_paid",
                "paymentId": str(row.id), "financeReference": finance_ref,
                "paidOn": result.get("paidOn")}

    if event == "payment.rejected":
        row = await _resolve_payment(session, payload)
        reason = str(payload.get("reason") or "").strip() or "Finance rejected (no reason given)"
        if row.status == PaymentStatus.paid:
            raise ValueError(
                f"Payment {row.id} is already paid — a rejection after settlement needs "
                "a Finance reversal, not this event"
            )
        # Move to HELD so the funding-integrity screen surfaces it for triage. Reason on the
        # payment.note field for the audit trail.
        result = await FundingService(FundingRepository(session)).set_payment_status(
            row.id, PaymentStatus.held, note=f"Finance rejected: {reason}",
        )
        return {"handler": "finance_payment", "action": "held",
                "paymentId": str(row.id), "reason": reason,
                "status": result.get("status")}

    raise ValueError(f"Unknown finance event type: {event_type!r}")
