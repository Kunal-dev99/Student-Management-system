"""Intervention plan staging.

The planner is the write-half of the closed loop. It:
  1. Accepts an InterventionPlanCreate (from Weekly Review, Case Copilot or manual).
  2. Rejects duplicate drafts via a deterministic idempotency key.
  3. Persists the plan + one action per allow-listed step.
  4. Never executes anything — confirm() is a separate step in the executor.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ValidationAppError
from app.core.principal import Principal
from app.intelligence.ai_bridge import intelligence_classify
from app.intelligence.models_p2 import InterventionAction, InterventionPlan
from app.intelligence.schemas_p2 import ActionType, InterventionPlanCreate

# Signal-kind → keyword rules for the deterministic classify fallback.
_SIGNAL_KEYWORD_RULES: dict[str, list[str]] = {
    "prepare_meeting_brief": ["supervision_gap", "no_meeting", "meeting overdue"],
    "request_funding_review": ["funding_expiring", "no_active_funding", "funding gap"],
    "open_review_evidence_check": ["milestone_overdue", "review", "evidence"],
    "schedule_reassessment": ["milestone_due", "reassess"],
    "create_task": ["follow up", "todo", "action"],
}
_ALLOWED_ACTION_TYPES: list[str] = [
    "create_task", "prepare_meeting_brief", "request_funding_review",
    "open_review_evidence_check", "schedule_reassessment",
]


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class InterventionPlanner:
    def __init__(self, session: AsyncSession, principal: Principal) -> None:
        self.session = session
        self.principal = principal

    async def stage(self, body: InterventionPlanCreate) -> InterventionPlan:
        if not body.actions:
            raise ValidationAppError("An intervention plan needs at least one action.")

        # Idempotency: same case + same signal + same action set = same plan.
        signal_hash = _hash(body.source_signal or {})
        action_hash = _hash([(a.action_type, a.target_ref) for a in body.actions])
        plan_key = f"{body.case_ref}|{signal_hash}|{action_hash}"

        # Only an ACTIVE plan blocks re-staging. A cancelled one must not — otherwise
        # cancel() looks like a dead end: the same idempotency_key lives on forever on
        # the cancelled row, and "cancel it first" in the message below would be a lie.
        existing = (await self.session.execute(
            select(InterventionPlan).where(
                InterventionPlan.idempotency_key == plan_key,
                InterventionPlan.status.in_(("draft", "confirmed")),
            )
        )).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(
                f"Plan already staged for this signal ({existing.status}). "
                "Cancel it first if you want a fresh one."
            )

        plan = InterventionPlan(
            case_ref=body.case_ref,
            student_id=body.student_id,
            rationale=body.rationale,
            source_signal=body.source_signal,
            reassess_at=body.reassess_at,
            status="draft",
            idempotency_key=plan_key,
            created_by_user_id=self.principal.user_id,
        )
        self.session.add(plan)
        await self.session.flush()

        # One action row per allow-listed step. Duplicate action inside a plan is refused
        # by the DB unique constraint (plan_id, idempotency_key).
        for a in body.actions:
            action_key = _hash({
                "case": body.case_ref,
                "type": a.action_type,
                "target": a.target_ref,
                "source": body.source_signal,
            })
            self.session.add(InterventionAction(
                plan_id=plan.id,
                action_type=a.action_type,
                target_ref=a.target_ref,
                owner_ref=a.owner_ref,
                due_at=a.due_at,
                payload=a.payload,
                idempotency_key=action_key,
                status="pending",
            ))
        await self.session.flush()
        return plan

    async def propose_from_signal(
        self, signal_kind: str, signal_detail: str, *, case_ref: str,
        student_id: uuid.UUID | None = None,
    ) -> dict:
        """LLM-assisted suggestion for a single action type + rationale.

        Returns a dict {action_type, rationale, source: "model"|"fallback"} the caller
        can feed straight into `stage()`. Never persists — the human still confirms.
        """
        result = await intelligence_classify(
            feature="intervention_planner",
            text=f"[{signal_kind}] {signal_detail}",
            labels=_ALLOWED_ACTION_TYPES,
            keyword_rules=_SIGNAL_KEYWORD_RULES,
            fallback_label="create_task",
            context=f"Signal kind: {signal_kind}. Case ref: {case_ref}.",
            principal_id=self.principal.user_id,
        )
        return {
            "action_type": result.label,
            "rationale": result.reasoning,
            "source": result.provenance.source,
            "model": result.provenance.model,
            "case_ref": case_ref,
            "student_id": student_id,
            "signal": {"kind": signal_kind, "detail": signal_detail},
        }

    async def cancel(self, plan_id: uuid.UUID, reason: str | None = None) -> InterventionPlan:
        plan = await self.session.get(InterventionPlan, plan_id)
        if plan is None:
            raise ValidationAppError("Plan not found.")
        if plan.status not in ("draft", "confirmed"):
            raise ValidationAppError(f"Plan is already {plan.status}; nothing to cancel.")
        plan.status = "cancelled"
        # Note stored on source_signal for audit.
        plan.source_signal = {**(plan.source_signal or {}), "cancel_reason": reason,
                                "cancelled_at": datetime.now(timezone.utc).isoformat()}
        # Free the idempotency_key for reuse. The column has a hard DB-level unique
        # constraint (not scoped to status), so leaving it untouched would make
        # "cancel it first if you want a fresh one" a lie: stage() would still hit
        # either the app-level duplicate check or, if that's relaxed, a raw
        # IntegrityError on the next attempt to reuse the same key. Replaced outright
        # (rather than suffixed) since case_ref can run up to 120 chars and the
        # original key can already sit close to the column's 200-char limit;
        # plan.id alone is short and guaranteed unique.
        plan.idempotency_key = f"cancelled:{plan.id}"
        await self.session.flush()
        return plan
