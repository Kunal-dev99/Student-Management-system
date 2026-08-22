"""Aggregates module routers under /api/v1 (arch §5, §11.1)."""
from __future__ import annotations

from fastapi import APIRouter

from app.modules.admissions.router import app_scoped as admissions_app_router
from app.modules.admissions.router import offer_router
from app.modules.identity.router import auth_router, me_router
from app.modules.person.router import router as person_router
from app.modules.recruitment.router import app_router as application_router
from app.modules.recruitment.router import opp_router, pipeline_router
from app.modules.student_record.router import router as student_router
from app.modules.student_record.router import programmes_router
from app.modules.student_record.router import lifecycle_router
from app.modules.supervision.router import student_scoped as supervision_student_router
from app.modules.supervision.router import sup_router
from app.modules.progression.router import (
    milestone_router,
    programme_router,
    student_router as progression_student_router,
)
from app.modules.funding.router import (
    funding_router,
    sources_router,
    student_router as funding_student_router,
)
from app.modules.thesis.router import student_router as thesis_student_router
from app.modules.thesis.router import thesis_router, nomination_router
from app.modules.completion.router import router as completion_router
from app.modules.reporting.router import router as reporting_router
from app.modules.reporting.router import reports_router
from app.modules.workflow.router import (
    definitions_router,
    instances_router,
    notifications_router,
    tasks_router,
)
from app.modules.integration.router import router as integration_router
from app.modules.scheduler.router import router as scheduler_router
from app.modules.portal.router import router as portal_router
from app.modules.exports.router import router as exports_router
from app.modules.exports.router import profiles_router as report_profiles_router
from app.modules.documents.router import router as documents_router
from app.modules.notifications.router import router as notification_prefs_router
from app.modules.audit.router import router as audit_router
from app.modules.assistant.router import router as assistant_router
from app.modules.identity.admin_router import admin_router
from app.modules.pattern_lab.router import router as pattern_lab_router
from app.modules.settings.router import reference_router, settings_router
from app.modules.research.router import (
    areas_router,
    awards_router,
    demand_router,
    lineage_router,
    matching_router,
)

api_router = APIRouter()

# Identity / auth
api_router.include_router(auth_router)
api_router.include_router(me_router)

# Person
api_router.include_router(person_router)

# Recruitment
api_router.include_router(opp_router)
api_router.include_router(application_router)
api_router.include_router(pipeline_router)

# Admissions (offer creation hangs off /applications; offer actions under /offers)
api_router.include_router(admissions_app_router)
api_router.include_router(offer_router)

# Student record
api_router.include_router(student_router)
api_router.include_router(programmes_router)
api_router.include_router(lifecycle_router)

# Supervision
api_router.include_router(supervision_student_router)
api_router.include_router(sup_router)

# Progression
api_router.include_router(programme_router)
api_router.include_router(progression_student_router)
api_router.include_router(milestone_router)

# Funding
api_router.include_router(sources_router)
api_router.include_router(funding_student_router)
api_router.include_router(funding_router)

# Thesis and examination
api_router.include_router(thesis_student_router)
api_router.include_router(thesis_router)
api_router.include_router(nomination_router)

# Completion and graduation
api_router.include_router(completion_router)

# Reporting / dashboards + analytics (Phase 3)
api_router.include_router(reporting_router)
api_router.include_router(reports_router)

# Workflow — tasks, notifications, configurable definitions
api_router.include_router(tasks_router)
api_router.include_router(notifications_router)
api_router.include_router(definitions_router)
api_router.include_router(instances_router)

# Integration hub — dispatcher, logs, webhooks
api_router.include_router(integration_router)

# Scheduler — periodic jobs (worker stand-in)
api_router.include_router(scheduler_router)

# Student portal
api_router.include_router(portal_router)

# Exports (statutory)
api_router.include_router(exports_router)
api_router.include_router(report_profiles_router)

# Phase 4A — documents, notification preferences, audit trail
api_router.include_router(documents_router)
api_router.include_router(notification_prefs_router)
api_router.include_router(audit_router)

# Phase 5 — "Ask PGR" assistant (read-only, admin pilot)
api_router.include_router(assistant_router)

# Phase 6.1 — research context: awards, demand, and position lineage
api_router.include_router(awards_router)
api_router.include_router(demand_router)
api_router.include_router(lineage_router)
api_router.include_router(matching_router)
api_router.include_router(areas_router)
api_router.include_router(settings_router)
api_router.include_router(reference_router)
api_router.include_router(admin_router)
api_router.include_router(pattern_lab_router)
