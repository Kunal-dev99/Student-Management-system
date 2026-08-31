"""W4 — Finance lens on the funding-integrity screen.

The existing lens on `/funding-integrity` answers *which students* have a broken funding chain.
Finance staff need a different cut of the same data: *the cashflow*. This service produces the
Finance-lens read model — cashflow totals for a window, plus three actionable lists (held,
overdue-approved, paid-without-Finance-reference).

Row-scoped like every other funding read: an `allowed_ids` filter narrows to the caller's
supervisory/administrative scope.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.funding.constants import PaymentStatus
from app.modules.funding.models import FundingArrangement, StipendPayment
from app.modules.person.models import Person
from app.modules.student_record.models import Student


def _d(x: Decimal | None) -> str:
    return str(x if x is not None else Decimal("0"))


class FinanceLensService:
    """Aggregates stipend-payment state for a Finance-facing view."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def snapshot(
        self,
        *,
        allowed_ids: list[uuid.UUID] | None = None,
        window_from: date | None = None,
        window_to: date | None = None,
        limit: int = 100,
    ) -> dict:
        today = date.today()
        w_from = window_from or today.replace(day=1)
        # Default upper bound = end of the current calendar quarter (approx: +3 months).
        w_to = window_to or (
            date(today.year + (today.month + 3 - 1) // 12,
                 ((today.month + 3 - 1) % 12) + 1, 1)
        )

        stmt = (
            select(StipendPayment, FundingArrangement, Student, Person)
            .join(FundingArrangement, FundingArrangement.id == StipendPayment.arrangement_id)
            .join(Student, Student.id == StipendPayment.student_id)
            .join(Person, Person.id == Student.person_id)
        )
        if allowed_ids is not None:
            stmt = stmt.where(StipendPayment.student_id.in_(allowed_ids))
        rows = (await self.session.execute(stmt)).all()

        totals: dict[str, Decimal] = {
            "scheduled": Decimal("0"), "approved": Decimal("0"), "paid": Decimal("0"),
            "held": Decimal("0"), "cancelled": Decimal("0"),
        }
        by_type: dict[str, dict[str, Decimal | int]] = {}
        held, overdue, unreconciled = [], [], []
        in_window_count = 0

        for pay, arr, stu, per in rows:
            status_val = pay.status.value if hasattr(pay.status, "value") else str(pay.status)
            in_window = (pay.due_date is not None and w_from <= pay.due_date <= w_to)
            if in_window:
                totals[status_val] = totals.get(status_val, Decimal("0")) + (pay.amount or Decimal("0"))
                in_window_count += 1
                ftype = arr.funding_type.value if hasattr(arr.funding_type, "value") else str(arr.funding_type)
                bucket = by_type.setdefault(ftype, {"paid": Decimal("0"), "outstanding": Decimal("0"), "count": 0})
                bucket["count"] = int(bucket["count"]) + 1
                if pay.status == PaymentStatus.paid:
                    bucket["paid"] += pay.amount or Decimal("0")
                elif pay.status in (PaymentStatus.scheduled, PaymentStatus.approved, PaymentStatus.held):
                    bucket["outstanding"] += pay.amount or Decimal("0")

            # Held — any date, needs triage regardless of window.
            if pay.status == PaymentStatus.held:
                held.append({
                    "paymentId": str(pay.id), "studentId": str(stu.id),
                    "studentRef": stu.student_ref,
                    "personName": f"{per.given_name} {per.family_name}",
                    "amount": _d(pay.amount), "currency": pay.currency,
                    "dueDate": pay.due_date.isoformat() if pay.due_date else None,
                    "note": pay.note, "link": f"/students/{stu.id}",
                })
            # Overdue approved — past due, not paid.
            if pay.status == PaymentStatus.approved and pay.due_date and pay.due_date < today:
                overdue.append({
                    "paymentId": str(pay.id), "studentId": str(stu.id),
                    "studentRef": stu.student_ref,
                    "personName": f"{per.given_name} {per.family_name}",
                    "amount": _d(pay.amount), "currency": pay.currency,
                    "dueDate": pay.due_date.isoformat(),
                    "daysOverdue": (today - pay.due_date).days,
                    "link": f"/students/{stu.id}",
                })
            # Paid but no Finance reference — reconciliation drift.
            if pay.status == PaymentStatus.paid and not (pay.finance_reference or "").strip():
                unreconciled.append({
                    "paymentId": str(pay.id), "studentId": str(stu.id),
                    "studentRef": stu.student_ref,
                    "personName": f"{per.given_name} {per.family_name}",
                    "amount": _d(pay.amount), "currency": pay.currency,
                    "paidOn": pay.paid_on.isoformat() if pay.paid_on else None,
                    "link": f"/students/{stu.id}",
                })

        # Deterministic order + cap for the UI.
        held.sort(key=lambda x: (x["dueDate"] or "9999", x["personName"]))
        overdue.sort(key=lambda x: (-x["daysOverdue"], x["personName"]))
        unreconciled.sort(key=lambda x: (x["paidOn"] or "9999", x["personName"]))

        return {
            "window": {"from": w_from.isoformat(), "to": w_to.isoformat()},
            "paymentsInWindow": in_window_count,
            "totals": {k: _d(v) for k, v in totals.items()},
            "byFundingType": [
                {"fundingType": k, "paid": _d(v["paid"]),
                 "outstanding": _d(v["outstanding"]), "count": int(v["count"])}
                for k, v in sorted(by_type.items())
            ],
            "held": held[:limit],
            "overdueApproved": overdue[:limit],
            "paidWithoutFinanceReference": unreconciled[:limit],
            "counts": {
                "held": len(held),
                "overdueApproved": len(overdue),
                "paidWithoutFinanceReference": len(unreconciled),
            },
        }
