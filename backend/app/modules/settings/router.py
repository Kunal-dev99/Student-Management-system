"""Settings endpoints (Phase 8): institution settings + reference data (LOVs).

Everything here requires `admin.configure` — these are institution-wide switches, not personal
preferences (those live under /notifications/preferences).
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.principal import Principal
from app.db.session import get_read_session, get_session

from app.modules.settings.service import SettingsService

settings_router = APIRouter(prefix="/settings", tags=["settings"])
reference_router = APIRouter(prefix="/reference", tags=["settings"])


class SettingWrite(BaseModel):
    value: Any


# --- institution settings ---

@settings_router.get("/institution", summary="Every institution setting, grouped, with defaults")
async def institution_settings(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await SettingsService(session).overview()


@settings_router.put("/institution/{key}", summary="Set an institution setting")
async def set_institution_setting(
    key: str,
    body: SettingWrite,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("admin.configure")),
) -> dict:
    return await SettingsService(session).set_value(key, body.value, principal.user_id)


@settings_router.delete("/institution/{key}", summary="Reset a setting to the shipped default")
async def reset_institution_setting(
    key: str,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await SettingsService(session).reset(key)


# --- configurable navigation (the runtime park mechanism for the sidebar) ---

class NavFeatureWrite(BaseModel):
    route: str
    enabled: bool


@settings_router.get("/nav-features", summary="Sidebar features, grouped, with on/off state")
async def nav_features(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    from app.modules.settings.nav_features import nav_overview

    return await nav_overview(session)


@settings_router.put("/nav-features", summary="Enable or disable a sidebar feature")
async def set_nav_feature(
    body: NavFeatureWrite,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("admin.configure")),
) -> dict:
    from app.modules.settings.nav_features import set_nav_feature as _set

    return await _set(session, route=body.route, enabled=body.enabled, user_id=principal.user_id)


# --- reference data (LOVs) ---

@reference_router.get("", summary="Which reference lists exist, and their editable fields")
async def reference_kinds(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("admin.configure")),
) -> list[dict]:
    return SettingsService(session).lov_kinds()


@reference_router.get("/value-sets", summary="Platform value sets with per-institution overrides merged in")
async def value_sets(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("admin.configure")),
) -> list[dict]:
    return await SettingsService(session).value_sets()


class ValueSetWrite(BaseModel):
    label: str | None = None
    description: str | None = None
    hidden: bool = False


@reference_router.put("/value-sets/{enum_name}/{value_code}",
                      summary="Override an enum value's label/description/hidden flag")
async def value_set_upsert(
    enum_name: str,
    value_code: str,
    body: ValueSetWrite,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("admin.configure")),
) -> dict:
    return await SettingsService(session).value_set_upsert(
        enum_name, value_code, body.model_dump(), principal.user_id
    )


@reference_router.delete("/value-sets/{enum_name}/{value_code}",
                         summary="Reset an enum value back to the shipped default")
async def value_set_reset(
    enum_name: str,
    value_code: str,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await SettingsService(session).value_set_reset(enum_name, value_code)


@reference_router.get("/{kind}", summary="List one reference list, with usage counts")
async def lov_list(
    kind: str,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("admin.configure")),
) -> list[dict]:
    return await SettingsService(session).lov_list(kind)


@reference_router.post("/{kind}", status_code=201, summary="Add a value")
async def lov_create(
    kind: str,
    payload: dict,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await SettingsService(session).lov_create(kind, payload)


@reference_router.patch("/{kind}/{row_id}", summary="Edit a value")
async def lov_update(
    kind: str,
    row_id: uuid.UUID,
    payload: dict,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await SettingsService(session).lov_update(kind, row_id, payload)


@reference_router.delete("/{kind}/{row_id}", summary="Delete a value (refused while in use)")
async def lov_delete(
    kind: str,
    row_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await SettingsService(session).lov_delete(kind, row_id)
