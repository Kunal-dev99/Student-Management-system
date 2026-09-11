"""Seed a small cohort of applications across the admissions actionable stages.

Idempotent: uses a distinctive email suffix so re-runs skip already-seeded rows.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import SessionFactory
# Import the registry so every model's ForeignKey targets are resolvable at flush time.
from app.db import registry as _registry  # noqa: F401
from app.modules.admissions.constants import OfferStatus
from app.modules.admissions.models import Offer
from app.modules.person.models import Person
from app.modules.recruitment.constants import (
    ApplicationRoute,
    CandidateStage,
    OpportunityStatus,
)
from app.modules.recruitment.models import Application, ResearchOpportunity


SEED_TAG = "@admissions-demo.local"

# One row per person we want visible on the admissions screen.
COHORT = [
    ("Marcus",    "Bell",     CandidateStage.under_assessment),
    ("Priya",     "Nair",     CandidateStage.shortlisted),
    ("Elena",     "Ford",     CandidateStage.interview),
    ("Yusuf",     "Ahmed",    CandidateStage.selected),
    ("Sofia",     "Rossi",    CandidateStage.offer_made),
    ("Kenji",     "Tanaka",   CandidateStage.offer_made),
    ("Aisha",     "Khan",     CandidateStage.offer_accepted),
]


async def main() -> None:
    async with SessionFactory() as s:
        # Pick a live opportunity to attach the applications to.
        opp = (await s.execute(
            select(ResearchOpportunity)
            .where(ResearchOpportunity.status.in_([
                OpportunityStatus.open, OpportunityStatus.recruiting,
            ]))
            .limit(1)
        )).scalar_one_or_none()
        if opp is None:
            # No live opportunity — flip the first draft to open so the seed can attach.
            opp = (await s.execute(
                select(ResearchOpportunity).order_by(ResearchOpportunity.created_at).limit(1)
            )).scalar_one()
            opp.status = OpportunityStatus.open
            await s.flush()
            print(f"Flipped '{opp.title}' to open for the seed.")

        created = 0
        skipped = 0
        for given, family, stage in COHORT:
            email = f"{given.lower()}.{family.lower()}{SEED_TAG}"
            existing = (await s.execute(select(Person).where(Person.email == email))).scalar_one_or_none()
            if existing:
                skipped += 1
                continue

            person = Person(given_name=given, family_name=family, email=email)
            s.add(person); await s.flush()

            app = Application(
                person_id=person.id,
                route=ApplicationRoute.opportunity_led,
                research_opportunity_id=opp.id,
                current_stage=stage,
                submitted_at=datetime.now(timezone.utc),
                fee_status="home",
            )
            s.add(app); await s.flush()

            if stage in (CandidateStage.offer_made, CandidateStage.offer_accepted):
                offer = Offer(
                    application_id=app.id,
                    status=OfferStatus.issued if stage == CandidateStage.offer_made
                           else OfferStatus.accepted,
                    conditions={"references": "pending",
                                "fees": "confirmed",
                                "visa": "not_required"},
                    issued_at=datetime.now(timezone.utc),
                    responded_at=(datetime.now(timezone.utc)
                                  if stage == CandidateStage.offer_accepted else None),
                )
                s.add(offer)

            created += 1

        await s.commit()
        print(f"Seeded {created} applications across admissions stages "
              f"(skipped {skipped} already-present).")
        print(f"Attached to opportunity: {opp.title} ({opp.id})")


if __name__ == "__main__":
    asyncio.run(main())
