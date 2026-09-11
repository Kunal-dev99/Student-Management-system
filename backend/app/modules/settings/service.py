"""Settings service (Phase 8): institution settings + list-of-values administration.

Two responsibilities:

1. **Institution settings** — read the merged view (registry default unless a DB override
   exists), write with registry validation, reset by deleting the override. Domain code reads a
   live value through `setting_value(session, key)`.

2. **Reference data (LOVs)** — CRUD for the lookup tables the rest of the platform points at
   (departments, research areas, programmes, funding sources). Deletion is **protected**: a value
   that any row still references cannot be deleted, because deleting it would either break those
   rows or silently orphan history. The error says exactly what is using it.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.modules.settings.models import InstitutionSetting, ValueSetOverride
from app.modules.settings.registry import SETTINGS, grouped


async def setting_value(session: AsyncSession, key: str) -> Any:
    """The live value of a setting: the institution override if set, else the shipped default.

    This is the single read path for domain code. One indexed lookup; no cache, so a change on
    the settings screen takes effect on the next request with nothing to invalidate.
    """
    definition = SETTINGS[key]  # KeyError here is a programming error, not user input
    row = (await session.execute(
        select(InstitutionSetting).where(InstitutionSetting.key == key)
    )).scalar_one_or_none()
    return row.value["value"] if row is not None else definition.default


class SettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Institution settings
    # ------------------------------------------------------------------

    async def overview(self) -> dict:
        overrides = {
            r.key: r for r in (await self.session.execute(
                select(InstitutionSetting)
            )).scalars().all()
        }
        groups = grouped()
        for g in groups:
            for s in g["settings"]:
                row = overrides.get(s["key"])
                s["value"] = row.value["value"] if row is not None else s["default"]
                s["overridden"] = row is not None
                s["updatedAt"] = row.updated_at.isoformat() if row is not None and row.updated_at else None
        return {"groups": groups}

    async def set_value(self, key: str, value: Any, user_id: uuid.UUID | None) -> dict:
        definition = SETTINGS.get(key)
        if definition is None:
            raise NotFoundError(f"Unknown setting: {key}")
        try:
            clean = definition.validate(value)
        except ValueError as exc:
            raise ValidationAppError(str(exc)) from exc
        row = (await self.session.execute(
            select(InstitutionSetting).where(InstitutionSetting.key == key)
        )).scalar_one_or_none()
        if row is None:
            row = InstitutionSetting(key=key, value={"value": clean}, updated_by_user_id=user_id)
            self.session.add(row)
        else:
            row.value = {"value": clean}
            row.updated_by_user_id = user_id
        await self.session.commit()
        return {"key": key, "value": clean, "overridden": clean != definition.default}

    async def reset(self, key: str) -> dict:
        definition = SETTINGS.get(key)
        if definition is None:
            raise NotFoundError(f"Unknown setting: {key}")
        row = (await self.session.execute(
            select(InstitutionSetting).where(InstitutionSetting.key == key)
        )).scalar_one_or_none()
        if row is not None:
            await self.session.delete(row)
            await self.session.commit()
        return {"key": key, "value": definition.default, "overridden": False}

    # ------------------------------------------------------------------
    # Reference data (LOVs)
    # ------------------------------------------------------------------

    def _lov(self) -> dict[str, dict]:
        """kind → model, editable fields, and every FK that references the table.

        Built lazily so importing this module never drags in every domain model.
        """
        from app.modules.funding.models import (
            CostCentre, FundingArrangement, FundingSource, ProjectCode,
        )
        from app.modules.progression.models import MilestoneDefinition
        from app.modules.recruitment.models import Application, ResearchOpportunity
        from app.modules.research.models import ResearchAward, ResearchDemand
        from app.modules.student_record.models import (
            Department,
            Programme,
            ResearchArea,
            ResearchProject,
            Student,
        )

        return {
            "departments": {
                "model": Department, "label": "Department",
                "fields": {"name": str, "code": str},
                "used_by": [
                    ("students", Student.department_id),
                    ("programmes", Programme.department_id),
                    ("research areas", ResearchArea.department_id),
                    ("research demands", ResearchDemand.department_id),
                    ("opportunities", ResearchOpportunity.department_id),
                ],
            },
            "research-areas": {
                "model": ResearchArea, "label": "Research area",
                "fields": {"name": str, "code": str, "department_id": uuid.UUID},
                "used_by": [
                    ("students", Student.research_area_id),
                    ("research projects", ResearchProject.research_area_id),
                    ("research demands", ResearchDemand.research_area_id),
                    ("opportunities", ResearchOpportunity.research_area_id),
                    ("applications", Application.research_area_id),
                ],
            },
            "programmes": {
                "model": Programme, "label": "Programme",
                "fields": {"name": str, "code": str, "department_id": uuid.UUID},
                "used_by": [
                    ("students", Student.programme_id),
                    ("milestone definitions", MilestoneDefinition.programme_id),
                ],
            },
            "funding-sources": {
                "model": FundingSource, "label": "Funding source",
                "fields": {"name": str, "funder_type": str},
                "used_by": [
                    ("funding arrangements", FundingArrangement.funding_source_id),
                    ("research awards", ResearchAward.funder_id),
                ],
            },
            # These two are referenced from funding_arrangement as STRING codes rather than
            # FKs (finance codes are shared with external ledgers so we keep the code as text).
            # `used_by_string` counts by matching the LOV row's `code` against the string column.
            "cost-centres": {
                "model": CostCentre, "label": "Cost centre",
                "fields": {"name": str, "code": str},
                "used_by": [],
                "used_by_string": [
                    ("funding arrangements", FundingArrangement.cost_centre, "code"),
                ],
            },
            "project-codes": {
                "model": ProjectCode, "label": "Project code",
                "fields": {"name": str, "code": str},
                "used_by": [],
                "used_by_string": [
                    ("funding arrangements", FundingArrangement.project_code, "code"),
                ],
            },
        }

    @staticmethod
    def _camel(field: str) -> str:
        head, *rest = field.split("_")
        return head + "".join(w.title() for w in rest)

    def lov_kinds(self) -> list[dict]:
        return [{"kind": k, "label": v["label"],
                 "fields": [self._camel(f) for f in v["fields"]]}
                for k, v in self._lov().items()]

    async def lov_list(self, kind: str) -> list[dict]:
        cfg = self._lov().get(kind)
        if cfg is None:
            raise NotFoundError(f"Unknown reference list: {kind}")
        rows = (await self.session.execute(
            select(cfg["model"]).order_by(cfg["model"].name)
        )).scalars().all()

        # One grouped count per referencing table (not per row) keeps this a handful of queries.
        usage: dict[uuid.UUID, int] = {}
        for _, fk in cfg["used_by"]:
            for ref_id, n in (await self.session.execute(
                select(fk, func.count()).where(fk.is_not(None)).group_by(fk)
            )).all():
                usage[ref_id] = usage.get(ref_id, 0) + int(n)
        # String-referenced LOVs (finance codes) — group by the string column, then
        # translate matches back to the LOV row id via its `code` field.
        for _, str_col, code_field in cfg.get("used_by_string", []):
            code_counts = dict((c, int(n)) for c, n in (await self.session.execute(
                select(str_col, func.count()).where(str_col.is_not(None), str_col != "")
                .group_by(str_col)
            )).all() if c)
            for r in rows:
                v = getattr(r, code_field)
                if v in code_counts:
                    usage[r.id] = usage.get(r.id, 0) + code_counts[v]

        return [{
            "id": str(r.id),
            **{self._camel(f): (str(getattr(r, f)) if isinstance(getattr(r, f), uuid.UUID)
                                else getattr(r, f))
               for f in cfg["fields"]},
            "inUse": usage.get(r.id, 0),
        } for r in rows]

    def _clean_payload(self, cfg: dict, payload: dict, *, partial: bool) -> dict:
        out: dict = {}
        for field, typ in cfg["fields"].items():
            camel = self._camel(field)
            if camel not in payload:
                if not partial and typ is not uuid.UUID:   # FK fields are optional on create
                    raise ValidationAppError(f"{camel} is required")
                continue
            value = payload[camel]
            if typ is uuid.UUID:
                out[field] = uuid.UUID(value) if value else None
            else:
                if value is None or not str(value).strip():
                    raise ValidationAppError(f"{camel} must not be empty")
                out[field] = str(value).strip()
        return out

    async def lov_create(self, kind: str, payload: dict) -> dict:
        cfg = self._lov().get(kind)
        if cfg is None:
            raise NotFoundError(f"Unknown reference list: {kind}")
        values = self._clean_payload(cfg, payload, partial=False)
        if "code" in values:
            dup = (await self.session.execute(
                select(cfg["model"]).where(func.lower(cfg["model"].code) == values["code"].lower())
            )).scalar_one_or_none()
            if dup is not None:
                raise ConflictError(f"{cfg['label']} code '{values['code']}' already exists")
        row = cfg["model"](**values)
        self.session.add(row)
        await self.session.commit()
        return {"id": str(row.id)}

    async def lov_update(self, kind: str, row_id: uuid.UUID, payload: dict) -> dict:
        cfg = self._lov().get(kind)
        if cfg is None:
            raise NotFoundError(f"Unknown reference list: {kind}")
        row = await self.session.get(cfg["model"], row_id)
        if row is None:
            raise NotFoundError(f"{cfg['label']} not found")
        for field, value in self._clean_payload(cfg, payload, partial=True).items():
            setattr(row, field, value)
        await self.session.commit()
        return {"id": str(row.id)}

    async def lov_delete(self, kind: str, row_id: uuid.UUID) -> dict:
        cfg = self._lov().get(kind)
        if cfg is None:
            raise NotFoundError(f"Unknown reference list: {kind}")
        row = await self.session.get(cfg["model"], row_id)
        if row is None:
            raise NotFoundError(f"{cfg['label']} not found")

        # Deleting a value that live rows point at would break or orphan them. Refuse with an
        # exact account of what is using it, so the fix (re-point or retire) is obvious.
        holders = []
        # String-referenced usage checks by matching the LOV's code against the string column.
        for what, str_col, code_field in cfg.get("used_by_string", []):
            code_val = getattr(row, code_field)
            if not code_val:
                continue
            n = (await self.session.execute(
                select(func.count()).where(str_col == code_val)
            )).scalar_one()
            if n:
                holders.append(f"{n} {what}")
        for what, fk in cfg["used_by"]:
            n = (await self.session.execute(
                select(func.count()).where(fk == row_id)
            )).scalar_one()
            if n:
                holders.append(f"{n} {what}")
        if holders:
            raise ConflictError(
                f"Cannot delete {cfg['label'].lower()} '{row.name}' — still referenced by "
                + ", ".join(holders) + ". Re-point those records first."
            )
        await self.session.delete(row)
        await self.session.commit()
        return {"deleted": True}

    # ------------------------------------------------------------------
    # Platform-fixed value sets (read-only)
    # ------------------------------------------------------------------

    def _humanise(self, code: str) -> str:
        """Fallback display for a shipped value code — 'in_review' → 'In review'."""
        return code.replace("_", " ").replace("-", " ").strip().capitalize()

    async def value_sets(self) -> list[dict]:
        """Every domain enum, with per-institution overrides merged in.

        The value **code** is fixed by the platform — the string that appears in the
        database, in FKs, and in business logic. The **label**, **description** and
        **hidden** flag are institution-configurable: label/description are shown to
        users, hidden hides a value from new selectors while keeping it valid on any
        existing row. A value with no override behaves exactly as before.
        """
        import enum as _enum

        from app.modules.admissions import constants as adm
        from app.modules.funding import constants as fund
        from app.modules.person import constants as per
        from app.modules.progression import constants as prog
        from app.modules.recruitment import constants as rec
        from app.modules.research import constants as res
        from app.modules.student_record import constants as stu
        from app.modules.supervision import constants as sup
        from app.modules.thesis import constants as th
        from app.modules.workflow import constants as wf

        # (enum_name, value_code) → override row.
        overrides: dict[tuple[str, str], ValueSetOverride] = {
            (o.enum_name, o.value_code): o
            for o in (await self.session.execute(select(ValueSetOverride))).scalars().all()
        }

        out = []
        seen: set[str] = set()
        for module, area in [(per, "Person"), (rec, "Recruitment"), (adm, "Admissions"),
                             (stu, "Student record"), (sup, "Supervision"), (prog, "Progression"),
                             (fund, "Funding"), (th, "Thesis"), (res, "Research"), (wf, "Workflow")]:
            for name in dir(module):
                obj = getattr(module, name)
                if not (isinstance(obj, type) and issubclass(obj, _enum.Enum)
                        and obj is not _enum.Enum):
                    continue
                if name in seen:
                    continue
                seen.add(name)
                values = []
                for e in obj:
                    ovr = overrides.get((name, e.value))
                    values.append({
                        "code": e.value,
                        "label": (ovr.label if ovr and ovr.label else self._humanise(e.value)),
                        "description": (ovr.description if ovr else None),
                        "hidden": bool(ovr.hidden) if ovr else False,
                        "overridden": ovr is not None,
                        "updatedAt": (ovr.updated_at.isoformat()
                                      if ovr and ovr.updated_at else None),
                    })
                out.append({"area": area, "name": name, "values": values})
        return out

    async def value_set_upsert(self, enum_name: str, value_code: str,
                                payload: dict, user_id: uuid.UUID | None) -> dict:
        """Create-or-update an override. Empty label/description clears that field."""
        # Confirm the (enum, code) pair actually exists in code — otherwise we'd let
        # admins configure ghosts. Cheapest check: rebuild the value_sets index.
        known = {(vs["name"], v["code"])
                 for vs in await self.value_sets() for v in vs["values"]}
        if (enum_name, value_code) not in known:
            raise NotFoundError(
                f"Unknown value set entry: {enum_name} / {value_code}"
            )
        row = (await self.session.execute(
            select(ValueSetOverride).where(
                ValueSetOverride.enum_name == enum_name,
                ValueSetOverride.value_code == value_code,
            )
        )).scalar_one_or_none()

        label = (payload.get("label") or "").strip() or None
        description = (payload.get("description") or "").strip() or None
        hidden = bool(payload.get("hidden", False))

        if row is None:
            row = ValueSetOverride(
                enum_name=enum_name, value_code=value_code,
                label=label, description=description, hidden=hidden,
                updated_by_user_id=user_id,
            )
            self.session.add(row)
        else:
            row.label = label
            row.description = description
            row.hidden = hidden
            row.updated_by_user_id = user_id
        await self.session.commit()
        return {"enumName": enum_name, "valueCode": value_code,
                "label": label, "description": description, "hidden": hidden}

    async def value_set_reset(self, enum_name: str, value_code: str) -> dict:
        row = (await self.session.execute(
            select(ValueSetOverride).where(
                ValueSetOverride.enum_name == enum_name,
                ValueSetOverride.value_code == value_code,
            )
        )).scalar_one_or_none()
        if row is not None:
            await self.session.delete(row)
            await self.session.commit()
        return {"enumName": enum_name, "valueCode": value_code, "overridden": False}
