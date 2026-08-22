"""Assistant tools (Phase 5.1 — all read-only).

Every tool is a thin wrapper over an existing service and is executed **as the signed-in user**:
the caller's `Principal` determines row scope via `student_scope`, exactly as the REST routers do.
The assistant therefore inherits all Phase 1–4 authorization for free and can never see more than
the human could.

Tool results are returned to the model wrapped as untrusted DATA (see service.py) — record content
is never treated as an instruction.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import student_scope
from app.core.principal import Principal
from app.modules.assistant.cohort import CohortQuery
from app.modules.assistant.constants import MAX_TOOL_ROWS
from app.modules.assistant.resolver import Resolver

# Routes the assistant may deep-link to (used by `navigate`).
NAV_TARGETS = {
    "dashboard": "/dashboard", "analytics": "/analytics", "students": "/students",
    "persons": "/persons", "recruitment": "/recruitment", "admissions": "/admissions",
    "supervision": "/supervision", "progression": "/progression", "funding": "/funding",
    "thesis": "/thesis", "completion": "/completion", "tasks": "/tasks",
    "workflows": "/workflows", "integration": "/integration", "audit": "/audit",
    "settings": "/settings", "portal": "/portal",
}


async def _allowed_ids(principal: Principal, session: AsyncSession) -> list[uuid.UUID] | None:
    """Row scope for this principal (None = unrestricted). Mirrors student_record.router."""
    from app.modules.student_record.router import scoped_ids

    return await scoped_ids(principal, session)


# --------------------------------------------------------------------------------------
# Tool schemas advertised to the model. Kept deliberately small: fewer, better-chosen tools
# produce better tool selection than a wrapper around all 124 endpoints.
# --------------------------------------------------------------------------------------
TOOL_SCHEMAS: list[dict] = [
    {
        "name": "find_student",
        "description": "Find students by name or student reference. ALWAYS use this to resolve a person before any other student tool — never invent an id.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Name or student ref, e.g. 'Marcus' or 'PGR-2026-1586FA'"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_student_overview",
        "description": "Full cross-module picture of one student: status, supervisors, funding, milestones, thesis, supervision-meeting compliance. Use after find_student.",
        "input_schema": {
            "type": "object",
            "properties": {"studentId": {"type": "string", "description": "studentId from find_student"}},
            "required": ["studentId"],
        },
    },
    {
        "name": "cohort_query",
        "description": (
            "Find the set of students matching a combination of conditions. This answers questions the UI has no screen for, "
            "e.g. 'students with no supervision meeting in 90 days and funding expiring this year'. Filters combine with AND. "
            "Each result explains why it matched."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["registered", "active", "completed", "withdrawn", "suspended"]},
                "programme": {"type": "string", "description": "Programme name, partial match"},
                "supervisorName": {"type": "string", "description": "Supervisor name, partial match"},
                "noSupervisionMeetingInDays": {"type": "integer", "description": "Students with no recorded supervision meeting in this many days"},
                "fundingExpiringWithinDays": {"type": "integer", "description": "Students whose active funding ends within this many days"},
                "noActiveFunding": {"type": "boolean", "description": "Students with no current funding arrangement"},
                "milestoneOverdue": {"type": "boolean", "description": "Students with a milestone past its due date and not yet decided"},
                "thesisStatus": {"type": "string", "description": "e.g. submitted, under_examination, corrections, approved"},
            },
        },
    },
    {
        "name": "get_analytics",
        "description": "Institution-level analytics: at-risk students with reasons, completion rate, and forecast.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_enterprise_360",
        "description": "PGR Enterprise 360 summary across five lenses (student, research, funding, workforce, statutory) for the whole population.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_my_tasks",
        "description": "The signed-in user's own open task queue.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "navigate",
        "description": "Produce a deep link into the app. Use for 'take me to X' requests, and whenever the user should complete an action on a form.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": f"One of: {', '.join(sorted(NAV_TARGETS))}, or a studentId for that student's record"},
            },
            "required": ["target"],
        },
    },
]


class ToolBox:
    """Executes tools with the caller's identity and scope."""

    def __init__(self, session: AsyncSession, principal: Principal) -> None:
        self.session = session
        self.principal = principal

    async def execute(self, name: str, args: dict) -> dict:
        fn = getattr(self, f"_t_{name}", None)
        if fn is None:
            return {"error": f"Unknown tool '{name}'"}
        try:
            return await fn(args or {})
        except Exception as exc:  # tool errors are data for the model, never crashes
            return {"error": f"{type(exc).__name__}: {exc}"}

    # --- tools ---

    async def _t_find_student(self, args: dict) -> dict:
        allowed = await _allowed_ids(self.principal, self.session)
        candidates = await Resolver(self.session).find_students(args.get("query", ""), allowed_ids=allowed)
        return {"candidates": candidates, "count": len(candidates)}

    async def _t_get_student_overview(self, args: dict) -> dict:
        from app.modules.student_record.repository import StudentRepository
        from app.modules.student_record.service import StudentService
        from app.modules.supervision.repository import SupervisionRepository
        from app.modules.supervision.service import SupervisionService
        from app.modules.progression.repository import ProgressionRepository
        from app.modules.progression.service import ProgressionService
        from app.modules.thesis.repository import ThesisRepository
        from app.modules.thesis.service import ThesisService

        sid = uuid.UUID(args["studentId"])
        allowed = await _allowed_ids(self.principal, self.session)
        summary = await StudentService(StudentRepository(self.session)).summary(sid, allowed_ids=allowed)
        sup = SupervisionService(SupervisionRepository(self.session))
        milestones = await ProgressionService(ProgressionRepository(self.session)).list_milestones(
            sid, allowed_ids=allowed
        )
        thesis = await ThesisService(ThesisRepository(self.session)).get_for_student(sid, allowed_ids=allowed)
        return {
            "student": {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in summary.items()},
            "supervisionCompliance": await sup.meeting_compliance(sid),
            "recentMeetings": (await sup.meetings_for_student(sid))[:5],
            "milestones": milestones[:MAX_TOOL_ROWS] if milestones else [],
            "thesis": {
                "status": thesis.status.value, "title": thesis.title,
                "submittedAt": thesis.submitted_at.isoformat() if thesis.submitted_at else None,
            } if thesis else None,
            "link": f"/students/{sid}",
        }

    async def _t_cohort_query(self, args: dict) -> dict:
        allowed = await _allowed_ids(self.principal, self.session)
        return await CohortQuery(self.session).run(
            allowed_ids=allowed,
            status=args.get("status"),
            programme=args.get("programme"),
            supervisor_name=args.get("supervisorName"),
            no_supervision_meeting_in_days=args.get("noSupervisionMeetingInDays"),
            funding_expiring_within_days=args.get("fundingExpiringWithinDays"),
            no_active_funding=bool(args.get("noActiveFunding")),
            milestone_overdue=bool(args.get("milestoneOverdue")),
            thesis_status=args.get("thesisStatus"),
            limit=MAX_TOOL_ROWS,
        )

    async def _t_get_analytics(self, args: dict) -> dict:
        from app.modules.reporting.analytics import AnalyticsService

        return await AnalyticsService(self.session).analytics()

    async def _t_get_enterprise_360(self, args: dict) -> dict:
        from app.modules.reporting.analytics import AnalyticsService

        data = await AnalyticsService(self.session).enterprise_360()
        # Summary + lens names only; the full population would blow the context budget.
        return {"summary": data["summary"], "lenses": data["lenses"], "populationSize": len(data["population"])}

    async def _t_list_my_tasks(self, args: dict) -> dict:
        from app.modules.workflow.repository import WorkflowRepository
        from app.modules.workflow.service import WorkflowService

        rows = await WorkflowService(WorkflowRepository(self.session)).my_tasks(self.principal)
        return {
            "tasks": [
                {"id": str(t.id), "title": t.title,
                 "status": t.status.value if hasattr(t.status, "value") else t.status,
                 "dueAt": t.due_at.isoformat() if t.due_at else None}
                for t in rows[:MAX_TOOL_ROWS]
            ],
            "link": "/tasks",
        }

    async def _t_navigate(self, args: dict) -> dict:
        target = (args.get("target") or "").strip().lower()
        if target in NAV_TARGETS:
            return {"link": NAV_TARGETS[target], "label": target}
        try:
            sid = uuid.UUID(target)
            return {"link": f"/students/{sid}", "label": "student record"}
        except ValueError:
            return {"error": f"Unknown navigation target '{target}'", "known": sorted(NAV_TARGETS)}
