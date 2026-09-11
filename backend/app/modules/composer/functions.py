"""The data functions — the only way the composer can obtain a number.

The model does not write SQL and does not invent values. It picks from this catalogue,
receives typed results, and decides how to *draw* them. That constraint is what makes the
output trustworthy: every figure on screen came out of a query somebody reviewed.

Each function is:

* **Permission-scoped.** The catalogue shown to the model is filtered by what the caller
  may see, and the check is repeated at call time. A supervisor cannot reach funding data
  by asking nicely.
* **Bounded.** Row caps and date windows are enforced here, not left to the prompt.
* **JSON-shaped.** Plain dicts and lists — no ORM objects leak into a prompt.

Registering a function is one decorator. The prompt-facing catalogue is generated from the
registry, so there is no second place to update.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal

Handler = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class DataFunction:
    name: str
    description: str
    handler: Handler
    permission: str | None = None
    params: dict[str, str] = field(default_factory=dict)


REGISTRY: dict[str, DataFunction] = {}


def data_function(
    *, name: str, description: str, permission: str | None = None,
    params: dict[str, str] | None = None,
) -> Callable[[Handler], Handler]:
    def decorate(fn: Handler) -> Handler:
        REGISTRY[name] = DataFunction(
            name=name, description=description, handler=fn,
            permission=permission, params=params or {},
        )
        return fn

    return decorate


def available_to(principal: Principal) -> list[DataFunction]:
    return [
        f for f in REGISTRY.values()
        if f.permission is None or principal.has_permission(f.permission)
    ]


def catalogue_for_prompt(principal: Principal) -> str:
    """The function list as the model sees it. Only what this caller may call."""
    lines: list[str] = []
    for f in available_to(principal):
        args = ", ".join(f"{k}: {v}" for k, v in f.params.items()) or "no arguments"
        lines.append(f"- {f.name}({args})\n    {f.description}")
    return "\n".join(lines)


class FunctionError(RuntimeError):
    """Bad call — unknown name, missing permission, or unresolvable argument."""


async def call(
    name: str, *, session: AsyncSession, principal: Principal, **kwargs: Any
) -> Any:
    fn = REGISTRY.get(name)
    if fn is None:
        raise FunctionError(f"There is no data function called '{name}'.")
    if fn.permission and not principal.has_permission(fn.permission):
        raise FunctionError(f"'{name}' requires the {fn.permission} permission.")
    unexpected = set(kwargs) - set(fn.params)
    if unexpected:
        raise FunctionError(
            f"'{name}' does not take {', '.join(sorted(unexpected))}. "
            f"Accepted: {', '.join(fn.params) or 'none'}."
        )
    return await fn.handler(session=session, principal=principal, **kwargs)


# ----------------------------------------------------------------------------- helpers


def _months_between(start: date | None, end: date | None) -> int | None:
    if start is None or end is None:
        return None
    return (end.year - start.year) * 12 + (end.month - start.month)


def _as_uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise FunctionError(
            f"{label} must be an id returned by a previous function, not a name."
        ) from exc


async def _student_row(session: AsyncSession, student_id: uuid.UUID):
    from app.modules.person.models import Person
    from app.modules.student_record.models import Student

    row = (
        await session.execute(
            select(Student, Person)
            .join(Person, Person.id == Student.person_id)
            .where(Student.id == student_id)
        )
    ).first()
    if row is None:
        raise FunctionError("No student with that id.")
    return row


# --------------------------------------------------------------------------- resolution


@data_function(
    name="search_student",
    description=(
        "Find students by name or student reference. Always call this first when the user "
        "names a person — every other student function needs the id it returns."
    ),
    permission="student.read",
    params={"query": "part of a name or a student reference"},
)
async def search_student(*, session: AsyncSession, principal: Principal, query: str) -> list[dict]:
    from app.modules.person.models import Person
    from app.modules.student_record.models import Student

    cleaned = str(query).lower().strip()
    if not cleaned:
        return []

    full_name = func.lower(Person.given_name + " " + Person.family_name)
    # "Marcus Bell" matches neither given_name nor family_name on its own, so match the
    # concatenation as well, and require every token to appear somewhere. Without this a
    # perfectly ordinary full name returns nothing and the caller wastes a round.
    condition = (
        full_name.like(f"%{cleaned}%")
        | func.lower(Student.student_ref).like(f"%{cleaned}%")
    )
    for token in cleaned.split():
        condition = condition | (
            func.lower(Person.given_name).like(f"%{token}%")
            | func.lower(Person.family_name).like(f"%{token}%")
        )

    rows = (
        await session.execute(
            select(Student, Person)
            .join(Person, Person.id == Student.person_id)
            .where(condition)
            .order_by(
                # Exact full-name matches first so a precise question gets a precise answer.
                (full_name == cleaned).desc(),
                Person.family_name,
            )
            .limit(10)
        )
    ).all()
    return [
        {
            "student_id": str(s.id),
            "name": f"{p.given_name} {p.family_name}",
            "student_ref": s.student_ref,
            "status": getattr(s.status, "value", str(s.status)),
        }
        for s, p in rows
    ]


# ------------------------------------------------------------------------------ student


@data_function(
    name="student_overview",
    description=(
        "Core facts for one student: name, reference, programme, status, study mode, start "
        "date, expected end date, and how many months into the registration they are."
    ),
    permission="student.read",
    params={"student_id": "id from search_student"},
)
async def student_overview(*, session: AsyncSession, principal: Principal, student_id: str) -> dict:
    from app.modules.student_record.models import Programme

    sid = _as_uuid(student_id, "student_id")
    student, person = await _student_row(session, sid)

    programme = None
    if student.programme_id:
        programme = (
            await session.execute(
                select(Programme.name).where(Programme.id == student.programme_id)
            )
        ).scalar_one_or_none()

    today = date.today()
    return {
        "student_id": str(student.id),
        "name": f"{person.given_name} {person.family_name}",
        "student_ref": student.student_ref,
        "programme": programme,
        "status": getattr(student.status, "value", str(student.status)),
        "study_mode": getattr(student.study_mode, "value", str(student.study_mode)),
        "start_date": student.start_date.isoformat() if student.start_date else None,
        "expected_end_date": (
            student.expected_end_date.isoformat() if student.expected_end_date else None
        ),
        "months_elapsed": _months_between(student.start_date, today),
        "months_total": _months_between(student.start_date, student.expected_end_date),
        "months_remaining": _months_between(today, student.expected_end_date),
    }


@data_function(
    name="student_milestones",
    description=(
        "Every progression milestone for a student with its due date, status and how many "
        "days early or late it was decided. Negative days_late means ahead of schedule."
    ),
    permission="progression.read",
    params={"student_id": "id from search_student"},
)
async def student_milestones(
    *, session: AsyncSession, principal: Principal, student_id: str
) -> list[dict]:
    from app.modules.progression.models import Milestone, MilestoneDefinition

    sid = _as_uuid(student_id, "student_id")
    rows = (
        await session.execute(
            select(Milestone, MilestoneDefinition.name)
            .join(MilestoneDefinition, MilestoneDefinition.id == Milestone.milestone_definition_id)
            .where(Milestone.student_id == sid)
            .order_by(Milestone.due_date)
        )
    ).all()

    today = date.today()
    out: list[dict] = []
    for milestone, name in rows:
        status = getattr(milestone.status, "value", str(milestone.status))
        overdue_days = None
        if milestone.due_date and status not in {"decided", "passed", "waived"}:
            overdue_days = max(0, (today - milestone.due_date).days)
        out.append(
            {
                "milestone": name,
                "due_date": milestone.due_date.isoformat() if milestone.due_date else None,
                "status": status,
                "overdue_days": overdue_days,
            }
        )
    return out


@data_function(
    name="student_supervision",
    description=(
        "A student's supervisors with their roles, plus the meeting log: dates, formats and "
        "how many days have passed since the most recent meeting."
    ),
    permission="student.read",
    params={"student_id": "id from search_student"},
)
async def student_supervision(
    *, session: AsyncSession, principal: Principal, student_id: str
) -> dict:
    from app.modules.person.models import Person
    from app.modules.supervision.models import SupervisionMeeting, SupervisorRelationship

    sid = _as_uuid(student_id, "student_id")

    supervisors = (
        await session.execute(
            select(SupervisorRelationship, Person)
            .join(Person, Person.id == SupervisorRelationship.supervisor_person_id)
            .where(SupervisorRelationship.student_id == sid)
            .where(SupervisorRelationship.valid_to.is_(None))
        )
    ).all()

    meetings = (
        await session.execute(
            select(SupervisionMeeting)
            .where(SupervisionMeeting.student_id == sid)
            .order_by(SupervisionMeeting.met_on.desc())
            .limit(40)
        )
    ).scalars().all()

    last = meetings[0].met_on if meetings else None
    return {
        "supervisors": [
            {
                "name": f"{p.given_name} {p.family_name}",
                "role": getattr(r.role, "value", str(r.role)),
                "status": getattr(r.status, "value", str(r.status)),
            }
            for r, p in supervisors
        ],
        "meeting_count": len(meetings),
        "last_meeting_on": last.isoformat() if last else None,
        "days_since_last_meeting": (date.today() - last).days if last else None,
        "meetings": [
            {
                "met_on": m.met_on.isoformat(),
                "format": getattr(m.format, "value", str(m.format)),
            }
            for m in meetings[:24]
        ],
    }


@data_function(
    name="student_funding",
    description=(
        "A student's funding: current arrangements, the date funding runs out, and a month-"
        "by-month burndown of committed stipend still to be paid. Also reports the gap in "
        "months between funding ending and the expected submission date — a positive gap "
        "means the student is unfunded before they finish."
    ),
    permission="funding.read",
    params={"student_id": "id from search_student"},
)
async def student_funding(
    *, session: AsyncSession, principal: Principal, student_id: str
) -> dict:
    from app.modules.funding.constants import COMMITTED_PAYMENT_STATES
    from app.modules.funding.models import FundingArrangement, FundingSource, StipendPayment

    sid = _as_uuid(student_id, "student_id")
    student, _person = await _student_row(session, sid)

    arrangements = (
        await session.execute(
            select(FundingArrangement, FundingSource.name)
            .outerjoin(FundingSource, FundingSource.id == FundingArrangement.funding_source_id)
            .where(FundingArrangement.student_id == sid)
            .order_by(FundingArrangement.valid_from)
        )
    ).all()

    payments = (
        await session.execute(
            select(StipendPayment)
            .where(StipendPayment.student_id == sid)
            .order_by(StipendPayment.due_date)
        )
    ).scalars().all()

    committed = [p for p in payments if p.status in COMMITTED_PAYMENT_STATES]
    total = sum(float(p.amount) for p in committed)

    # Remaining committed stipend after each scheduled payment — the burndown line.
    burndown: list[dict] = []
    running = total
    for p in committed:
        running -= float(p.amount)
        burndown.append({"date": p.due_date.isoformat(), "remaining": round(running, 2)})

    funding_ends = max(
        (a.valid_to for a, _ in arrangements if a.valid_to is not None),
        default=None,
    )
    if committed:
        last_payment = committed[-1].due_date
        funding_ends = max(funding_ends, last_payment) if funding_ends else last_payment

    gap_months = _months_between(funding_ends, student.expected_end_date)

    return {
        "arrangements": [
            {
                "type": getattr(a.funding_type, "value", str(a.funding_type)),
                "source": source,
                "status": getattr(a.status, "value", str(a.status)),
                "valid_from": a.valid_from.isoformat() if a.valid_from else None,
                "valid_to": a.valid_to.isoformat() if a.valid_to else None,
                "stipend_amount": float(a.stipend_amount) if a.stipend_amount else None,
                "currency": a.currency,
            }
            for a, source in arrangements
        ],
        "committed_total": round(total, 2),
        "currency": next((p.currency for p in committed if p.currency), None),
        "burndown": burndown,
        "funding_ends_on": funding_ends.isoformat() if funding_ends else None,
        "expected_end_date": (
            student.expected_end_date.isoformat() if student.expected_end_date else None
        ),
        "unfunded_gap_months": gap_months if (gap_months or 0) > 0 else 0,
    }


@data_function(
    name="student_timeline",
    description=(
        "A merged, date-ordered event stream for one student — milestones, supervision "
        "meetings and funding changes — suitable for a timeline block."
    ),
    permission="student.read",
    params={
        "student_id": "id from search_student",
        "since_months": "how far back to look, in months (default 24)",
    },
)
async def student_timeline(
    *, session: AsyncSession, principal: Principal, student_id: str, since_months: int = 24
) -> list[dict]:
    from app.modules.funding.models import FundingArrangement
    from app.modules.progression.models import Milestone, MilestoneDefinition
    from app.modules.supervision.models import SupervisionMeeting

    sid = _as_uuid(student_id, "student_id")
    try:
        window = max(1, min(int(since_months), 120))
    except (TypeError, ValueError):
        window = 24
    cutoff = date.today() - timedelta(days=window * 31)

    events: list[dict] = []

    milestones = (
        await session.execute(
            select(Milestone, MilestoneDefinition.name)
            .join(MilestoneDefinition, MilestoneDefinition.id == Milestone.milestone_definition_id)
            .where(Milestone.student_id == sid)
        )
    ).all()
    for m, name in milestones:
        if m.due_date and m.due_date >= cutoff:
            events.append(
                {
                    "at": m.due_date.isoformat(),
                    "kind": "milestone",
                    "label": name,
                    "detail": getattr(m.status, "value", str(m.status)),
                }
            )

    meetings = (
        await session.execute(
            select(SupervisionMeeting)
            .where(SupervisionMeeting.student_id == sid)
            .where(SupervisionMeeting.met_on >= cutoff)
        )
    ).scalars().all()
    for m in meetings:
        events.append(
            {
                "at": m.met_on.isoformat(),
                "kind": "meeting",
                "label": "Supervision meeting",
                "detail": getattr(m.format, "value", str(m.format)),
            }
        )

    if principal.has_permission("funding.read"):
        arrangements = (
            await session.execute(
                select(FundingArrangement).where(FundingArrangement.student_id == sid)
            )
        ).scalars().all()
        for a in arrangements:
            if a.valid_from and a.valid_from >= cutoff:
                events.append(
                    {
                        "at": a.valid_from.isoformat(),
                        "kind": "funding",
                        "label": "Funding started",
                        "detail": getattr(a.funding_type, "value", str(a.funding_type)),
                    }
                )
            if a.valid_to and a.valid_to >= cutoff:
                events.append(
                    {"at": a.valid_to.isoformat(), "kind": "funding", "label": "Funding ended",
                     "detail": None}
                )

    events.sort(key=lambda e: e["at"])
    return events[:120]


# ------------------------------------------------------------------------------- cohort


@data_function(
    name="cohort_metrics",
    description=(
        "Headline counts across all students the caller can see: total, active, on leave, "
        "graduated, and how many are within six months of their expected end date."
    ),
    permission="student.read",
    params={},
)
async def cohort_metrics(*, session: AsyncSession, principal: Principal) -> dict:
    from app.modules.student_record.models import Student

    students = (await session.execute(select(Student))).scalars().all()
    today = date.today()
    soon = today + timedelta(days=183)

    by_status: dict[str, int] = {}
    for s in students:
        key = getattr(s.status, "value", str(s.status))
        by_status[key] = by_status.get(key, 0) + 1

    return {
        "total": len(students),
        "by_status": by_status,
        "finishing_within_6_months": sum(
            1 for s in students
            if s.expected_end_date and today <= s.expected_end_date <= soon
        ),
    }


@data_function(
    name="funding_cliff_scan",
    description=(
        "Every student whose funding ends before their expected submission date, with the "
        "size of the unfunded gap in months. Sorted worst gap first. This is the cohort-wide "
        "version of the gap reported by student_funding."
    ),
    permission="funding.read",
    params={"within_months": "only include gaps opening within this many months (default 18)"},
)
async def funding_cliff_scan(
    *, session: AsyncSession, principal: Principal, within_months: int = 18
) -> list[dict]:
    from app.modules.funding.models import FundingArrangement
    from app.modules.person.models import Person
    from app.modules.student_record.constants import StudentStatus
    from app.modules.student_record.models import Student

    try:
        horizon_months = max(1, min(int(within_months), 60))
    except (TypeError, ValueError):
        horizon_months = 18
    horizon = date.today() + timedelta(days=horizon_months * 31)

    rows = (
        await session.execute(
            select(Student, Person)
            .join(Person, Person.id == Student.person_id)
            .where(Student.status == StudentStatus.active)
        )
    ).all()
    if not rows:
        return []

    ends = dict(
        (
            await session.execute(
                select(FundingArrangement.student_id, func.max(FundingArrangement.valid_to))
                .where(FundingArrangement.student_id.in_([s.id for s, _ in rows]))
                .group_by(FundingArrangement.student_id)
            )
        ).all()
    )

    out: list[dict] = []
    for student, person in rows:
        funding_ends = ends.get(student.id)
        if not funding_ends or not student.expected_end_date:
            continue
        if funding_ends > horizon:
            continue
        gap = _months_between(funding_ends, student.expected_end_date)
        if not gap or gap <= 0:
            continue
        out.append(
            {
                "student_id": str(student.id),
                "name": f"{person.given_name} {person.family_name}",
                "student_ref": student.student_ref,
                "funding_ends_on": funding_ends.isoformat(),
                "expected_end_date": student.expected_end_date.isoformat(),
                "gap_months": gap,
            }
        )

    out.sort(key=lambda r: r["gap_months"], reverse=True)
    return out[:60]


@data_function(
    name="supervisor_load",
    description=(
        "Every supervisor with a current caseload: how many students they supervise, their "
        "configured cap, and how far over or under it they are."
    ),
    permission="student.read",
    params={},
)
async def supervisor_load(*, session: AsyncSession, principal: Principal) -> list[dict]:
    from app.modules.person.models import Person
    from app.modules.supervision.models import SupervisorRelationship
    from app.modules.supervision.w2_models import SupervisorProfile
    from app.modules.supervision.workforce_lens import CURRENT_STATUSES

    counts = dict(
        (
            await session.execute(
                select(
                    SupervisorRelationship.supervisor_person_id,
                    func.count(SupervisorRelationship.id),
                )
                .where(SupervisorRelationship.valid_to.is_(None))
                .where(SupervisorRelationship.status.in_(CURRENT_STATUSES))
                .group_by(SupervisorRelationship.supervisor_person_id)
            )
        ).all()
    )
    if not counts:
        return []

    caps = dict(
        (
            await session.execute(
                select(SupervisorProfile.person_id, SupervisorProfile.max_students)
            )
        ).all()
    )
    people = dict(
        (
            await session.execute(
                select(Person.id, func.concat(Person.given_name, " ", Person.family_name))
                .where(Person.id.in_(list(counts)))
            )
        ).all()
    )

    out = []
    for person_id, load in counts.items():
        cap = caps.get(person_id)
        out.append(
            {
                "name": people.get(person_id, "Unknown"),
                "current_load": int(load),
                "cap": int(cap) if cap else None,
                "over_by": (int(load) - int(cap)) if cap and load > cap else 0,
            }
        )
    out.sort(key=lambda r: (-r["over_by"], -r["current_load"]))
    return out


# Registry population — imported last so `data_function` exists by the time the second
# tranche is loaded. Importing either module yields the whole catalogue.
from app.modules.composer import functions_more  # noqa: E402,F401
