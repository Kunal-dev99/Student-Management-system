"""Second tranche of data functions — thesis, attention lists, trends, recruitment, people.

Split from `functions.py` purely for size; the registry is shared and there is no
behavioural difference between the two files. `functions.py` imports this at the bottom so
that importing either one populates the whole catalogue.

Grouped by the question they answer rather than by the module they read from, because that
is how the model reasons about them.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal
from app.modules.composer.functions import _as_uuid, _student_row, data_function


# -------------------------------------------------------------------------------- thesis


@data_function(
    name="student_thesis",
    description=(
        "One student's thesis: status, title, submission date, nominated examiners with "
        "conflict-of-interest flags, viva date and format, examination outcome, and any "
        "outstanding corrections with their deadlines."
    ),
    permission="student.read",
    params={"student_id": "id from search_student"},
)
async def student_thesis(*, session: AsyncSession, principal: Principal, student_id: str) -> dict:
    from app.modules.person.models import Person
    from app.modules.thesis.models import (
        Examination, ExaminerNomination, Thesis, ThesisCorrection,
    )

    sid = _as_uuid(student_id, "student_id")
    thesis = (await session.execute(
        select(Thesis).where(Thesis.student_id == sid)
    )).scalar_one_or_none()
    if thesis is None:
        return {"status": "not started", "examiners": [], "corrections": []}

    examination = (await session.execute(
        select(Examination).where(Examination.thesis_id == thesis.id)
    )).scalar_one_or_none()
    examiners = (await session.execute(
        select(ExaminerNomination, Person)
        .join(Person, Person.id == ExaminerNomination.examiner_person_id)
        .where(ExaminerNomination.thesis_id == thesis.id)
    )).all()
    corrections = (await session.execute(
        select(ThesisCorrection).where(ThesisCorrection.thesis_id == thesis.id)
    )).scalars().all()

    today = date.today()
    return {
        "status": getattr(thesis.status, "value", str(thesis.status)),
        "title": thesis.title,
        "submitted_on": thesis.submitted_at.date().isoformat() if thesis.submitted_at else None,
        "days_since_submission": (
            (today - thesis.submitted_at.date()).days if thesis.submitted_at else None
        ),
        "viva_date": (
            examination.viva_date.isoformat() if examination and examination.viva_date else None
        ),
        "viva_format": (
            getattr(examination.viva_format, "value", None)
            if examination and examination.viva_format else None
        ),
        "outcome": (
            getattr(examination.outcome, "value", None)
            if examination and examination.outcome else None
        ),
        "examiners": [
            {
                "name": f"{p.given_name} {p.family_name}",
                "type": getattr(n.examiner_type, "value", str(n.examiner_type)),
                "affiliation": n.affiliation,
                "approved": bool(n.approved),
                "conflict_of_interest": bool(n.conflict_of_interest),
            }
            for n, p in examiners
        ],
        "corrections": [
            {
                "kind": getattr(c.kind, "value", str(c.kind)),
                "deadline": c.deadline.isoformat() if c.deadline else None,
                "days_remaining": (c.deadline - today).days if c.deadline else None,
                "submitted": c.submitted_at is not None,
                "signed_off": c.approved_at is not None,
            }
            for c in corrections
        ],
    }


@data_function(
    name="thesis_pipeline",
    description=(
        "How many theses sit at each stage across the institution — preparation, intention "
        "to submit, submitted, under examination, corrections, approved, failed. The "
        "cohort-level view of where work is stuck."
    ),
    permission="student.read",
    params={},
)
async def thesis_pipeline(*, session: AsyncSession, principal: Principal) -> dict:
    from app.modules.thesis.models import Thesis

    rows = (await session.execute(
        select(Thesis.status, func.count(Thesis.id)).group_by(Thesis.status)
    )).all()
    by_stage = {getattr(s, "value", str(s)): int(n) for s, n in rows}
    return {"by_stage": by_stage, "total": sum(by_stage.values())}


@data_function(
    name="upcoming_vivas",
    description=(
        "Vivas scheduled within the next N days, soonest first, with the student, date, "
        "format, location and whether an approved examiner is in place."
    ),
    permission="student.read",
    params={"within_days": "how far ahead to look (default 90)"},
)
async def upcoming_vivas(
    *, session: AsyncSession, principal: Principal, within_days: int = 90
) -> list[dict]:
    from app.modules.person.models import Person
    from app.modules.student_record.models import Student
    from app.modules.thesis.models import Examination, ExaminerNomination, Thesis

    try:
        window = max(1, min(int(within_days), 365))
    except (TypeError, ValueError):
        window = 90
    today = date.today()

    rows = (await session.execute(
        select(Examination, Thesis, Student, Person)
        .join(Thesis, Thesis.id == Examination.thesis_id)
        .join(Student, Student.id == Thesis.student_id)
        .join(Person, Person.id == Student.person_id)
        .where(Examination.viva_date.is_not(None))
        .where(Examination.viva_date >= today)
        .where(Examination.viva_date <= today + timedelta(days=window))
        .order_by(Examination.viva_date)
        .limit(60)
    )).all()
    if not rows:
        return []

    approved = {
        tid for (tid,) in (await session.execute(
            select(ExaminerNomination.thesis_id)
            .where(ExaminerNomination.thesis_id.in_([t.id for _e, t, _s, _p in rows]))
            .where(ExaminerNomination.approved.is_(True))
        )).all()
    }

    return [
        {
            "student_id": str(s.id),
            "name": f"{p.given_name} {p.family_name}",
            "student_ref": s.student_ref,
            "viva_date": e.viva_date.isoformat(),
            "days_away": (e.viva_date - today).days,
            "format": getattr(e.viva_format, "value", None) if e.viva_format else None,
            "location": e.viva_location,
            "examiner_approved": t.id in approved,
        }
        for e, t, s, p in rows
    ]


# ------------------------------------------------------------------ who needs attention


@data_function(
    name="overdue_milestones",
    description=(
        "Students with milestones past their due date and not yet decided, worst overdue "
        "first. The core 'who is behind' question."
    ),
    permission="progression.read",
    params={"min_days_overdue": "only include milestones at least this overdue (default 1)"},
)
async def overdue_milestones(
    *, session: AsyncSession, principal: Principal, min_days_overdue: int = 1
) -> list[dict]:
    from app.modules.person.models import Person
    from app.modules.progression.models import Milestone, MilestoneDefinition
    from app.modules.student_record.models import Student

    try:
        threshold = max(0, int(min_days_overdue))
    except (TypeError, ValueError):
        threshold = 1
    today = date.today()

    rows = (await session.execute(
        select(Milestone, MilestoneDefinition.name, Student, Person)
        .join(MilestoneDefinition, MilestoneDefinition.id == Milestone.milestone_definition_id)
        .join(Student, Student.id == Milestone.student_id)
        .join(Person, Person.id == Student.person_id)
        .where(Milestone.due_date.is_not(None))
        .where(Milestone.due_date <= today - timedelta(days=threshold))
        .order_by(Milestone.due_date)
        .limit(120)
    )).all()

    # "Decided" covers passed and waived outcomes; only open milestones are overdue.
    settled = {"decided", "passed", "waived"}
    out = [
        {
            "student_id": str(student.id),
            "name": f"{person.given_name} {person.family_name}",
            "student_ref": student.student_ref,
            "milestone": name,
            "due_date": milestone.due_date.isoformat(),
            "days_overdue": (today - milestone.due_date).days,
            "status": getattr(milestone.status, "value", str(milestone.status)),
        }
        for milestone, name, student, person in rows
        if getattr(milestone.status, "value", str(milestone.status)) not in settled
    ]
    out.sort(key=lambda r: r["days_overdue"], reverse=True)
    return out[:50]


@data_function(
    name="supervision_compliance",
    description=(
        "Active students whose last supervision meeting is older than the expected "
        "interval, or who have never been seen at all. Never-met first, then longest gap. "
        "Students with no current supervisor are flagged."
    ),
    permission="student.read",
    params={"min_days_since": "gap threshold in days (default 90)"},
)
async def supervision_compliance(
    *, session: AsyncSession, principal: Principal, min_days_since: int = 90
) -> list[dict]:
    from app.modules.person.models import Person
    from app.modules.student_record.constants import StudentStatus
    from app.modules.student_record.models import Student
    from app.modules.supervision.models import SupervisionMeeting, SupervisorRelationship

    try:
        threshold = max(1, int(min_days_since))
    except (TypeError, ValueError):
        threshold = 90
    today = date.today()

    students = (await session.execute(
        select(Student, Person)
        .join(Person, Person.id == Student.person_id)
        .where(Student.status == StudentStatus.active)
    )).all()
    if not students:
        return []

    ids = [s.id for s, _ in students]
    last_meeting = dict((await session.execute(
        select(SupervisionMeeting.student_id, func.max(SupervisionMeeting.met_on))
        .where(SupervisionMeeting.student_id.in_(ids))
        .group_by(SupervisionMeeting.student_id)
    )).all())
    supervised = {
        sid for (sid,) in (await session.execute(
            select(SupervisorRelationship.student_id)
            .where(SupervisorRelationship.student_id.in_(ids))
            .where(SupervisorRelationship.valid_to.is_(None))
        )).all()
    }

    out = []
    for student, person in students:
        last = last_meeting.get(student.id)
        gap = (today - last).days if last else None
        if last is not None and gap < threshold:
            continue
        out.append({
            "student_id": str(student.id),
            "name": f"{person.given_name} {person.family_name}",
            "student_ref": student.student_ref,
            "last_meeting_on": last.isoformat() if last else None,
            "days_since_last_meeting": gap,
            "never_met": last is None,
            "has_supervisor": student.id in supervised,
        })
    out.sort(key=lambda r: (not r["never_met"], -(r["days_since_last_meeting"] or 0)))
    return out[:50]


# ---------------------------------------------------------------------------- over time


async def _monthly_counts(session: AsyncSession, column, months: int, *, label: str) -> list[dict]:
    """Shared month bucketing.

    Months with no activity are emitted as zero rather than omitted — a gap in a line chart
    reads as missing data, when what actually happened is that nothing happened.
    """
    try:
        window = max(1, min(int(months), 60))
    except (TypeError, ValueError):
        window = 24

    today = date.today()
    start = date(today.year, today.month, 1)
    for _ in range(window - 1):
        start = (
            date(start.year - 1, 12, 1) if start.month == 1
            else date(start.year, start.month - 1, 1)
        )

    rows = (await session.execute(
        select(column, func.count())
        .where(column.is_not(None))
        .where(column >= start)
        .group_by(column)
    )).all()

    buckets: dict[str, int] = {}
    cursor = start
    while cursor <= today:
        buckets[cursor.strftime("%Y-%m")] = 0
        cursor = (
            date(cursor.year + 1, 1, 1) if cursor.month == 12
            else date(cursor.year, cursor.month + 1, 1)
        )

    for when, count in rows:
        if when is None:
            continue
        key = when.strftime("%Y-%m")
        if key in buckets:
            buckets[key] += int(count)

    return [{"month": k, label: v} for k, v in sorted(buckets.items())]


@data_function(
    name="completion_trend",
    description=(
        "Graduations per month over the last N months, oldest first. A time series — draw "
        "it as a line_chart."
    ),
    permission="student.read",
    params={"months": "how many months back (default 24)"},
)
async def completion_trend(
    *, session: AsyncSession, principal: Principal, months: int = 24
) -> list[dict]:
    from app.modules.completion.models import Completion

    return await _monthly_counts(session, Completion.graduation_date, months, label="graduations")


@data_function(
    name="intake_trend",
    description=(
        "New student registrations per month over the last N months, oldest first. A time "
        "series — draw it as a line_chart. Pair with completion_trend to compare intake "
        "against output."
    ),
    permission="student.read",
    params={"months": "how many months back (default 24)"},
)
async def intake_trend(
    *, session: AsyncSession, principal: Principal, months: int = 24
) -> list[dict]:
    from app.modules.student_record.models import Student

    return await _monthly_counts(session, Student.start_date, months, label="registrations")


# --------------------------------------------------------------------------- recruitment


@data_function(
    name="application_pipeline",
    description=(
        "Applications at each recruitment stage, and split by route (opportunity-led vs "
        "student-led). The admissions funnel."
    ),
    permission="recruitment.read",
    params={},
)
async def application_pipeline(*, session: AsyncSession, principal: Principal) -> dict:
    from app.modules.recruitment.models import Application

    rows = (await session.execute(
        select(Application.current_stage, Application.route, func.count(Application.id))
        .group_by(Application.current_stage, Application.route)
    )).all()

    by_stage: dict[str, int] = {}
    by_route: dict[str, int] = {}
    for stage, route, count in rows:
        s = getattr(stage, "value", str(stage))
        r = getattr(route, "value", str(route))
        by_stage[s] = by_stage.get(s, 0) + int(count)
        by_route[r] = by_route.get(r, 0) + int(count)

    return {"by_stage": by_stage, "by_route": by_route, "total": sum(by_stage.values())}


@data_function(
    name="applications_needing_action",
    description=(
        "Live applications that are blocked or stalled: visa-required with no completed "
        "visa check, or open with no movement for a long time. Longest open first."
    ),
    permission="recruitment.read",
    params={"stale_after_days": "treat as stalled after this many days open (default 30)"},
)
async def applications_needing_action(
    *, session: AsyncSession, principal: Principal, stale_after_days: int = 30
) -> list[dict]:
    from app.modules.person.models import Person
    from app.modules.recruitment.constants import TERMINAL_STAGES
    from app.modules.recruitment.models import Application

    try:
        stale_days = max(1, int(stale_after_days))
    except (TypeError, ValueError):
        stale_days = 30
    today = date.today()

    rows = (await session.execute(
        select(Application, Person)
        .join(Person, Person.id == Application.person_id)
        .order_by(Application.submitted_at)
        .limit(150)
    )).all()

    out = []
    for application, person in rows:
        if application.current_stage in TERMINAL_STAGES:
            continue
        submitted = application.submitted_at.date() if application.submitted_at else None
        age = (today - submitted).days if submitted else None
        visa_blocked = application.visa_required and application.visa_check_completed_at is None
        if not visa_blocked and (age is None or age < stale_days):
            continue

        reasons = []
        if visa_blocked:
            reasons.append("visa check outstanding")
        if age is not None and age >= stale_days:
            reasons.append(f"open {age} days")

        out.append({
            "application_id": str(application.id),
            "name": f"{person.given_name} {person.family_name}",
            "stage": getattr(application.current_stage, "value", str(application.current_stage)),
            "route": getattr(application.route, "value", str(application.route)),
            "submitted_on": submitted.isoformat() if submitted else None,
            "days_open": age,
            "blocked_on": ", ".join(reasons),
        })
    out.sort(key=lambda r: r["days_open"] or 0, reverse=True)
    return out[:40]


# ---------------------------------------------------------------------------- completion


@data_function(
    name="completion_pipeline",
    description=(
        "Where students sit in the completion process — requirements met, award confirmed, "
        "graduated — plus a breakdown of the award classifications conferred."
    ),
    permission="student.read",
    params={},
)
async def completion_pipeline(*, session: AsyncSession, principal: Principal) -> dict:
    from app.modules.completion.models import Award, Completion

    status_rows = (await session.execute(
        select(Completion.status, func.count(Completion.id)).group_by(Completion.status)
    )).all()
    class_rows = (await session.execute(
        select(Award.classification, func.count(Award.id))
        .where(Award.classification.is_not(None))
        .group_by(Award.classification)
    )).all()

    by_status = {getattr(s, "value", str(s)): int(n) for s, n in status_rows}
    return {
        "by_status": by_status,
        "by_classification": {c: int(n) for c, n in class_rows},
        "total": sum(by_status.values()),
    }


# ---------------------------------------------------------- shape-specific breakdowns
#
# The composer's donut, heatmap and gauge blocks expect payloads shaped exactly for them.
# These small functions do the reshaping deterministically, so the model just picks the
# block and passes the data through — no inventing rows or columns.


@data_function(
    name="funding_type_breakdown",
    description=(
        "Active students grouped by funding type — research council, university "
        "scholarship, employer, self-funded, etc. Returns {slices:[{label,value}]} ready "
        "for a donut or pie block."
    ),
    permission="funding.read",
    params={},
)
async def funding_type_breakdown(*, session: AsyncSession, principal: Principal) -> dict:
    from app.modules.funding.models import FundingArrangement, FundingStatus
    from app.modules.student_record.constants import StudentStatus
    from app.modules.student_record.models import Student

    rows = (await session.execute(
        select(FundingArrangement.funding_type, func.count(func.distinct(Student.id)))
        .join(Student, Student.id == FundingArrangement.student_id)
        .where(Student.status == StudentStatus.active)
        .where(FundingArrangement.status == FundingStatus.active)
        .group_by(FundingArrangement.funding_type)
    )).all()

    slices = [
        {"label": getattr(t, "value", str(t)).replace("_", " "), "value": int(n)}
        for t, n in rows
    ]
    slices.sort(key=lambda s: s["value"], reverse=True)
    return {"slices": slices, "total": sum(s["value"] for s in slices)}


@data_function(
    name="overdue_milestones_heatmap",
    description=(
        "Overdue milestones reshaped as a heatmap: rows are students, columns are "
        "milestone types, cells are days overdue. Returns "
        "{rows:[str], columns:[str], cells:[{row,column,value}]} — pass straight into a "
        "heatmap block."
    ),
    permission="progression.read",
    params={},
)
async def overdue_milestones_heatmap(
    *, session: AsyncSession, principal: Principal
) -> dict:
    from app.modules.person.models import Person
    from app.modules.progression.models import Milestone, MilestoneDefinition
    from app.modules.student_record.models import Student

    today = date.today()
    rows_result = (await session.execute(
        select(Milestone, MilestoneDefinition.name, Student, Person)
        .join(MilestoneDefinition, MilestoneDefinition.id == Milestone.milestone_definition_id)
        .join(Student, Student.id == Milestone.student_id)
        .join(Person, Person.id == Student.person_id)
        .where(Milestone.due_date.is_not(None))
        .where(Milestone.due_date <= today)
        .limit(200)
    )).all()

    settled = {"decided", "passed", "waived"}
    student_names: list[str] = []
    milestone_types: list[str] = []
    cells: list[dict] = []
    for milestone, name, student, person in rows_result:
        status = getattr(milestone.status, "value", str(milestone.status))
        if status in settled:
            continue
        who = f"{person.given_name} {person.family_name}"
        if who not in student_names:
            student_names.append(who)
        if name not in milestone_types:
            milestone_types.append(name)
        cells.append({
            "row": who, "column": name,
            "value": (today - milestone.due_date).days,
        })
    return {
        "rows": student_names[:12], "columns": milestone_types[:8], "cells": cells,
    }


@data_function(
    name="completion_gauge_data",
    description=(
        "Completion progress as a gauge payload: {value, maximum, target}. Value is the "
        "count of students who have graduated; maximum is the total student population; "
        "target defaults to 90% of maximum. Pass straight into a gauge block."
    ),
    permission="student.read",
    params={},
)
async def completion_gauge_data(*, session: AsyncSession, principal: Principal) -> dict:
    from app.modules.student_record.constants import StudentStatus
    from app.modules.student_record.models import Student

    total = (await session.execute(
        select(func.count(Student.id))
    )).scalar_one() or 0
    # `completed` is the terminal successful state — the enum has no `graduated` value.
    completed = (await session.execute(
        select(func.count(Student.id)).where(Student.status == StudentStatus.completed)
    )).scalar_one() or 0

    return {
        "value": int(completed),
        "maximum": int(total),
        "target": int(round(total * 0.9)),
        "unit": "number",
    }


# -------------------------------------------------------------------------------- people


@data_function(
    name="search_person",
    description=(
        "Find any person by name or email — supervisors, examiners, staff, applicants. Use "
        "this rather than search_student when the person may not be a student."
    ),
    permission="person.read",
    params={"query": "part of a name or email address"},
)
async def search_person(*, session: AsyncSession, principal: Principal, query: str) -> list[dict]:
    from app.modules.person.models import Person

    cleaned = str(query).lower().strip()
    if not cleaned:
        return []

    full_name = func.lower(Person.given_name + " " + Person.family_name)
    condition = full_name.like(f"%{cleaned}%") | func.lower(Person.email).like(f"%{cleaned}%")
    for token in cleaned.split():
        condition = condition | (
            func.lower(Person.given_name).like(f"%{token}%")
            | func.lower(Person.family_name).like(f"%{token}%")
        )

    rows = (await session.execute(
        select(Person).where(condition)
        .order_by((full_name == cleaned).desc(), Person.family_name)
        .limit(10)
    )).scalars().all()
    return [
        {"person_id": str(p.id), "name": f"{p.given_name} {p.family_name}", "email": p.email}
        for p in rows
    ]


# ---------------------------------------------------------------- graph-shaped helpers
#
# The composer's `tree` and `roadmap` blocks need nodes/edges and ordered steps. Asking
# the model to construct those from flat function results works but fails inconsistently.
# These functions return the shape the block wants — so the model's job shrinks to
# "draw this as a tree" instead of "invent the graph structure from these rows".


@data_function(
    name="funding_lineage_graph",
    description=(
        "One student's funding chain as a ready-to-render tree — nodes for the student, "
        "each arrangement, the funding source, the research award and the funder, with "
        "directed edges linking source to consumer. Use with the `tree` block. Return "
        "shape: {nodes:[{id,label,group,detail}], edges:[{source,target,label}]}."
    ),
    permission="funding.read",
    params={"student_id": "id from search_student"},
)
async def funding_lineage_graph(
    *, session: AsyncSession, principal: Principal, student_id: str
) -> dict:
    from app.modules.funding.models import FundingArrangement, FundingSource
    from app.modules.research.models import ResearchAward

    sid = _as_uuid(student_id, "student_id")
    student, person = await _student_row(session, sid)
    arrangements = (await session.execute(
        select(FundingArrangement).where(FundingArrangement.student_id == sid)
    )).scalars().all()

    if not arrangements:
        return {"nodes": [], "edges": []}

    source_ids = [a.funding_source_id for a in arrangements if a.funding_source_id]
    award_ids = [a.research_award_id for a in arrangements if a.research_award_id]

    sources = dict((s.id, s) for s in (await session.execute(
        select(FundingSource).where(FundingSource.id.in_(source_ids)) if source_ids
        else select(FundingSource).where(False)
    )).scalars().all()) if source_ids else {}
    awards = dict((a.id, a) for a in (await session.execute(
        select(ResearchAward).where(ResearchAward.id.in_(award_ids)) if award_ids
        else select(ResearchAward).where(False)
    )).scalars().all()) if award_ids else {}

    nodes: list[dict] = [{
        "id": f"student:{student.id}",
        "label": f"{person.given_name} {person.family_name}",
        "group": "student",
        "detail": student.student_ref,
    }]
    edges: list[dict] = []
    seen: set[str] = {nodes[0]["id"]}

    for a in arrangements:
        arr_id = f"arrangement:{a.id}"
        nodes.append({
            "id": arr_id,
            "label": getattr(a.funding_type, "value", str(a.funding_type)),
            "group": "arrangement",
            "detail": (
                f"£{a.stipend_amount:,.0f}" if a.stipend_amount else
                getattr(a.status, "value", str(a.status))
            ),
        })
        seen.add(arr_id)
        # Arrangement pays the student — edge from money to consumer.
        edges.append({"source": arr_id, "target": nodes[0]["id"], "label": "funds"})

        if a.funding_source_id and a.funding_source_id in sources:
            src = sources[a.funding_source_id]
            src_id = f"source:{src.id}"
            if src_id not in seen:
                nodes.append({
                    "id": src_id, "label": src.name, "group": "source",
                    "detail": src.funder_type,
                })
                seen.add(src_id)
            edges.append({"source": src_id, "target": arr_id})

        if a.research_award_id and a.research_award_id in awards:
            award = awards[a.research_award_id]
            aw_id = f"award:{award.id}"
            if aw_id not in seen:
                nodes.append({
                    "id": aw_id, "label": award.title[:40], "group": "award",
                    "detail": award.award_ref,
                })
                seen.add(aw_id)
            edges.append({"source": aw_id, "target": arr_id, "label": "under"})

    return {"nodes": nodes, "edges": edges, "layout": "hierarchical", "direction": "right"}


@data_function(
    name="student_journey",
    description=(
        "One student's whole progression as an ordered list of steps — application, "
        "registration, each milestone, viva, graduation. Each step carries a status "
        "(done / current / upcoming / at_risk / missed) and a date. Use with the "
        "`roadmap` block. Return shape: {steps:[{label,status,at,detail}]}."
    ),
    permission="student.read",
    params={"student_id": "id from search_student"},
)
async def student_journey(
    *, session: AsyncSession, principal: Principal, student_id: str
) -> dict:
    from app.modules.completion.models import Completion
    from app.modules.progression.models import Milestone, MilestoneDefinition
    from app.modules.thesis.models import Examination, Thesis

    sid = _as_uuid(student_id, "student_id")
    student, _person = await _student_row(session, sid)

    milestones = (await session.execute(
        select(Milestone, MilestoneDefinition.name)
        .join(MilestoneDefinition, MilestoneDefinition.id == Milestone.milestone_definition_id)
        .where(Milestone.student_id == sid)
        .order_by(Milestone.due_date)
    )).all()
    thesis = (await session.execute(
        select(Thesis).where(Thesis.student_id == sid)
    )).scalar_one_or_none()
    examination = None
    if thesis is not None:
        examination = (await session.execute(
            select(Examination).where(Examination.thesis_id == thesis.id)
        )).scalar_one_or_none()
    completion = (await session.execute(
        select(Completion).where(Completion.student_id == sid)
    )).scalar_one_or_none()

    today = date.today()
    steps: list[dict] = []

    # Registration is always the first anchor.
    steps.append({
        "label": "Registered",
        "status": "done" if student.start_date and student.start_date <= today else "upcoming",
        "at": student.start_date.isoformat() if student.start_date else None,
        "detail": student.student_ref,
    })

    # Milestones in their scheduled order.
    settled = {"decided", "passed", "waived"}
    current_seen = False
    for milestone, name in milestones:
        status_value = getattr(milestone.status, "value", str(milestone.status))
        due = milestone.due_date
        if status_value in settled:
            step_status = "done"
        elif due and due < today:
            step_status = "missed"
        elif not current_seen:
            step_status = "current"
            current_seen = True
        else:
            step_status = "upcoming"
        steps.append({
            "label": name,
            "status": step_status,
            "at": due.isoformat() if due else None,
            "detail": status_value.replace("_", " "),
        })

    # Thesis stages when reached.
    if thesis:
        thesis_status = getattr(thesis.status, "value", str(thesis.status))
        steps.append({
            "label": "Thesis submitted",
            "status": (
                "done" if thesis.submitted_at else
                "current" if thesis_status == "intention_to_submit" else "upcoming"
            ),
            "at": thesis.submitted_at.date().isoformat() if thesis.submitted_at else None,
        })
        if examination and examination.viva_date:
            steps.append({
                "label": "Viva",
                "status": (
                    "done" if examination.outcome else
                    "current" if examination.viva_date <= today else "upcoming"
                ),
                "at": examination.viva_date.isoformat(),
                "detail": getattr(examination.outcome, "value", None) if examination.outcome else None,
            })

    # Graduation caps it.
    grad_status = "upcoming"
    grad_date = None
    if completion:
        if completion.graduation_date:
            grad_status = "done"
            grad_date = completion.graduation_date.isoformat()
        elif getattr(completion.status, "value", None) == "award_confirmed":
            grad_status = "current"
    steps.append({
        "label": "Graduated",
        "status": grad_status,
        "at": grad_date,
        "detail": student.expected_end_date.isoformat() if not grad_date and student.expected_end_date else None,
    })

    return {"steps": steps}


@data_function(
    name="supervisor_caseload",
    description=(
        "The students one supervisor currently supervises, with each student's status, the "
        "supervisory role, and days since their last supervision meeting."
    ),
    permission="student.read",
    params={"person_id": "id from search_person"},
)
async def supervisor_caseload(
    *, session: AsyncSession, principal: Principal, person_id: str
) -> list[dict]:
    from app.modules.person.models import Person
    from app.modules.student_record.models import Student
    from app.modules.supervision.models import SupervisionMeeting, SupervisorRelationship
    from app.modules.supervision.workforce_lens import CURRENT_STATUSES

    pid = _as_uuid(person_id, "person_id")
    rows = (await session.execute(
        select(SupervisorRelationship, Student, Person)
        .join(Student, Student.id == SupervisorRelationship.student_id)
        .join(Person, Person.id == Student.person_id)
        .where(SupervisorRelationship.supervisor_person_id == pid)
        .where(SupervisorRelationship.valid_to.is_(None))
        .where(SupervisorRelationship.status.in_(CURRENT_STATUSES))
    )).all()
    if not rows:
        return []

    today = date.today()
    last_meeting = dict((await session.execute(
        select(SupervisionMeeting.student_id, func.max(SupervisionMeeting.met_on))
        .where(SupervisionMeeting.student_id.in_([s.id for _r, s, _p in rows]))
        .group_by(SupervisionMeeting.student_id)
    )).all())

    return [
        {
            "student_id": str(student.id),
            "name": f"{person.given_name} {person.family_name}",
            "student_ref": student.student_ref,
            "status": getattr(student.status, "value", str(student.status)),
            "role": getattr(rel.role, "value", str(rel.role)),
            "days_since_last_meeting": (
                (today - last_meeting[student.id]).days
                if last_meeting.get(student.id) else None
            ),
        }
        for rel, student, person in rows
    ]
