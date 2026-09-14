"""Policy Compiler — controlled policy-to-configuration proposal.

Arch §19: the LLM does not emit arbitrary Python/SQL/rule expressions. Only allow-listed
settings and configuration targets can be proposed. Unknown clauses map to "manual
implementation required" — the operator sees the gap explicitly.

Phase 6 ships the allow-list + a deterministic clause matcher. LLM-driven mapping can
plug in later behind the same schema.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.intelligence.ai_bridge import intelligence_read
from app.intelligence.models_p6 import PolicyProposal, PolicyVersion

# Valid dispositions FROM each current status. `review()` previously applied any
# disposition to a proposal in any status — an already-published (potentially
# already-applied) proposal could be silently flipped to "rejected" afterward, or
# a rejected one "published", with zero record of the change ever conflicting.
# published/rejected are terminal: once governance has settled the question, it
# doesn't reopen without staging a fresh proposal.
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft":     {"reviewed", "approved", "rejected"},
    "reviewed":  {"approved", "rejected"},
    "approved":  {"published", "rejected"},
    "rejected":  set(),
    "published": set(),
}


class _LlmClause(BaseModel):
    setting_key: str = Field(description="Allow-listed setting key or a short "
                                          "descriptive slug if unknown.")
    proposed_value: int | None = Field(default=None,
                                        description="Numeric value stated in the clause.")
    matched_span: str = Field(description="Short quote of the clause, ≤ 200 chars.")


# Allow-listed institution settings the compiler is permitted to propose changes to.
# Anything outside this map becomes a "manual" candidate.
ALLOW_LISTED_SETTINGS: dict[str, dict[str, Any]] = {
    "supervision.expected_meeting_interval_days": {"type": "int", "min": 7, "max": 365},
    "supervision.max_supervisees":                 {"type": "int", "min": 1, "max": 20},
    "funding.min_gap_days":                        {"type": "int", "min": 0, "max": 365},
    "progression.annual_review_window_months":     {"type": "int", "min": 6, "max": 24},
}


# Clause pattern → (setting_key, extractor)
#
# The gap between keyword and number uses `[^.]*?` — NOT `.*?` — deliberately. `.*?`
# is non-greedy but still crosses sentence boundaries: on a real multi-clause policy
# text like "...funding gap...is 45 days. Clause 6.3: ...8 active supervisees", the
# max_supervisees pattern would walk right past the full stop and capture 45 (the
# funding-gap number) as the supervisee cap instead of the real value, 8. Restricting
# the wildcard to "not a period" confines every match to one sentence.
CLAUSE_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(
        r"annual\s+review[^.]*?(\d{1,2})\s+months", re.IGNORECASE),
     "progression.annual_review_window_months", "months"),
    (re.compile(
        r"expected[^.]*?meeting[^.]*?(\d{1,3})\s+days", re.IGNORECASE),
     "supervision.expected_meeting_interval_days", "days"),
    (re.compile(
        r"(?:maximum|no\s+more\s+than)[^.]*?(\d{1,2})[^.]*?supervisees", re.IGNORECASE),
     "supervision.max_supervisees", "count"),
    (re.compile(
        r"funding[^.]*?gap[^.]*?(\d{1,3})\s+days", re.IGNORECASE),
     "funding.min_gap_days", "days"),
]


class PolicyCompiler:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def propose(self, policy_version_id: uuid.UUID, policy_text: str,
                       *, enable_llm: bool = False) -> PolicyProposal:
        version = await self.session.get(PolicyVersion, policy_version_id)
        if version is None:
            raise NotFoundError("Policy version not found.")

        rule_candidates: list[dict[str, Any]] = []
        manual_items: list[dict[str, Any]] = []

        # Deterministic clause matcher.
        for pattern, setting_key, kind in CLAUSE_PATTERNS:
            for m in pattern.finditer(policy_text):
                proposed_value = int(m.group(1))
                spec = ALLOW_LISTED_SETTINGS.get(setting_key)
                if spec is None:
                    manual_items.append({
                        "setting_key": setting_key,
                        "reason": "not in allow-list — manual implementation required",
                        "matched_span": m.group(0),
                    })
                    continue
                if not (spec["min"] <= proposed_value <= spec["max"]):
                    manual_items.append({
                        "setting_key": setting_key,
                        "reason": (f"proposed value {proposed_value} outside allow-list bounds "
                                   f"[{spec['min']}, {spec['max']}]"),
                        "matched_span": m.group(0),
                    })
                    continue
                # Read the current value to build a from/to diff.
                current = await self._current_setting(setting_key)
                if current == proposed_value:
                    continue
                rule_candidates.append({
                    "setting_key": setting_key,
                    "from_value": current,
                    "to_value": proposed_value,
                    "rationale": f"Policy clause: {m.group(0).strip()}",
                    "kind": kind,
                })

        # LLM clause extraction — additive. Whatever the regex found stays authoritative.
        # LLM-only picks land in `manual_items` unless they hit an allow-listed key.
        if enable_llm:
            already_spans = {rc.get("matched_span", "").strip().lower()
                              for rc in rule_candidates}
            already_spans |= {m.get("matched_span", "").strip().lower()
                               for m in manual_items}
            result = await intelligence_read(
                feature="policy_compiler",
                text=policy_text[:8000],
                schema=_LlmClause,
                hint=("Extract ONE material governance clause about supervision meeting "
                       "intervals, supervisee caps, annual reviews, or funding gaps."),
            )
            if not result.needs_manual:
                span = (result.fields.get("matched_span") or "").strip()
                setting_key = (result.fields.get("setting_key") or "").strip()
                proposed_value = result.fields.get("proposed_value")
                if span and span.lower() not in already_spans:
                    spec = ALLOW_LISTED_SETTINGS.get(setting_key)
                    if (spec is not None and isinstance(proposed_value, int)
                            and spec["min"] <= proposed_value <= spec["max"]):
                        current = await self._current_setting(setting_key)
                        if current != proposed_value:
                            rule_candidates.append({
                                "setting_key": setting_key,
                                "from_value": current,
                                "to_value": proposed_value,
                                "rationale": f"LLM-extracted clause: {span[:200]}",
                                "kind": "llm",
                                "matched_span": span,
                                "engine": "llm",
                            })
                    else:
                        manual_items.append({
                            "setting_key": setting_key or "unknown",
                            "reason": "LLM found a clause outside the allow-list — manual review",
                            "matched_span": span,
                            "engine": "llm",
                        })

        # Impact simulation is compact for P6: for each candidate, count records the
        # change would touch. Wired lightly so the endpoint returns real numbers.
        simulation = await self._simulate(rule_candidates)

        proposal = PolicyProposal(
            source_version_id=version.id,
            rule_candidates=rule_candidates + [{"manual": True, **m} for m in manual_items],
            config_candidates=[],
            simulation_result=simulation,
            status="draft",
        )
        self.session.add(proposal)
        await self.session.flush()
        return proposal

    async def _current_setting(self, key: str) -> Any | None:
        try:
            from app.modules.settings.service import setting_value
            return await setting_value(self.session, key)
        except Exception:  # noqa: BLE001
            return None

    async def _simulate(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        # Simple impact query — how many students/milestones would fall in scope of the
        # new bounds. Kept lightweight; full timeline preview is a Phase 6+ addition.
        from app.modules.progression.models import Milestone
        from sqlalchemy import func
        total = (await self.session.execute(
            select(func.count()).select_from(Milestone)
        )).scalar_one()
        return {
            "candidates": len(candidates),
            "milestone_universe": int(total),
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    async def review(self, proposal_id: uuid.UUID, disposition: str,
                      reviewed_by_user_id: uuid.UUID | None) -> PolicyProposal:
        row = await self.session.get(PolicyProposal, proposal_id)
        if row is None:
            raise NotFoundError("Policy proposal not found.")
        if disposition not in ("reviewed", "approved", "rejected", "published"):
            raise ValueError(f"Invalid disposition: {disposition}")
        allowed = _VALID_TRANSITIONS.get(row.status, set())
        if disposition not in allowed:
            reason = (
                f"'{row.status}' is a terminal state and cannot be changed."
                if not allowed else
                f"A proposal in '{row.status}' can only move to: {', '.join(sorted(allowed))}."
            )
            raise ValidationAppError(
                f"Cannot move proposal from '{row.status}' to '{disposition}'. {reason}"
            )
        row.status = disposition
        row.reviewed_by_user_id = reviewed_by_user_id
        row.reviewed_at = datetime.now(timezone.utc)
        if disposition == "published":
            row.published_at = datetime.now(timezone.utc)
        await self.session.flush()
        return row
