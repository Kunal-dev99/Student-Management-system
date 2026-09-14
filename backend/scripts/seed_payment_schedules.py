"""Bulk stipend payment schedules for the ICR demo cohort.

The bulk student seed (`seed_bulk_students.py`) creates a `FundingArrangement` per student
but never generates its instalment schedule — so the Payment Status page had almost nothing
to show. This script closes that gap using the REAL service/workflow code paths (not hand-
crafted rows), so every instalment's status and Finance trail is exactly what the running
app would have produced:

  - `FundingService.generate_schedule()` — builds the instalments for an arrangement.
  - `FundingService.approve_payment()` — approves a scheduled instalment (now emits an
    outbound "sent to Finance" notification, closing a gap this session also fixed).
  - `IntegrationService.handle_inbound()` with a synthetic finance/payment.confirmed or
    finance/payment.rejected event — exactly the code path a real Finance webhook takes,
    which both applies the domain change (mark_paid / held) AND writes the correctly
    aggregate-tagged inbound integration_log row.
  - `IntegrationService.dispatch_pending()` — flushes the outbound outbox events created
    above into real integration_log rows, exactly as the worker would.

Status mix, by due date relative to today:
  - overdue instalments: ~80% paid, ~12% held (Finance rejected), ~8% left approved
    (the "approved but overdue" bucket the Funding Integrity Finance lens looks for)
  - due within the next 60 days: approved (sent to Finance, awaiting payment)
  - further out: left scheduled

Idempotent — skips any arrangement that already has payment rows. Safe to re-run.

    python -m scripts.seed_payment_schedules
"""
from __future__ import annotations

import asyncio
import random
from datetime import date, timedelta

from sqlalchemy import select

from app.core.database import SessionFactory
from app.db import registry as _registry  # noqa: F401
from app.modules.funding.constants import PaymentFrequency, PaymentStatus
from app.modules.funding.models import FundingArrangement, StipendPayment
from app.modules.funding.repository import FundingRepository
from app.modules.funding.service import FundingService
from app.modules.integration.repository import IntegrationRepository
from app.modules.integration.service import IntegrationService

random.seed(9100)

TODAY = date.today()
MAX_ARRANGEMENTS = 220
FREQUENCIES = [PaymentFrequency.monthly, PaymentFrequency.quarterly]


async def main() -> None:
    async with SessionFactory() as session:
        funding_svc = FundingService(FundingRepository(session))
        integration_svc = IntegrationService(IntegrationRepository(session))

        arrangements = (await session.execute(
            select(FundingArrangement).where(FundingArrangement.stipend_amount.is_not(None))
        )).scalars().all()

        # Idempotency: skip any arrangement that already has payment rows.
        existing_arrangement_ids = set((await session.execute(
            select(StipendPayment.arrangement_id).distinct()
        )).scalars().all())
        todo = [a for a in arrangements if a.id not in existing_arrangement_ids][:MAX_ARRANGEMENTS]

        if not todo:
            print("  = every funded arrangement already has a payment schedule - skipped")
            return

        print(f"  scheduling payments for {len(todo)} arrangements...")
        counts = {"paid": 0, "held": 0, "approved": 0, "scheduled": 0}
        processed = 0

        for arrangement in todo:
            frequency = random.choice(FREQUENCIES)
            payments = await FundingService(FundingRepository(session)).generate_schedule(
                arrangement.id, frequency=frequency,
            )
            # generate_schedule() commits internally — re-fetch the real ORM rows to act on.
            rows = await FundingRepository(session).payments_for_arrangement(arrangement.id)

            for p in rows:
                if p.due_date >= TODAY + timedelta(days=60):
                    continue  # stays scheduled
                if p.due_date >= TODAY:
                    await funding_svc.approve_payment(p.id)
                    counts["approved"] += 1
                    continue

                # Overdue: needs to have gone through approval before Finance can act on it.
                await funding_svc.approve_payment(p.id)
                roll = random.random()
                if roll < 0.80:
                    paid_on = (p.due_date + timedelta(days=random.randint(0, 10))).isoformat()
                    await integration_svc.handle_inbound(
                        system="finance", source_id=f"seed-{p.id}-confirmed",
                        event_type="payment.confirmed",
                        payload={
                            "paymentId": str(p.id),
                            "financeReference": f"FIN-{random.randint(100000, 999999)}",
                            "paidOn": paid_on,
                        },
                    )
                    counts["paid"] += 1
                elif roll < 0.92:
                    await integration_svc.handle_inbound(
                        system="finance", source_id=f"seed-{p.id}-rejected",
                        event_type="payment.rejected",
                        payload={"paymentId": str(p.id), "reason": "Cost centre closed for this period"},
                    )
                    counts["held"] += 1
                else:
                    counts["approved"] += 1  # left approved-but-overdue, on purpose

            processed += 1
            if processed % 25 == 0:
                await integration_svc.dispatch_pending()
                print(f"  ... {processed} arrangements scheduled")

        await integration_svc.dispatch_pending()
        for a in todo:
            for p in await FundingRepository(session).payments_for_arrangement(a.id):
                if p.status == PaymentStatus.scheduled:
                    counts["scheduled"] += 1
        print(f"Payment schedules complete: {processed} arrangements — "
              f"paid {counts['paid']}, held {counts['held']}, approved {counts['approved']}, "
              f"scheduled ~{counts['scheduled']}.")


if __name__ == "__main__":
    asyncio.run(main())
