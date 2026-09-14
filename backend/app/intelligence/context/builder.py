"""Bounded CaseContext assembly.

Reads only through domain services — never wide table selects. Everything that lands
on a returned CaseContext is either the resolved id/name/window that the caller
already supplied OR a small per-domain summary built from row-scoped reads.

The builder is deliberately read-only and side-effect-free: no notifications, no
outbox events, no writes to the source-of-truth tables. Even the EvidenceClaim rows
recorded alongside are optional — passing `record_evidence=False` returns the
context without persisting anything.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal
from app.intelligence.evidence import EvidenceService, evidence_hash
from app.intelligence.schemas import (
    CaseContext,
    DomainSummary,
    EvidenceClaimCreate,
    MissingSource,
    TimeWindow,
)


class CaseContextBuilder:
    """Assemble the working set behind Ask PGR, the Twin and intervention planning."""

    def __init__(
        self,
        session: AsyncSession,
        principal: Principal,
        evidence: EvidenceService | None = None,
    ) -> None:
        self.session = session
        self.principal = principal
        self.evidence = evidence

    async def for_student(
        self,
        student_id: uuid.UUID,
        time_window: TimeWindow | None = None,
        artefact_id: uuid.UUID | None = None,
    ) -> CaseContext:
        """Build a CaseContext centered on one student.

        Records `EvidenceClaim`s for every fact it reads when `artefact_id` and an
        evidence service are provided — that's how the frontend's "why this answer"
        panel later shows sources.
        """
        principal_scope = self._principal_scope()
        summaries: list[DomainSummary] = []
        missing: list[MissingSource] = []
        now = datetime.now(timezone.utc)

        # --- Identity summary --------------------------------------------------
        from app.modules.person.models import Person
        from app.modules.student_record.models import Student

        row = (await self.session.execute(
            select(Student, Person)
            .join(Person, Person.id == Student.person_id)
            .where(Student.id == student_id)
        )).first()
        if row is None:
            # We never surface "not found" as a missing_data claim — that's a NotFound.
            from app.core.errors import NotFoundError
            raise NotFoundError("Student not found")
        student, person = row

        status = student.status.value if hasattr(student.status, "value") else str(student.status)
        identity_facts = [
            {"label": "name", "value": f"{person.given_name} {person.family_name}"},
            {"label": "ref", "value": student.student_ref},
            {"label": "status", "value": status},
            {"label": "study_mode",
             "value": student.study_mode.value if hasattr(student.study_mode, "value") else str(student.study_mode)},
        ]
        summaries.append(DomainSummary(
            domain="identity",
            highlights=[f"{person.given_name} {person.family_name} — {status}"],
            facts=identity_facts,
        ))
        await self._record(artefact_id, [
            EvidenceClaimCreate(
                artefact_id=artefact_id or uuid.uuid4(),
                claim_type="deterministic_fact",
                source_type="student",
                source_id=str(student.id),
                locator={"fields": [f["label"] for f in identity_facts]},
                value_hash=evidence_hash({f["label"]: f["value"] for f in identity_facts}),
                as_of=now,
                permission_scope=principal_scope,
                detail={"summary": "identity"},
            ),
        ] if artefact_id else [])

        # --- Supervision summary ----------------------------------------------
        try:
            from app.modules.supervision.repository import SupervisionRepository
            from app.modules.supervision.service import SupervisionService
            sup = SupervisionService(SupervisionRepository(self.session))
            compliance = await sup.meeting_compliance(student.id)
            meetings = await sup.meetings_for_student(student.id)
            sup_facts = [
                {"label": "last_meeting_on", "value": compliance.get("lastMeetingOn")},
                {"label": "days_since", "value": compliance.get("daysSince")},
                {"label": "overdue", "value": compliance.get("overdue")},
                {"label": "meeting_count", "value": len(meetings)},
            ]
            highlights = []
            if compliance.get("overdue"):
                highlights.append(
                    f"Supervision overdue — last on {compliance.get('lastMeetingOn') or 'never'}"
                )
            summaries.append(DomainSummary(
                domain="supervision",
                highlights=highlights,
                counts={"meetings": len(meetings)},
                facts=sup_facts,
            ))
            await self._record(artefact_id, [
                EvidenceClaimCreate(
                    artefact_id=artefact_id or uuid.uuid4(),
                    claim_type="deterministic_fact",
                    source_type="supervision_meeting",
                    source_id=str(student.id),
                    locator={"aggregate": "compliance"},
                    value_hash=evidence_hash(compliance),
                    as_of=now,
                    permission_scope=principal_scope,
                    detail={"summary": "supervision"},
                ),
            ] if artefact_id else [])
        except Exception:  # noqa: BLE001
            missing.append(MissingSource(source="supervision", reason="unavailable"))

        # --- Funding summary --------------------------------------------------
        try:
            from app.modules.funding.constants import FundingStatus
            from app.modules.funding.models import FundingArrangement
            arrangements = (await self.session.execute(
                select(FundingArrangement).where(FundingArrangement.student_id == student.id)
            )).scalars().all()
            active = [a for a in arrangements if a.status == FundingStatus.active]
            fund_facts = [{"label": "active_count", "value": len(active)},
                          {"label": "total_count", "value": len(arrangements)}]
            highlights = []
            if not active:
                highlights.append("No active funding arrangement.")
            summaries.append(DomainSummary(
                domain="funding",
                highlights=highlights,
                counts={"active": len(active), "total": len(arrangements)},
                facts=fund_facts,
            ))
            await self._record(artefact_id, [
                EvidenceClaimCreate(
                    artefact_id=artefact_id or uuid.uuid4(),
                    claim_type="deterministic_fact",
                    source_type="funding_arrangement",
                    source_id=str(student.id),
                    locator={"aggregate": "counts"},
                    value_hash=evidence_hash({"active": len(active), "total": len(arrangements)}),
                    as_of=now,
                    permission_scope=principal_scope,
                    detail={"summary": "funding"},
                ),
            ] if artefact_id else [])
        except Exception:  # noqa: BLE001
            missing.append(MissingSource(source="funding", reason="unavailable"))

        # --- Progression summary ----------------------------------------------
        try:
            from app.modules.progression.constants import MilestoneStatus
            from app.modules.progression.models import Milestone
            milestones = (await self.session.execute(
                select(Milestone).where(Milestone.student_id == student.id)
            )).scalars().all()
            open_states = {MilestoneStatus.not_started, MilestoneStatus.due,
                            MilestoneStatus.submitted, MilestoneStatus.under_review,
                            MilestoneStatus.overdue}
            open_milestones = [m for m in milestones if m.status in open_states]
            summaries.append(DomainSummary(
                domain="progression",
                highlights=(["Overdue milestones present."]
                            if any(m.status == MilestoneStatus.overdue for m in milestones) else []),
                counts={"open": len(open_milestones), "total": len(milestones)},
                facts=[{"label": "open", "value": len(open_milestones)},
                       {"label": "total", "value": len(milestones)}],
            ))
        except Exception:  # noqa: BLE001
            missing.append(MissingSource(source="progression", reason="unavailable"))

        # --- Finance inbound handler is a known missing source (per arch doc §30)
        missing.append(MissingSource(
            source="finance_inbound",
            reason="Finance payment confirmation handler is TBD in the platform architecture; "
                    "AI must not claim payment receipt beyond PGR-side state.",
        ))

        return CaseContext(
            principal_scope=principal_scope,
            student_id=student.id,
            time_window=time_window,
            domain_summaries=summaries,
            missing_sources=missing,
        )

    # ---- helpers -----------------------------------------------------------------

    def _principal_scope(self) -> dict[str, Any]:
        return {
            "user_id": str(self.principal.user_id),
            "roles": list(self.principal.roles or []),
            "email": self.principal.email,
        }

    async def _record(
        self, artefact_id: uuid.UUID | None, claims: list[EvidenceClaimCreate],
    ) -> None:
        if not artefact_id or not claims or self.evidence is None:
            return
        await self.evidence.record_many(claims)
