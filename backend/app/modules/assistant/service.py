"""Assistant orchestration (CB-A — fuzzy+BoW, zero LLM).

The LLM path was retired in CB-A. Every query is routed by the deterministic fuzzy router
(`app.modules.fuzzy`) against the intent registry (`app.modules.fuzzy.vocab`). Three outcomes:

- ``answer``           — a confident intent match; run the bound tool, return a card.
- ``clarify``          — top intents within CLARIFY_MARGIN; return chip options.
- ``not_understood``   — no intent hit above threshold; return honest hint with the closest
                         candidates as chips (see CB-B for the write-intent + chip flow;
                         CB-A already surfaces the chip list here).

Safety properties:
- executes as the signed-in user; every tool applies that user's row scope
- **read-only**: no tool in this phase mutates anything
- no external calls, no API key, no network required
- every response carries `trace` so the interpretation is auditable
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal
from app.modules.assistant.tools import NAV_TARGETS, ToolBox
from app.modules.assistant.write_actions import registry as write_registry
from app.modules.fuzzy import pending_write, slot_memory
from app.modules.fuzzy.intents import registry as intent_registry
from app.modules.fuzzy.router import RouteDecision, route
from app.modules.fuzzy.telemetry import log_unmatched

logger = logging.getLogger("pgr.assistant")


class AssistantService:
    def __init__(self, session: AsyncSession, principal: Principal) -> None:
        self.session = session
        self.principal = principal
        self.tools = ToolBox(session, principal)

    async def query(self, text: str, history: list[dict] | None = None,
                    session_id: str | None = None) -> dict:
        """Entry point.

        CB-B additions:
        - Pronoun resolution via slot_memory. A follow-up like "her payments" reuses the last
          resolved entity for THIS user+session, if it exists and hasn't expired.
        - Write-intent handling. If the top intent is a write action, stage a pending record
          and return a confirm_write envelope. The action does NOT run without an explicit
          `/assistant/confirm` call.
        """
        # 1. Rewrite pronouns before we route.
        prepared = self._resolve_pronouns(text or "", session_id)

        decision = await route(prepared, self.principal, self.session)

        # 2. Remember the resolved entity for the next turn (60s TTL).
        if decision.entities:
            top = decision.entities[0]
            slot_memory.remember_person(
                str(self.principal.user_id), session_id,
                entity_id=top.id, entity_name=top.name, student_ref=top.student_ref,
            )

        # 3. Dispatch.
        if decision.kind == "answer":
            top = decision.matches[0].intent
            if top.write_action:
                return await self._render_confirm_write(decision, top)
            return await self._render_answer(decision)
        if decision.kind == "clarify":
            await self._log_gap(decision)
            return self._render_clarify(decision)
        await self._log_gap(decision)
        return self._render_not_understood(decision)

    async def _log_gap(self, decision: RouteDecision) -> None:
        """CB-C — record clarify/unmatched queries for the vocab-review admin surface."""
        role = (self.principal.roles or [None])[0] if getattr(self.principal, "roles", None) else None
        await log_unmatched(
            self.session,
            original_query=decision.query,
            entity_names=[e.name for e in decision.entities],
            suggested_intents=[
                {"name": m.intent.name, "score": round(m.score, 3)} for m in decision.matches
            ],
            session_role=role,
        )

    def _resolve_pronouns(self, text: str, session_id: str | None) -> str:
        """Substitute personal pronouns with the last-remembered person's name."""
        tokens = text.split()
        if not any(t.lower().strip(",.?!") in slot_memory.PRONOUNS_PERSON for t in tokens):
            return text
        remembered = slot_memory.recall_person(str(self.principal.user_id), session_id)
        if remembered is None:
            return text
        # Simple substitution: swap the first pronoun for the remembered name.
        replaced: list[str] = []
        done = False
        for t in tokens:
            bare = t.lower().strip(",.?!")
            if not done and bare in slot_memory.PRONOUNS_PERSON:
                replaced.append(remembered.entity_name)
                done = True
            else:
                replaced.append(t)
        return " ".join(replaced)

    async def confirm(self, pending_id: str) -> dict:
        """Execute a previously-staged write intent. Consumes the pending record."""
        pending = pending_write.pop(str(self.principal.user_id), pending_id)
        if pending is None:
            return {
                "kind": "not_understood",
                "answer": "That confirmation has expired or was never issued. Please re-ask.",
                "card": None, "chips": [], "links": [], "trace": {},
                "readOnly": False, "path": "unmatched", "data": {}, "understood": "",
                "toolsUsed": [],
            }
        # Second permission check at execute time — belt-and-braces.
        result = await write_registry.execute(
            pending.action, self.session, self.principal, pending.args,
        )
        return {
            "kind": "answer",
            "answer": f"Done — {pending.target.get('label', pending.action)}.",
            "card": {"spec": f"write_result_{pending.action}", "data": result},
            "chips": [], "links": self._links_from(result),
            "trace": {"executed": pending.action, "pendingId": pending.id},
            "toolsUsed": [pending.action], "readOnly": False,
            "path": "fuzzy", "data": result, "understood": pending.target.get("label", ""),
        }

    async def _render_confirm_write(self, d: RouteDecision, intent) -> dict:
        """Stage a write intent and return the confirmation envelope. No mutation happens here."""
        # Permission check BEFORE staging so a 403 arrives fast.
        if intent.write_permission and not self.principal.has_permission(intent.write_permission):
            return self._envelope(
                kind="not_understood", decision=d,
                text=f"You don't have the {intent.write_permission} permission for that action.",
                chips=[],
            )

        plan = await write_registry.stage(intent.write_action, self.session, self.principal, d)
        if plan is None:
            # Couldn't identify the target — degrade to clarify with a chip prompting the user
            # to name the entity explicitly.
            return self._envelope(
                kind="clarify", decision=d,
                text=(f"To {intent.description.lower()} I need the student's name or ref. "
                       "Try adding it, e.g. 'approve Alice Khan's payment'."),
                chips=[],
            )

        pending = pending_write.stage(
            str(self.principal.user_id),
            action=plan.action, target=plan.target, args=plan.args, diff=plan.diff,
        )
        return {
            "kind": "confirm_write",
            "answer": f"About to {intent.description.lower()} Confirm?",
            "card": {
                "spec": intent.card,
                "data": {
                    "pendingId": pending.id, "action": plan.action,
                    "target": plan.target, "diff": plan.diff,
                    "expiresInSeconds": pending_write.TTL_SECONDS,
                },
            },
            "chips": [], "links": [],
            "trace": d.trace(),
            "toolsUsed": [], "readOnly": False,
            "path": "fuzzy", "data": plan.diff, "understood": plan.target.get("label", ""),
            "pendingId": pending.id,
        }

    # ---------------- kind dispatch ----------------

    async def _render_answer(self, d: RouteDecision) -> dict:
        top = d.matches[0]
        intent = top.intent
        args = await self._build_args(intent, d)
        data = await self._call_tool(intent.tool, args)
        return self._envelope(
            kind="answer", decision=d, text=self._phrase(intent, args, data),
            card={"spec": intent.card, "data": data},
            tools_used=[intent.tool],
        )

    def _render_clarify(self, d: RouteDecision) -> dict:
        chips = [
            {"label": self._chip_label(m.intent),
             "description": m.intent.description,
             "intent": m.intent.name,
             "slots": self._slots_for_chip(m.intent, d),
             "score": round(m.score, 3)}
            for m in d.matches
        ]
        return self._envelope(
            kind="clarify", decision=d,
            text="A few things match — which did you mean?", chips=chips,
        )

    def _render_not_understood(self, d: RouteDecision) -> dict:
        # Even at not-understood we surface the closest 3 intents so the user gets somewhere.
        near = d.matches[:3]
        chips = [
            {"label": self._chip_label(m.intent),
             "description": m.intent.description,
             "intent": m.intent.name,
             "slots": self._slots_for_chip(m.intent, d),
             "score": round(m.score, 3)}
            for m in near
        ]
        hint = ("I didn't recognise that. Try one of these, or ask 'help' to see the full list."
                if chips else
                "I didn't recognise that. Try 'help' to see the questions I know how to answer.")
        return self._envelope(kind="not_understood", decision=d, text=hint, chips=chips)

    # ---------------- helpers ----------------

    async def _build_args(self, intent, d: RouteDecision) -> dict[str, Any]:
        args: dict[str, Any] = dict(intent.default_args)
        # Person slot
        if "person" in intent.optional_slots and d.entities:
            args["studentId"] = d.entities[0].id
        # Window slot
        if "window" in intent.optional_slots and d.time_slot:
            args["windowFrom"] = d.time_slot.start.isoformat()
            args["windowTo"] = d.time_slot.end.isoformat()
        # Navigation target extraction from tokens
        if intent.tool == "navigate":
            target = self._pick_nav_target(d.tokens)
            if target:
                args["target"] = target
        return args

    def _pick_nav_target(self, tokens: tuple[str, ...]) -> str | None:
        token_set = set(tokens)
        # Try each nav key against the token set; longest match wins so "supervision workforce"
        # beats bare "supervision".
        candidates = sorted(NAV_TARGETS.keys(), key=len, reverse=True)
        for key in candidates:
            key_tokens = set(key.replace("-", " ").replace("_", " ").split())
            if key_tokens.issubset(token_set):
                return key
        return None

    async def _call_tool(self, tool: str, args: dict) -> dict:
        if tool == "__help__":
            return self._help_payload()
        if tool == "funding_cashflow":
            # New W4 endpoint; wrap it as a tool.
            from app.modules.funding.finance_lens import FinanceLensService
            from datetime import date as _date
            from app.modules.student_record.router import scoped_ids
            allowed = await scoped_ids(self.principal, self.session)
            wf = _date.fromisoformat(args["windowFrom"]) if args.get("windowFrom") else None
            wt = _date.fromisoformat(args["windowTo"]) if args.get("windowTo") else None
            return await FinanceLensService(self.session).snapshot(
                allowed_ids=allowed, window_from=wf, window_to=wt,
            )
        if tool == "supervisor_workforce":
            from app.modules.supervision.workforce_lens import WorkforceLensService
            return await WorkforceLensService(self.session).snapshot()
        # Fall back to the existing tool registry (find_student, get_student_overview,
        # cohort_query, get_analytics, get_enterprise_360, list_my_tasks, navigate).
        return await self.tools.execute(tool, args)

    def _help_payload(self) -> dict:
        groups: dict[str, list[dict]] = {}
        for intent in intent_registry().all():
            groups.setdefault(intent.group, []).append({
                "name": intent.name, "description": intent.description,
                "examples": list(intent.examples[:3]),
            })
        return {"groups": [{"name": g, "intents": v} for g, v in sorted(groups.items())]}

    def _phrase(self, intent, args: dict, data: dict) -> str:
        # A single, deterministic phrasing per intent — no free text. Cards carry the detail.
        if intent.tool == "__help__":
            n = sum(len(g["intents"]) for g in data.get("groups", []))
            return f"I know {n} intents across {len(data.get('groups', []))} groups."
        if intent.tool == "navigate":
            return f"Opening {data.get('label', 'that')}."
        if intent.tool == "list_my_tasks":
            n = len(data.get("tasks", []) or [])
            return f"You have {n} open task{'s' if n != 1 else ''}."
        if intent.tool == "funding_cashflow":
            counts = data.get("counts", {})
            lens = args.get("lens")
            if lens == "held":
                return f"{counts.get('held', 0)} payment(s) currently held by Finance."
            if lens == "overdueApproved":
                return f"{counts.get('overdueApproved', 0)} approved payment(s) overdue."
            if lens == "paidWithoutFinanceReference":
                return f"{counts.get('paidWithoutFinanceReference', 0)} paid without a Finance reference."
            totals = data.get("totals", {})
            return f"Paid this window: {totals.get('paid', '0')}. Held: {totals.get('held', '0')}."
        if intent.tool == "supervisor_workforce":
            t = data.get("totals", {})
            return (f"{t.get('supervisors', 0)} supervisors, "
                    f"{t.get('overCapacity', 0)} over cap, "
                    f"{t.get('pendingRequests', 0)} pending requests.")
        if intent.tool == "get_analytics":
            risk = data.get("risk", {}) or {}
            return f"{risk.get('atRiskCount', 0)} of {risk.get('activeStudents', 0)} active students at risk."
        if intent.tool == "cohort_query":
            n = data.get("count", 0)
            return f"{n} student{'s' if n != 1 else ''} match."
        if intent.tool == "get_student_overview":
            st = data.get("student", {}) or {}
            return f"{st.get('personName', '?')} ({st.get('studentRef', '?')}) — {st.get('status', '?')}."
        return "Done."

    def _chip_label(self, intent) -> str:
        """Chip button text. Use the intent's first example so clicking re-submits a phrasing
        that will actually match — the description often uses words the vocab doesn't."""
        if intent.examples:
            return intent.examples[0]
        return intent.description

    def _slots_for_chip(self, intent, d: RouteDecision) -> dict:
        slots: dict[str, Any] = {}
        if "person" in intent.optional_slots and d.entities:
            slots["personId"] = d.entities[0].id
            slots["personName"] = d.entities[0].name
        if "window" in intent.optional_slots and d.time_slot:
            slots["window"] = d.time_slot.as_iso()
        return slots

    def _envelope(
        self, *, kind: str, decision: RouteDecision, text: str,
        card: dict | None = None, chips: list[dict] | None = None,
        tools_used: list[str] | None = None,
    ) -> dict:
        links = self._links_from(card["data"] if card else {})
        return {
            "kind": kind,
            "answer": text,
            "card": card,
            "chips": chips or [],
            "links": links,
            "trace": decision.trace(),
            "toolsUsed": tools_used or [],
            "readOnly": True,
            # Back-compat with the old envelope keys the FE still reads:
            "path": {"answer": "fuzzy", "clarify": "clarify", "not_understood": "unmatched"}[kind],
            "data": card["data"] if card else {},
            "understood": text,
        }

    @staticmethod
    def _links_from(out: dict) -> list[dict]:
        links: list[dict] = []
        if isinstance(out, dict):
            if isinstance(out.get("link"), str):
                links.append({"label": "Open", "href": out["link"]})
            for row in (out.get("students") or out.get("candidates") or out.get("supervisors") or [])[:10]:
                if isinstance(row, dict) and row.get("link"):
                    links.append({
                        "label": row.get("personName") or row.get("studentRef") or "Open",
                        "href": row["link"],
                    })
        # Dedup preserving order.
        seen, unique = set(), []
        for l in links:
            if l["href"] not in seen:
                seen.add(l["href"])
                unique.append(l)
        return unique[:10]
