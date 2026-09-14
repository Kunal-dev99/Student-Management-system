"""Twin assembly — reads only, no side effects.

The twin is derived at read time from authoritative services. Optional worker-side
caching (materialised view or a snapshot table) is a Phase 3+ optimisation and stays
invalidatable by domain `updated_at`.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.principal import Principal
from app.ai.types import Evidence
from app.intelligence.ai_bridge import intelligence_narrate
from app.intelligence.twin.schemas import (
    DependencyEdge,
    ModelSignal,
    NarratedState,
    PressurePoint,
    StudentTwinSnapshot,
)


class TwinBuilder:
    def __init__(self, session: AsyncSession, principal: Principal) -> None:
        self.session = session
        self.principal = principal

    async def snapshot(
        self, student_id: uuid.UUID, *, enable_llm: bool = False,
    ) -> StudentTwinSnapshot:
        from app.modules.person.models import Person
        from app.modules.student_record.models import Student

        row = (await self.session.execute(
            select(Student, Person)
            .join(Person, Person.id == Student.person_id)
            .where(Student.id == student_id)
        )).first()
        if row is None:
            raise NotFoundError("Student not found")
        student, person = row

        state: dict = {
            "name": f"{person.given_name} {person.family_name}",
            "student_ref": student.student_ref,
            "status": student.status.value if hasattr(student.status, "value") else str(student.status),
            "study_mode": student.study_mode.value if hasattr(student.study_mode, "value") else None,
            "start_date": student.start_date.isoformat() if student.start_date else None,
            "expected_end_date": (student.expected_end_date.isoformat()
                                    if student.expected_end_date else None),
        }
        today = date.today()
        pressure: list[PressurePoint] = []
        deps: list[DependencyEdge] = []
        blockers: list[str] = []
        signals: list[ModelSignal] = []

        # --- Milestone pressure points -----------------------------------------
        try:
            from app.modules.progression.constants import MilestoneStatus
            from app.modules.progression.models import Milestone, MilestoneDefinition
            rows = (await self.session.execute(
                select(Milestone, MilestoneDefinition)
                .join(MilestoneDefinition, MilestoneDefinition.id == Milestone.milestone_definition_id)
                .where(Milestone.student_id == student_id)
            )).all()
            for m, mdef in rows:
                if m.status not in (MilestoneStatus.not_started, MilestoneStatus.due,
                                     MilestoneStatus.submitted, MilestoneStatus.under_review,
                                     MilestoneStatus.overdue):
                    continue
                if m.status == MilestoneStatus.overdue or (m.due_date and m.due_date < today):
                    pressure.append(PressurePoint(
                        kind="milestone_overdue", label=mdef.name,
                        when=m.due_date, weight=8,
                        evidence={"kind": "milestone", "id": str(m.id)},
                    ))
                elif m.due_date and (m.due_date - today).days <= 30:
                    pressure.append(PressurePoint(
                        kind="milestone_due", label=mdef.name,
                        when=m.due_date, weight=5,
                        evidence={"kind": "milestone", "id": str(m.id)},
                    ))
        except Exception:  # noqa: BLE001
            blockers.append("progression data unavailable")

        # --- Funding pressure points -------------------------------------------
        try:
            from app.modules.funding.constants import FundingStatus
            from app.modules.funding.models import FundingArrangement
            arrangements = (await self.session.execute(
                select(FundingArrangement).where(FundingArrangement.student_id == student_id)
            )).scalars().all()
            active = [a for a in arrangements if a.status == FundingStatus.active]
            if not active:
                pressure.append(PressurePoint(
                    kind="no_active_funding", label="No active funding arrangement",
                    weight=6,
                    evidence={"kind": "funding", "count": 0},
                ))
            for a in active:
                if a.valid_to and (a.valid_to - today).days <= 180:
                    pressure.append(PressurePoint(
                        kind="funding_expiring", label=f"Funding ends {a.valid_to.isoformat()}",
                        when=a.valid_to, weight=7,
                        evidence={"kind": "funding_arrangement", "id": str(a.id)},
                    ))
        except Exception:  # noqa: BLE001
            blockers.append("funding data unavailable")

        # --- Supervision gap ----------------------------------------------------
        try:
            from app.modules.supervision.repository import SupervisionRepository
            from app.modules.supervision.service import SupervisionService
            sup = SupervisionService(SupervisionRepository(self.session))
            compliance = await sup.meeting_compliance(student_id)
            if compliance.get("overdue"):
                pressure.append(PressurePoint(
                    kind="supervision_gap",
                    label=f"Supervision overdue — last on {compliance.get('lastMeetingOn') or 'never'}",
                    weight=6,
                    evidence={"kind": "supervision_meeting", "aggregate": "compliance"},
                ))
                deps.append(DependencyEdge(
                    from_ref={"kind": "student", "id": str(student_id)},
                    to_ref={"kind": "supervisor"},
                    reason="Next agreed actions depend on the next supervision meeting.",
                ))
        except Exception:  # noqa: BLE001
            blockers.append("supervision compliance unavailable")

        # --- Model signals from Pattern Lab production predictions --------------
        try:
            from app.modules.pattern_lab.models import MlModelVersion, MlPrediction
            # Pull the latest prediction per target for this student. `MlPrediction`
            # carries `target_key` directly — no join table needed.
            rows = (await self.session.execute(
                select(MlPrediction, MlModelVersion)
                .join(MlModelVersion, MlModelVersion.id == MlPrediction.model_version_id)
                .where(MlPrediction.student_id == student_id,
                       MlModelVersion.status == "production")
                .order_by(MlPrediction.scored_at.desc())
                .limit(20)
            )).all()
            seen_targets: set[str] = set()
            for pred, ver in rows:
                if pred.target_key in seen_targets:
                    continue
                seen_targets.add(pred.target_key)
                signals.append(ModelSignal(
                    target=pred.target_key,
                    probability=float(pred.probability),
                    model_version_id=ver.id,
                    model_health="healthy",
                ))
        except Exception:  # noqa: BLE001
            pass  # model signals are optional context, not a blocker

        # Sort pressure by weight desc so the caller sees what matters first.
        pressure.sort(key=lambda p: -p.weight)

        narrated: NarratedState | None = None
        if enable_llm:
            narrated = await self._narrate_state(state, pressure, signals)

        return StudentTwinSnapshot(
            student_id=student.id,
            as_of=datetime.now(timezone.utc),
            state=state,
            pressure_points=pressure,
            dependencies=deps,
            model_signals=signals,
            blockers=blockers,
            narrated_state=narrated,
        )

    async def _narrate_state(
        self, state: dict, pressure: list[PressurePoint], signals: list[ModelSignal],
    ) -> NarratedState:
        """Produce a grounded one-paragraph state summary; falls back to a template.

        Every figure the model may quote appears in `evidence.figures` — the top
        pressure point and any model probability. The deterministic fallback splices
        the same figures into a plain sentence so the feature works with LLM off.
        """
        figures: dict[str, str] = {
            "student_ref": state.get("student_ref") or "unknown",
            "status": state.get("status") or "unknown",
            "pressure_count": str(len(pressure)),
        }
        if pressure:
            top = pressure[0]
            figures["top_pressure"] = top.label
            figures["top_pressure_kind"] = top.kind
        else:
            figures["top_pressure"] = "no material pressure"
            figures["top_pressure_kind"] = "none"
        if signals:
            s = signals[0]
            figures["primary_target"] = s.target
            figures["primary_probability"] = f"{s.probability:.2f}"

        fallback = ("Student {student_ref} is {status}; {pressure_count} pressure "
                    "point(s), top: {top_pressure}.")
        evidence = Evidence(
            figures=figures,
            context={
                "pressure_kinds": [p.kind for p in pressure[:5]],
                "study_mode": state.get("study_mode"),
            },
        )
        result = await intelligence_narrate(
            feature="twin",
            evidence=evidence,
            question="Summarise this student's current state in one short paragraph.",
            fallback_template=fallback,
            principal_id=self.principal.user_id,
        )
        return NarratedState(
            body=result.body,
            source=result.provenance.source,
            model=result.provenance.model,
        )
