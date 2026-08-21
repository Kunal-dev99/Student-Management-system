"""Configurable workflow definitions + instances (arch §9.1, BE-2.1).

A workflow is a versioned state machine stored as data: states + transitions
(`{from, on, to, action}`). Instances advance by dispatching events; a transition's optional
`action` can create a task — so a new flow (or a change to one) needs no code, only data.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, WorkflowError
from app.modules.workflow.engine import WorkflowEngine
from app.modules.workflow.models import WorkflowDefinition, WorkflowInstance


class WorkflowDefinitionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_definitions(self) -> list[WorkflowDefinition]:
        stmt = select(WorkflowDefinition).order_by(WorkflowDefinition.key, WorkflowDefinition.version)
        return list((await self.session.execute(stmt)).scalars().all())

    async def create_definition(self, *, key: str, name: str, initial_state: str, states: list, transitions: list, activate: bool) -> WorkflowDefinition:
        max_v = (await self.session.execute(
            select(func.max(WorkflowDefinition.version)).where(WorkflowDefinition.key == key)
        )).scalar_one_or_none()
        version = (max_v or 0) + 1
        if initial_state not in states:
            raise WorkflowError("initial_state must be one of states")
        defn = WorkflowDefinition(
            key=key, version=version, name=name, initial_state=initial_state,
            states=states, transitions=transitions, active=False,
        )
        self.session.add(defn)
        await self.session.flush()
        if activate:
            await self._activate(defn)
        await self.session.commit()
        await self.session.refresh(defn)
        return defn

    async def _activate(self, defn: WorkflowDefinition) -> None:
        # Only one active version per key.
        others = (await self.session.execute(
            select(WorkflowDefinition).where(WorkflowDefinition.key == defn.key, WorkflowDefinition.id != defn.id)
        )).scalars().all()
        for o in others:
            o.active = False
        defn.active = True

    async def activate(self, definition_id: uuid.UUID) -> WorkflowDefinition:
        defn = (await self.session.execute(select(WorkflowDefinition).where(WorkflowDefinition.id == definition_id))).scalar_one_or_none()
        if defn is None:
            raise NotFoundError("Workflow definition not found")
        await self._activate(defn)
        await self.session.commit()
        await self.session.refresh(defn)
        return defn

    async def _active_for_key(self, key: str) -> WorkflowDefinition | None:
        return (await self.session.execute(
            select(WorkflowDefinition).where(WorkflowDefinition.key == key, WorkflowDefinition.active.is_(True))
        )).scalar_one_or_none()

    async def start_instance(self, key: str, aggregate_type: str, aggregate_id: uuid.UUID, context: dict | None) -> WorkflowInstance:
        defn = await self._active_for_key(key)
        if defn is None:
            raise WorkflowError(f"No active workflow definition for '{key}'")
        instance = WorkflowInstance(
            definition_id=defn.id, aggregate_type=aggregate_type, aggregate_id=aggregate_id,
            current_state=defn.initial_state, context=context,
        )
        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def list_instances(self) -> list[WorkflowInstance]:
        stmt = select(WorkflowInstance).order_by(WorkflowInstance.created_at.desc()).limit(100)
        return list((await self.session.execute(stmt)).scalars().all())

    async def dispatch_event(self, instance_id: uuid.UUID, event: str) -> WorkflowInstance:
        instance = (await self.session.execute(select(WorkflowInstance).where(WorkflowInstance.id == instance_id))).scalar_one_or_none()
        if instance is None:
            raise NotFoundError("Workflow instance not found")
        defn = (await self.session.execute(select(WorkflowDefinition).where(WorkflowDefinition.id == instance.definition_id))).scalar_one()
        transition = next(
            (t for t in defn.transitions if t.get("from") == instance.current_state and t.get("on") == event),
            None,
        )
        if transition is None:
            raise WorkflowError(f"No transition from '{instance.current_state}' on '{event}'")
        instance.current_state = transition["to"]
        # Optional data-driven action: create a task.
        action = transition.get("action") or {}
        if isinstance(action, dict) and action.get("createTask"):
            spec = action["createTask"]
            WorkflowEngine(self.session).create_task(
                title=spec.get("title", "Workflow task"),
                assignee_role=spec.get("assigneeRole"),
                aggregate_type=instance.aggregate_type, aggregate_id=instance.aggregate_id,
            )
        await self.session.commit()
        await self.session.refresh(instance)
        return instance
