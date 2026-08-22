"""Integration hub service — the outbox dispatcher and inbound webhook handler (arch §10.2).

Dispatch is idempotent: only outbox events with dispatched_at IS NULL are processed, and each is
marked dispatched once its adapters have been called. Inbound messages are deduplicated by
(system, source_id).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.errors import ConflictError
from app.modules.integration.adapters import ROUTES, deliver
from app.modules.integration.constants import Direction, IntegrationStatus
from app.modules.integration.models import IntegrationLog
from app.modules.integration.repository import IntegrationRepository

logger = logging.getLogger("pgr.integration")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _backoff_seconds(attempts: int) -> int:
    # Exponential backoff, capped: 2, 4, 8, 16, ... up to 5 min.
    return min(2 ** attempts, 300)


class IntegrationService:
    def __init__(self, repo: IntegrationRepository) -> None:
        self.repo = repo
        self.session = repo.session

    async def dispatch_pending(self) -> dict:
        settings = get_settings()
        events = await self.repo.pending_outbox()
        dispatched = 0
        outbound = 0
        failed = 0
        dead = 0
        for ev in events:
            adapters = ROUTES.get(ev.event_type, [])
            if not adapters:
                self.repo.add(IntegrationLog(
                    direction=Direction.outbound, system="internal", event_type=ev.event_type,
                    aggregate_type=ev.aggregate_type, aggregate_id=ev.aggregate_id,
                    status=IntegrationStatus.skipped, detail={"note": "no external route"}, created_at=_now(),
                ))
                ev.dispatched_at = _now()
                dispatched += 1
                continue
            try:
                for adapter in adapters:
                    message = await deliver(adapter, ev.event_type, ev.payload or {})
                    self.repo.add(IntegrationLog(
                        direction=Direction.outbound, system=adapter.system, event_type=ev.event_type,
                        aggregate_type=ev.aggregate_type, aggregate_id=ev.aggregate_id,
                        status=IntegrationStatus.success, detail=message, created_at=_now(),
                    ))
                    outbound += 1
                ev.dispatched_at = _now()
                ev.last_error = None
                dispatched += 1
            except Exception as exc:  # delivery failed — retry with backoff, then dead-letter
                ev.attempts = (ev.attempts or 0) + 1
                ev.last_error = str(exc)[:300]
                self.repo.add(IntegrationLog(
                    direction=Direction.outbound, system="integration", event_type=ev.event_type,
                    aggregate_type=ev.aggregate_type, aggregate_id=ev.aggregate_id,
                    status=IntegrationStatus.failed,
                    detail={"attempt": ev.attempts, "error": ev.last_error}, created_at=_now(),
                ))
                if ev.attempts >= settings.outbox_max_attempts:
                    ev.dead_lettered = True
                    dead += 1
                    logger.error("outbox event %s dead-lettered after %s attempts", ev.id, ev.attempts)
                else:
                    ev.next_attempt_at = _now() + timedelta(seconds=_backoff_seconds(ev.attempts))
                    failed += 1
        await self.session.commit()
        return {"dispatched": dispatched, "outboundCalls": outbound, "failed": failed, "deadLettered": dead}

    async def reconciliation(self, window_days: int = 30) -> dict:
        """Is the integration boundary healthy, and what needs a human? (Phase 7, item R3.)

        Answers three questions an administrator actually asks:
        1. Is anything stuck going **out**? (pending backlog, dead letters)
        2. Did anything fail coming **in**? (failed inbound messages, unhandled types)
        3. What is **waiting on a person**? (unmatched HR records queued as tasks)
        """
        from datetime import timedelta

        from sqlalchemy import func, select

        from app.modules.workflow.constants import OPEN_TASK_STATES
        from app.modules.workflow.models import OutboxEvent, Task

        since = _now() - timedelta(days=window_days)

        # --- outbound ---
        oldest_pending = (await self.session.execute(
            select(func.min(OutboxEvent.created_at)).where(
                OutboxEvent.dispatched_at.is_(None), OutboxEvent.dead_lettered.is_(False)
            )
        )).scalar_one_or_none()
        dispatched = (await self.session.execute(
            select(func.count()).select_from(OutboxEvent)
            .where(OutboxEvent.dispatched_at.is_not(None), OutboxEvent.created_at >= since)
        )).scalar_one()

        dead = await self.repo.dead_lettered(50)

        # --- inbound, by system and outcome ---
        rows = (await self.session.execute(
            select(IntegrationLog.system, IntegrationLog.direction,
                   IntegrationLog.status, func.count())
            .where(IntegrationLog.created_at >= since)
            .group_by(IntegrationLog.system, IntegrationLog.direction, IntegrationLog.status)
        )).all()
        by_system: dict[str, dict] = {}
        for system, direction, status, count in rows:
            d = (direction.value if hasattr(direction, "value") else direction)
            st = (status.value if hasattr(status, "value") else status)
            entry = by_system.setdefault(system, {"inbound": {}, "outbound": {}})
            entry.setdefault(d, {})[st] = int(count)

        failed_inbound = [
            {
                "id": str(l.id), "system": l.system, "eventType": l.event_type,
                "sourceId": l.source_id,
                "error": (l.detail or {}).get("_error"),
                "createdAt": l.created_at.isoformat() if l.created_at else None,
            }
            for l in (await self.session.execute(
                select(IntegrationLog).where(
                    IntegrationLog.direction == Direction.inbound,
                    IntegrationLog.status == IntegrationStatus.failed,
                    IntegrationLog.created_at >= since,
                ).order_by(IntegrationLog.created_at.desc()).limit(25)
            )).scalars().all()
        ]

        # --- waiting on a person ---
        unmatched = [
            {
                "taskId": str(t.id), "title": t.title, "payload": t.payload,
                "createdAt": t.created_at.isoformat() if t.created_at else None,
            }
            for t in (await self.session.execute(
                select(Task).where(
                    Task.aggregate_type == "hr_employee_record",
                    Task.status.in_(OPEN_TASK_STATES),
                ).order_by(Task.created_at.desc()).limit(25)
            )).scalars().all()
        ]

        pending = await self.repo.pending_count()
        issues = len(dead) + len(failed_inbound) + len(unmatched)
        return {
            "windowDays": window_days,
            "outbound": {
                "pending": pending,
                "dispatchedInWindow": int(dispatched),
                "deadLettered": await self.repo.dead_letter_count(),
                "oldestPendingAt": oldest_pending.isoformat() if oldest_pending else None,
                "deadLetters": [
                    {"id": str(e.id), "eventType": e.event_type, "attempts": e.attempts,
                     "lastError": e.last_error,
                     "createdAt": e.created_at.isoformat() if e.created_at else None}
                    for e in dead
                ],
            },
            "inbound": {"bySystem": by_system, "failed": failed_inbound},
            "awaitingPeople": {"unmatchedHrRecords": unmatched},
            "healthy": issues == 0 and pending == 0,
            "issueCount": issues,
        }

    async def replay_dead_letter(self, event_id) -> bool:
        """Reset a dead-lettered event so the next dispatch retries it (arch §10.2 reconciliation)."""
        ev = await self.repo.get_outbox_event(event_id)
        if ev is None or not ev.dead_lettered:
            return False
        ev.dead_lettered = False
        ev.attempts = 0
        ev.next_attempt_at = None
        ev.last_error = None
        await self.session.commit()
        return True

    async def apply_hr_employee_record(self, payload: dict) -> dict:
        """Map an inbound HR employee record onto an existing person (Phase 6.4).

        Matching is **deterministic only** — email, then exact full name. Anything ambiguous or
        unmatched becomes a task for a human; identities are never merged on a guess, because a
        wrong merge silently joins two people's records and is very hard to undo.
        """
        from datetime import date

        from sqlalchemy import func, select

        from app.modules.person.constants import PersonRelationshipType
        from app.modules.person.models import Person
        from app.modules.person.repository import PersonRepository
        from app.modules.person.service import PersonService
        from app.modules.workflow.engine import WorkflowEngine

        email = (payload.get("email") or "").strip().lower()
        given = (payload.get("givenName") or "").strip()
        family = (payload.get("familyName") or "").strip()
        started = payload.get("startDate")

        matches: list[Person] = []
        if email:
            matches = list((await self.session.execute(
                select(Person).where(func.lower(Person.email) == email)
            )).scalars().all())
        if not matches and given and family:
            matches = list((await self.session.execute(
                select(Person).where(
                    func.lower(Person.given_name) == given.lower(),
                    func.lower(Person.family_name) == family.lower(),
                )
            )).scalars().all())

        if len(matches) != 1:
            reason = "no match" if not matches else f"{len(matches)} possible matches"
            WorkflowEngine(self.session).create_task(
                title=f"Match HR employee record: {given} {family}".strip(),
                assignee_role="PGR Administrator",
                aggregate_type="hr_employee_record", aggregate_id=None,
                payload={"reason": reason, "email": email or None,
                         "givenName": given or None, "familyName": family or None},
            )
            await self.session.commit()
            return {"status": "queued_for_review", "reason": reason, "candidates": len(matches)}

        person = matches[0]
        await PersonService(PersonRepository(self.session)).transition_identity(
            person.id, end_type=None, open_type=PersonRelationshipType.employee,
            source_system="hr", on_date=date.fromisoformat(started) if started else None,
        )
        await self.session.commit()
        return {"status": "linked", "personId": str(person.id)}

    async def handle_inbound(self, system: str, source_id: str, event_type: str, payload: dict) -> dict:
        """Record an inbound partner message and **apply** it where we know how (arch §10.2).

        Phase 6 note: logging alone was not enough — the gap analysis specifically asked for real
        partner mappings, not just adapters. Recognised messages are now applied to the domain;
        anything unrecognised is still logged (so nothing is lost) and reported as `logged_only`.
        """
        # Idempotency: ignore repeats of an already-processed source id (arch §10.2).
        if await self.repo.inbound_exists(system, source_id):
            return {"status": "duplicate", "sourceId": source_id}

        applied: dict | None = None
        error: str | None = None
        try:
            applied = await self._apply_inbound(system, event_type, payload)
        except Exception as exc:  # a bad partner payload must not lose the message
            error = f"{type(exc).__name__}: {exc}"

        try:
            self.repo.add(IntegrationLog(
                direction=Direction.inbound, system=system, event_type=event_type,
                source_id=source_id,
                status=IntegrationStatus.failed if error else IntegrationStatus.success,
                detail={**payload, "_applied": applied, "_error": error},
                created_at=_now(),
            ))
            await self.session.commit()
        except Exception as exc:  # unique (system, source_id) race
            await self.session.rollback()
            raise ConflictError("Duplicate inbound message") from exc

        if error:
            return {"status": "logged_with_error", "sourceId": source_id, "error": error}
        if applied is None:
            return {"status": "logged_only", "sourceId": source_id,
                    "note": f"No handler for {system}/{event_type}; the message was recorded."}
        return {"status": "processed", "sourceId": source_id, "applied": applied}

    # Partner message → domain action. Keeping this table small and explicit is deliberate:
    # an inbound message should only ever reach a handler we chose for it.
    async def _apply_inbound(self, system: str, event_type: str, payload: dict) -> dict | None:
        key = (system.lower(), (event_type or "").lower())
        if key in {("research", "award.updated"), ("research", "award.created")}:
            from app.modules.research.repository import ResearchRepository
            from app.modules.research.service import ResearchService

            award = await ResearchService(ResearchRepository(self.session)).upsert_from_research_system(
                payload, system="research"
            )
            return {"handler": "research_award", "awardRef": award.award_ref, "id": str(award.id)}
        if key in {("hr", "employee.appointed"), ("hr", "employee.updated")}:
            return {"handler": "hr_employee", **(await self.apply_hr_employee_record(payload))}
        return None

    async def recent_logs(self, limit: int = 50):
        return await self.repo.recent_logs(limit)

    async def pending_count(self) -> int:
        return await self.repo.pending_count()
