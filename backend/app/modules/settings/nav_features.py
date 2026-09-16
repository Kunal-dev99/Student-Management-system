"""Configurable navigation — the runtime park mechanism for the sidebar (ICR).

Every top-level nav destination is a *feature* an admin can switch off. Switching one off removes
it from the sidebar and blocks its route, but changes nothing in code — the route and its screens
stay in place, ready to switch back on. This is the runtime, tenant-wide evolution of the static
``frontend/src/config/studentPanels.ts`` park config, applied to the whole navigation.

State lives in the generic ``InstitutionSetting`` key→JSON store under ``nav:<route>`` keys, so it
shares the same persistence and audit as every other institution setting; defaults are on. A couple
of destinations are ``core`` (Dashboard, Settings) and are never disableable — otherwise an admin
could hide the very screen that turns things back on.

The recruitment funnel (/research, /recruitment, /admissions) is deliberately NOT here: it already
has its own master switch, ``recruitment.enabled`` (ICR G2), and is toggled under Institution
policy. This registry governs everything else.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.settings.models import InstitutionSetting

NAV_GROUPS = ("Main", "Administration", "Advanced")


@dataclass(frozen=True)
class NavFeatureDef:
    route: str
    label: str
    group: str
    core: bool = False   # always-on; not shown as a toggle (you must keep a way back)

    @property
    def key(self) -> str:
        return f"nav:{self.route}"


# Mirrors the AppShell sidebar. Dashboard + Settings are core so the admin can always navigate and
# reach the toggle screen. Recruitment funnel routes are intentionally excluded (see module docs).
NAV_FEATURES: list[NavFeatureDef] = [
    # Main
    NavFeatureDef("/dashboard", "Dashboard", "Main", core=True),
    NavFeatureDef("/analytics", "Analytics", "Main"),
    NavFeatureDef("/portal", "My journey", "Main"),
    NavFeatureDef("/documents", "Documents", "Main"),
    NavFeatureDef("/messages", "Messages", "Main"),
    NavFeatureDef("/tasks", "Tasks", "Main"),
    NavFeatureDef("/reviews/weekly", "Weekly review", "Main"),
    NavFeatureDef("/my-students", "My students", "Main"),
    NavFeatureDef("/persons", "Persons", "Main"),
    NavFeatureDef("/students", "Students", "Main"),
    NavFeatureDef("/funding/payments", "Payment status", "Main"),
    NavFeatureDef("/supervision", "Supervision", "Main"),
    NavFeatureDef("/supervision/workforce", "Workforce", "Main"),
    NavFeatureDef("/progression", "Progression", "Main"),
    NavFeatureDef("/progression/transfer-viva", "Transfer viva", "Main"),
    NavFeatureDef("/funding", "Funding", "Main"),
    NavFeatureDef("/thesis", "Thesis", "Main"),
    NavFeatureDef("/completion", "Completion", "Main"),
    # Administration
    NavFeatureDef("/programmes", "Programmes", "Administration"),
    NavFeatureDef("/funding-integrity", "Funding integrity", "Administration"),
    NavFeatureDef("/statutory", "Statutory", "Administration"),
    NavFeatureDef("/workflows", "Workflows", "Administration"),
    NavFeatureDef("/integration", "Integration", "Administration"),
    NavFeatureDef("/settings", "Settings", "Administration", core=True),
    NavFeatureDef("/audit", "Audit", "Administration"),
    # Advanced
    NavFeatureDef("/composer", "Composer", "Advanced"),
    NavFeatureDef("/pattern-lab", "Pattern Lab", "Advanced"),
    NavFeatureDef("/case-explorer", "Case Explorer", "Advanced"),
    NavFeatureDef("/policy-compiler", "Policy Compiler", "Advanced"),
    NavFeatureDef("/change-radar", "Change Radar", "Advanced"),
]

_BY_KEY = {f.key: f for f in NAV_FEATURES}
_TOGGLEABLE_KEYS = [f.key for f in NAV_FEATURES if not f.core]


async def _overrides(session: AsyncSession) -> dict[str, bool]:
    """The stored on/off overrides for nav keys (absent key = default on)."""
    rows = (
        await session.execute(
            select(InstitutionSetting).where(InstitutionSetting.key.in_(_TOGGLEABLE_KEYS))
        )
    ).scalars().all()
    return {r.key: bool(r.value.get("value", True)) for r in rows}


async def disabled_nav_map(session: AsyncSession) -> dict[str, bool]:
    """`{key: False}` for every disabled toggleable feature — the shape /me sends the client.

    Only disabled entries are emitted: the client treats an absent key as on, so this stays small
    and the default-on behaviour is automatic.
    """
    overrides = await _overrides(session)
    return {key: False for key, val in overrides.items() if val is False}


async def nav_overview(session: AsyncSession) -> dict:
    """Grouped nav features with their current enabled state, for the admin toggle screen."""
    overrides = await _overrides(session)
    groups: dict[str, list[dict]] = {g: [] for g in NAV_GROUPS}
    for f in NAV_FEATURES:
        groups.setdefault(f.group, []).append({
            "route": f.route,
            "label": f.label,
            "group": f.group,
            "core": f.core,
            "enabled": True if f.core else overrides.get(f.key, True),
        })
    return {"groups": [{"group": g, "items": groups[g]} for g in NAV_GROUPS if groups.get(g)]}


async def set_nav_feature(
    session: AsyncSession, *, route: str, enabled: bool, user_id=None
) -> dict:
    """Enable/disable one nav feature. Refuses core features and unknown routes."""
    from app.core.errors import NotFoundError, ValidationAppError

    key = f"nav:{route}"
    definition = _BY_KEY.get(key)
    if definition is None:
        raise NotFoundError(f"Unknown navigation feature: {route}")
    if definition.core:
        raise ValidationAppError(f"{definition.label} is a core screen and cannot be disabled")

    row = (
        await session.execute(select(InstitutionSetting).where(InstitutionSetting.key == key))
    ).scalar_one_or_none()
    if row is None:
        row = InstitutionSetting(key=key, value={"value": enabled}, updated_by_user_id=user_id)
        session.add(row)
    else:
        row.value = {"value": enabled}
        row.updated_by_user_id = user_id
    await session.commit()
    return {"route": route, "enabled": enabled}
