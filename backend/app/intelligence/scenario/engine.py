"""Scenario preview — side-effect-free calculation of what a proposed change would do.

Absolute rules (arch §10):
  - No notifications, tasks, outbox events, audit rows, external calls.
  - Deterministic rule diff and model sensitivity are separate outputs.
  - Assumptions are recorded explicitly on every result.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.intelligence.ai_bridge import intelligence_classify
from app.intelligence.scenario.schemas import (
    DeterministicDiff,
    ModelSensitivity,
    QualitativeSensitivity,
    ScenarioRequest,
    ScenarioResult,
)

_DIRECTION_LABELS = ["likely_increase", "likely_decrease", "no_clear_change", "uncertain"]
_DIRECTION_KEYWORDS: dict[str, list[str]] = {
    "likely_decrease": ["extend", "more time", "covers expected end", "additional weeks"],
    "likely_increase": ["gap", "does not cover", "shortfall", "overdue"],
}


class ScenarioEngine:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def preview(self, req: ScenarioRequest) -> ScenarioResult:
        from app.modules.student_record.models import Student

        student = await self.session.get(Student, req.student_id)
        if student is None:
            raise NotFoundError("Student not found")

        diff = await self._deterministic(student, req)
        sensitivity = (await self._sensitivity(student, req)
                        if req.include_sensitivity else [])
        # The quantitative pipeline is a stub today (see `_sensitivity`) — until it's
        # wired, fall back to an LLM qualitative judgment for any target this student
        # already has a live production score on, rather than showing nothing.
        qualitative: list[QualitativeSensitivity] = []
        if req.include_sensitivity and not sensitivity:
            qualitative = await self._qualitative_sensitivity(student, req, diff)
        return ScenarioResult(
            student_id=student.id,
            request=req,
            deterministic_diff=diff,
            model_sensitivity=sensitivity,
            qualitative_sensitivity=qualitative,
            missing_data=[],
            computed_at=datetime.now(timezone.utc),
        )

    async def _deterministic(self, student, req: ScenarioRequest) -> DeterministicDiff:
        expected_before = student.expected_end_date
        expected_after = expected_before
        assumptions: list[str] = []
        milestones_shifted: list[dict] = []

        if req.change == "suspend_for_weeks":
            weeks = int(req.params.get("weeks", 0))
            if weeks <= 0:
                raise ValidationAppError("`weeks` must be a positive integer.")
            if expected_before:
                expected_after = expected_before + timedelta(weeks=weeks)
            assumptions.append(
                f"All undecided milestones with a due date are shifted by {weeks} weeks."
            )
            milestones_shifted = await self._shift_open_milestones(student.id,
                                                                     timedelta(weeks=weeks))

        elif req.change == "extend_expected_end_by_months":
            months = int(req.params.get("months", 0))
            if months <= 0:
                raise ValidationAppError("`months` must be a positive integer.")
            days = months * 30  # simple, assumption noted
            if expected_before:
                expected_after = expected_before + timedelta(days=days)
            assumptions.append(f"One month treated as 30 days for date arithmetic.")

        elif req.change == "change_study_mode":
            new_mode = req.params.get("mode")
            if new_mode not in ("full_time", "part_time"):
                raise ValidationAppError("`mode` must be full_time or part_time.")
            if student.study_mode and str(student.study_mode).endswith("full_time") and new_mode == "part_time":
                # PGR conventions treat 1 FT year ≈ 2 PT years for date extension.
                if expected_before:
                    remaining = (expected_before - date.today()).days
                    expected_after = expected_before + timedelta(days=max(remaining, 0))
                assumptions.append(
                    "Full-time → part-time doubles the remaining months to expected end."
                )
            else:
                assumptions.append("Mode change does not shift the expected end in this direction.")

        elif req.change == "shift_next_milestone_by_days":
            days = int(req.params.get("days", 0))
            milestones_shifted = await self._shift_next_milestone(student.id, timedelta(days=days))
            assumptions.append(
                "Only the earliest open, undecided milestone is shifted; downstream milestones untouched."
            )

        else:
            raise ValidationAppError(f"Unknown change type: {req.change}")

        funding_before = await self._funding_coverage(student.id, expected_before)
        funding_after = await self._funding_coverage(student.id, expected_after)

        return DeterministicDiff(
            expected_end_before=expected_before,
            expected_end_after=expected_after,
            milestones_shifted=milestones_shifted,
            funding_coverage_before=funding_before,
            funding_coverage_after=funding_after,
            assumptions=assumptions,
        )

    async def _shift_open_milestones(self, student_id: uuid.UUID,
                                       delta: timedelta) -> list[dict]:
        from app.modules.progression.constants import MilestoneStatus
        from app.modules.progression.models import Milestone, MilestoneDefinition
        rows = (await self.session.execute(
            select(Milestone, MilestoneDefinition)
            .join(MilestoneDefinition, MilestoneDefinition.id == Milestone.milestone_definition_id)
            .where(Milestone.student_id == student_id,
                   Milestone.status.in_([MilestoneStatus.not_started, MilestoneStatus.due,
                                          MilestoneStatus.submitted, MilestoneStatus.under_review]),
                   Milestone.due_date.is_not(None))
        )).all()
        return [
            {
                "milestone": mdef.name,
                "before": m.due_date.isoformat(),
                "after": (m.due_date + delta).isoformat(),
            }
            for m, mdef in rows
        ]

    async def _shift_next_milestone(self, student_id: uuid.UUID,
                                      delta: timedelta) -> list[dict]:
        from app.modules.progression.constants import MilestoneStatus
        from app.modules.progression.models import Milestone, MilestoneDefinition
        rows = (await self.session.execute(
            select(Milestone, MilestoneDefinition)
            .join(MilestoneDefinition, MilestoneDefinition.id == Milestone.milestone_definition_id)
            .where(Milestone.student_id == student_id,
                   Milestone.status.in_([MilestoneStatus.not_started, MilestoneStatus.due]),
                   Milestone.due_date.is_not(None))
            .order_by(Milestone.due_date.asc())
            .limit(1)
        )).all()
        return [
            {"milestone": mdef.name,
             "before": m.due_date.isoformat(),
             "after": (m.due_date + delta).isoformat()}
            for m, mdef in rows
        ]

    async def _funding_coverage(self, student_id: uuid.UUID,
                                  target_end: date | None) -> dict:
        from app.modules.funding.constants import FundingStatus
        from app.modules.funding.models import FundingArrangement
        arrangements = (await self.session.execute(
            select(FundingArrangement).where(FundingArrangement.student_id == student_id)
        )).scalars().all()
        active = [a for a in arrangements if a.status == FundingStatus.active]
        latest_end = max((a.valid_to for a in active if a.valid_to is not None),
                          default=None)
        return {
            "active_count": len(active),
            "latest_end": latest_end.isoformat() if latest_end else None,
            "covers_expected_end": (target_end is not None and latest_end is not None
                                     and latest_end >= target_end),
        }

    async def _sensitivity(self, student, req: ScenarioRequest) -> list[ModelSensitivity]:
        """Placeholder: full sensitivity uses Pattern Lab's exact production pipeline.

        Phase 3 lays the interface; concrete integration ships when we wire the
        SensitivityRunner adapter to `MlModelVersion.artifact`. Until then this returns
        an empty list so the endpoint contract stays honest (no fabricated numbers).
        """
        return []

    async def _scored_targets(self, student_id: uuid.UUID) -> list[tuple[str, float]]:
        """Every production-model target this student currently has a live score on.

        Mirrors the query TwinBuilder uses for `model_signals` — kept independent
        here since the engine has no principal/row-scoping context to share a builder
        instance with.
        """
        from app.modules.pattern_lab.models import MlModelVersion, MlPrediction
        rows = (await self.session.execute(
            select(MlPrediction, MlModelVersion)
            .join(MlModelVersion, MlModelVersion.id == MlPrediction.model_version_id)
            .where(MlPrediction.student_id == student_id,
                   MlModelVersion.status == "production")
            .order_by(MlPrediction.scored_at.desc())
            .limit(20)
        )).all()
        seen: dict[str, float] = {}
        for pred, _ver in rows:
            seen.setdefault(pred.target_key, float(pred.probability))
        return list(seen.items())

    async def _qualitative_sensitivity(
        self, student, req: ScenarioRequest, diff: DeterministicDiff,
    ) -> list[QualitativeSensitivity]:
        """LLM judgment of how the scenario likely nudges each live target.

        Grounded strictly in the deterministic diff already computed — the model
        never sees or invents new facts, it only judges direction from the same
        numbers the reader can see in the "Rule impact" card above it.
        """
        targets = await self._scored_targets(student.id)
        if not targets:
            return []

        context_lines = [
            f"Change requested: {req.change} with params {req.params}",
            f"Expected end: {diff.expected_end_before} -> {diff.expected_end_after}",
            f"Milestones shifted: {len(diff.milestones_shifted)}",
            f"Funding coverage before: {diff.funding_coverage_before}",
            f"Funding coverage after: {diff.funding_coverage_after}",
        ]
        context = "\n".join(context_lines)

        results: list[QualitativeSensitivity] = []
        for target_key, baseline in targets:
            classified = await intelligence_classify(
                feature="scenario_qualitative_sensitivity",
                text=(f"Target: {target_key} (currently scored at {baseline:.0%}).\n\n"
                      f"Deterministic effect of the proposed change:\n{context}"),
                labels=_DIRECTION_LABELS,
                keyword_rules=_DIRECTION_KEYWORDS,
                fallback_label="uncertain",
                context=(
                    "Judge only the DIRECTION this target's risk probability would "
                    "plausibly move given the deterministic effect above — never a "
                    "number. This is a qualitative judgment, not a re-run of the "
                    "trained model."
                ),
            )
            results.append(QualitativeSensitivity(
                target=target_key,
                direction=classified.label,  # type: ignore[arg-type]
                rationale=classified.reasoning,
                baseline_probability=baseline,
                engine=classified.provenance.source,
                model=classified.provenance.model,
            ))
        return results
