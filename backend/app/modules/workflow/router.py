"""Workflow HTTP endpoints (arch §11.5 — workflow, tasks, notifications)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

import uuid as _uuid

from app.core.dependencies import get_current_principal, require_permission
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.workflow.definitions_service import WorkflowDefinitionService
from app.modules.workflow.repository import WorkflowRepository
from app.modules.workflow.schemas import (
    EventRequest,
    NotificationOut,
    StartInstanceRequest,
    TaskOut,
    WorkflowDefinitionCreate,
    WorkflowDefinitionOut,
    WorkflowInstanceOut,
)
from app.modules.workflow.service import WorkflowService

tasks_router = APIRouter(prefix="/tasks", tags=["workflow"])
notifications_router = APIRouter(prefix="/notifications", tags=["workflow"])
definitions_router = APIRouter(prefix="/workflow-definitions", tags=["workflow"])
instances_router = APIRouter(prefix="/workflow-instances", tags=["workflow"])


def _svc(session: AsyncSession) -> WorkflowService:
    return WorkflowService(WorkflowRepository(session))


def _def_svc(session: AsyncSession) -> WorkflowDefinitionService:
    return WorkflowDefinitionService(session)


@tasks_router.get("", response_model=list[TaskOut], summary="My task queue (by role or assignment)")
async def my_tasks(
    only_open: bool = Query(True),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> list[TaskOut]:
    tasks = await _svc(session).my_tasks(principal, only_open=only_open)
    return [TaskOut.model_validate(t) for t in tasks]


@tasks_router.post("/{task_id}/complete", response_model=TaskOut, summary="Complete a task")
async def complete_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> TaskOut:
    return TaskOut.model_validate(await _svc(session).complete_task(task_id, principal))


@notifications_router.get("", response_model=list[NotificationOut], summary="My notifications")
async def my_notifications(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> list[NotificationOut]:
    rows = await _svc(session).my_notifications(principal)
    return [NotificationOut.model_validate(n) for n in rows]


@notifications_router.post("/{notification_id}/read", response_model=NotificationOut, summary="Mark read")
async def mark_read(
    notification_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> NotificationOut:
    return NotificationOut.model_validate(await _svc(session).mark_read(notification_id, principal))


# --- Configurable workflow definitions + instances (BE-2.1) ---
@definitions_router.get("", response_model=list[WorkflowDefinitionOut], summary="List workflow definitions")
async def list_definitions(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> list[WorkflowDefinitionOut]:
    return [WorkflowDefinitionOut.model_validate(d) for d in await _def_svc(session).list_definitions()]


@definitions_router.post("", response_model=WorkflowDefinitionOut, status_code=201, summary="Create a workflow definition")
async def create_definition(
    body: WorkflowDefinitionCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> WorkflowDefinitionOut:
    defn = await _def_svc(session).create_definition(
        key=body.key, name=body.name, initial_state=body.initial_state,
        states=body.states, transitions=body.transitions, activate=body.activate,
    )
    return WorkflowDefinitionOut.model_validate(defn)


@definitions_router.post("/{definition_id}/activate", response_model=WorkflowDefinitionOut, summary="Activate a version")
async def activate_definition(
    definition_id: _uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> WorkflowDefinitionOut:
    return WorkflowDefinitionOut.model_validate(await _def_svc(session).activate(definition_id))


@instances_router.get("", response_model=list[WorkflowInstanceOut], summary="List workflow instances")
async def list_instances(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> list[WorkflowInstanceOut]:
    return [WorkflowInstanceOut.model_validate(i) for i in await _def_svc(session).list_instances()]


@instances_router.post("", response_model=WorkflowInstanceOut, status_code=201, summary="Start a workflow instance")
async def start_instance(
    body: StartInstanceRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> WorkflowInstanceOut:
    inst = await _def_svc(session).start_instance(body.key, body.aggregate_type, body.aggregate_id, body.context)
    return WorkflowInstanceOut.model_validate(inst)


@instances_router.post("/{instance_id}/events", response_model=WorkflowInstanceOut, summary="Dispatch an event")
async def dispatch_event(
    instance_id: _uuid.UUID,
    body: EventRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> WorkflowInstanceOut:
    return WorkflowInstanceOut.model_validate(await _def_svc(session).dispatch_event(instance_id, body.event))
