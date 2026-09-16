"""Statutory reporting as a configurable layer (Phase 6.6 — CIO vision GAP-05).

Statutory returns change every year; the PGR lifecycle does not. So HESA is treated as an
**external specification**, expressed as configuration, not as core domain logic:

    ReportProfile (e.g. "HESA Student", 2026/27)
      └── ReportFieldMapping[]  target field ← source expression + transform + validation

Adding or amending a return means editing configuration, not writing Python. Profiles are
versioned by academic year, so regenerating a prior year's return uses that year's mapping and
reproduces the original file.

The **source expression** is a deliberately small dotted path over a flat per-student record
(e.g. `student.status`, `person.nationality`, `funding.type`). It is not a general expression
language: anything executable in configuration would be a security problem and an operational one.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.exports.models import ReportFieldMapping, ReportProfile

# --- transforms available to a mapping. Pure, total functions: no I/O, no failure. ---

def _t_upper(v): return str(v).upper() if v is not None else None
def _t_lower(v): return str(v).lower() if v is not None else None
def _t_date_iso(v): return v.isoformat() if isinstance(v, (date, datetime)) else v
def _t_date_compact(v): return v.strftime("%Y%m%d") if isinstance(v, (date, datetime)) else v
def _t_year(v): return str(v.year) if isinstance(v, (date, datetime)) else v
def _t_bool_yn(v): return ("Y" if v else "N") if v is not None else None
def _t_int(v):
    try:
        return str(int(Decimal(str(v))))
    except Exception:
        return None
def _t_str(v): return "" if v is None else str(v)


# --- data-cleaning transforms (ICR G5 fix assistant). Non-destructive: they normalise/massage a
#     value, never blank it. Applied at the RETURN layer (the mapping), so the master record is
#     untouched and the change is reversible config. ---
import re as _re

# Characters a statutory text field may safely contain; anything else is stripped (accents kept).
_SAFE_TEXT = _re.compile(r"[^0-9A-Za-zÀ-ÿ .,'\-/()]")

def _t_strip_special(v):
    if v is None:
        return None
    cleaned = _SAFE_TEXT.sub("", str(v))
    return _re.sub(r"\s{2,}", " ", cleaned).strip()

def _t_clamp_pct(v):
    """Clamp a percentage-like number into 0–100 (an outlier is corrected, never removed)."""
    if v is None or str(v).strip() == "":
        return v
    try:
        n = Decimal(str(v))
    except Exception:
        return v
    n = max(Decimal("0"), min(Decimal("100"), n))
    return str(int(n)) if n == n.to_integral_value() else str(n)


TRANSFORMS = {
    "upper": _t_upper, "lower": _t_lower, "date_iso": _t_date_iso,
    "date_compact": _t_date_compact, "year": _t_year, "bool_yn": _t_bool_yn,
    "int": _t_int, "str": _t_str,
    "strip_special": _t_strip_special, "clamp_pct": _t_clamp_pct,
}


# --- F1 — HESA coding frames. Pure lookups, unknown inputs return None so validation catches it. ---

def _map(table: dict[str, str]):
    def _fn(v):
        if v is None:
            return None
        key = str(v).strip().lower()
        return table.get(key)
    return _fn


TRANSFORMS.update({
    "hesa_sex": _map({
        "female": "10", "f": "10", "woman": "10",
        "male": "11",   "m": "11", "man": "11",
        "other": "12",  "non-binary": "12", "nonbinary": "12",
        "": "13",       "unknown": "13", "not specified": "13", "prefer not to say": "13",
    }),
    "hesa_mode": _map({
        "full_time": "01", "full-time": "01", "fulltime": "01", "full time": "01", "ft": "01",
        "part_time": "02", "part-time": "02", "parttime": "02", "part time": "02", "pt": "02",
        "sandwich": "03",
        "writing_up": "31", "writing-up": "31",
    }),
    "hesa_yn": _map({
        "true": "Y", "yes": "Y", "y": "Y", "1": "Y",
        "false": "N", "no": "N", "n": "N", "0": "N",
    }),
    "hesa_studylevel": _map({
        "phd": "D00", "doctorate": "D00", "d00": "D00",
        "mphil": "M11", "m11": "M11",
        "masters": "H11", "h11": "H11",
        "pgdip": "I11", "i11": "I11",
    }),
    "hesa_route": _map({
        "opportunity": "OPPORTUNITY", "route_a": "OPPORTUNITY",
        "proposal": "PROPOSAL", "route_b": "PROPOSAL",
    }),
})


def _luhn_check_digit(number: str) -> str:
    digits = [int(c) for c in number]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def husid(inst_code: str, start_year: int | None, ref: str) -> str:
    """A stable HESA-shaped unique student id: 4-digit institution code + 2-digit entry year +
    6-digit sequence (deterministic from the student ref) + a Luhn check digit. Generated, never
    hand-keyed (ICR G5)."""
    import hashlib

    code = (inst_code or "0000")[:4].rjust(4, "0")
    yy = f"{(start_year or 0) % 100:02d}"
    seq = int(hashlib.sha1(ref.encode()).hexdigest(), 16) % 1_000_000
    body = f"{code}{yy}{seq:06d}"
    return body + _luhn_check_digit(body)


def resolve(record: dict, path: str):
    """Read a dotted path out of the flat student record. Unknown paths resolve to None."""
    node = record
    for part in (path or "").split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
        if node is None:
            return None
    return node


class StatutoryEngine:
    """Builds a statutory extract purely from configuration."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------------- profiles ----------------

    async def list_profiles(self) -> list[dict]:
        rows = (await self.session.execute(
            select(ReportProfile).order_by(ReportProfile.code, ReportProfile.academic_year)
        )).scalars().all()
        out = []
        for p in rows:
            fields = await self._mappings(p.id)
            out.append({**self.profile_out(p), "fieldCount": len(fields)})
        return out

    @staticmethod
    def profile_out(p: ReportProfile) -> dict:
        return {
            "id": str(p.id), "code": p.code, "name": p.name,
            "academicYear": p.academic_year, "version": p.version,
            "description": p.description, "isActive": p.is_active,
            "signedOff": p.signed_off_by is not None,
            "signedOffAt": p.signed_off_at.isoformat() if p.signed_off_at else None,
            "signedOffBy": str(p.signed_off_by) if p.signed_off_by else None,
            "signedOffNotes": p.signed_off_notes,
        }

    @staticmethod
    def mapping_out(m: ReportFieldMapping) -> dict:
        return {
            "id": str(m.id), "targetField": m.target_field, "position": m.position,
            "sourceExpression": m.source_expression, "transform": m.transform,
            "defaultValue": m.default_value, "required": m.required,
            "allowedValues": m.allowed_values,
        }

    async def get_profile(self, profile_id: uuid.UUID) -> ReportProfile:
        p = (await self.session.execute(
            select(ReportProfile).where(ReportProfile.id == profile_id)
        )).scalar_one_or_none()
        if p is None:
            raise NotFoundError("Report profile not found")
        return p

    async def _mappings(self, profile_id: uuid.UUID) -> list[ReportFieldMapping]:
        return list((await self.session.execute(
            select(ReportFieldMapping)
            .where(ReportFieldMapping.profile_id == profile_id)
            .order_by(ReportFieldMapping.position)
        )).scalars().all())

    async def profile_detail(self, profile_id: uuid.UUID) -> dict:
        p = await self.get_profile(profile_id)
        # ICR G5 — surface where each field is captured on the record ("keyed_at"), from the spec,
        # so Registry can see the record location behind every mapping, not just the source path.
        from app.modules.exports.spec_resolver import resolve_fields
        keyed = {f["field"]: f.get("keyed_at") for f in await resolve_fields(self.session, p.code)}
        fields = []
        for m in await self._mappings(p.id):
            row = self.mapping_out(m)
            row["keyedAt"] = keyed.get(m.target_field)
            fields.append(row)
        return {**self.profile_out(p), "fields": fields}

    async def create_profile(
        self, *, code: str, name: str, academic_year: str,
        description: str | None = None, version: int = 1,
    ) -> ReportProfile:
        existing = (await self.session.execute(
            select(ReportProfile).where(
                ReportProfile.code == code, ReportProfile.academic_year == academic_year,
                ReportProfile.version == version,
            )
        )).scalar_one_or_none()
        if existing:
            raise ConflictError(
                f"Profile {code} {academic_year} v{version} already exists — clone it to a new version"
            )
        profile = ReportProfile(code=code, name=name, academic_year=academic_year,
                                version=version, description=description)
        self.session.add(profile)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    @staticmethod
    def _refuse_if_signed_off(profile: ReportProfile, action: str) -> None:
        """A signed-off profile is a historical fact; editing would rewrite what Registry attested to."""
        if profile.signed_off_by is not None:
            raise ConflictError(
                f"Profile {profile.code} {profile.academic_year} v{profile.version} is signed off — "
                f"unsign it before you can {action}."
            )

    async def add_field(
        self, profile_id: uuid.UUID, *, target_field: str, source_expression: str,
        position: int | None = None, transform: str | None = None,
        default_value: str | None = None, required: bool = False,
        allowed_values: list[str] | None = None,
    ) -> ReportFieldMapping:
        profile = await self.get_profile(profile_id)
        self._refuse_if_signed_off(profile, "add a field")
        if transform and transform not in TRANSFORMS:
            raise WorkflowError(
                f"Unknown transform '{transform}'. Available: {', '.join(sorted(TRANSFORMS))}"
            )
        existing = await self._mappings(profile_id)
        if any(m.target_field == target_field for m in existing):
            raise ConflictError(f"Field '{target_field}' is already mapped in this profile")
        mapping = ReportFieldMapping(
            profile_id=profile_id, target_field=target_field,
            source_expression=source_expression,
            position=position if position is not None else len(existing) + 1,
            transform=transform, default_value=default_value,
            required=required, allowed_values=allowed_values,
        )
        self.session.add(mapping)
        await self.session.commit()
        await self.session.refresh(mapping)
        return mapping

    async def clone_profile(self, profile_id: uuid.UUID, *, academic_year: str) -> ReportProfile:
        """Carry a return forward to a new year — the usual way a statutory change is handled."""
        source = await self.get_profile(profile_id)
        clone = await self.create_profile(
            code=source.code, name=source.name, academic_year=academic_year,
            description=f"Cloned from {source.academic_year} v{source.version}",
        )
        for m in await self._mappings(source.id):
            self.session.add(ReportFieldMapping(
                profile_id=clone.id, target_field=m.target_field, position=m.position,
                source_expression=m.source_expression, transform=m.transform,
                default_value=m.default_value, required=m.required,
                allowed_values=m.allowed_values,
            ))
        await self.session.commit()
        await self.session.refresh(clone)
        return clone

    async def from_spec(
        self, *, spec_key: str, academic_year: str | None = None, name: str | None = None,
    ) -> ReportProfile:
        """Create a profile PRE-MAPPED from a published spec pack — ICR G5.

        Every spec field becomes a mapping using its best-known source/transform/coding frame;
        fields with no automatic source are created required-but-unmapped (empty source), so the
        sign-off gate and validation flag exactly what Registry still needs to supply. This is the
        honest version of "check the website": HESA publishes the spec, we ship it as data.
        """
        from app.modules.exports.spec_resolver import resolve_pack

        # Through the resolver — an accepted advisory's active version supersedes the code baseline.
        pack = await resolve_pack(self.session, spec_key)
        if pack is None:
            raise NotFoundError(f"No spec pack '{spec_key}'")
        profile = await self.create_profile(
            code=pack["code"], name=name or pack["name"],
            academic_year=academic_year or pack["academic_year"],
            description=f"Created from spec pack {spec_key}",
        )
        for i, f in enumerate(pack["fields"], start=1):
            self.session.add(ReportFieldMapping(
                profile_id=profile.id, target_field=f["field"], position=i,
                source_expression=f.get("source", "") or "",
                transform=f.get("transform"), default_value=f.get("default"),
                required=f.get("required", True), allowed_values=f.get("allowed"),
            ))
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    # ---------------- the flat record every mapping reads from ----------------

    async def build_records(self) -> list[dict]:
        """One flat dict per student. This is the *only* contract mappings depend on, so the
        domain model can evolve without breaking every configured return."""
        from app.modules.funding.constants import FundingStatus
        from app.modules.funding.models import FundingArrangement, FundingSource
        from app.modules.person.models import Person
        from app.modules.recruitment.models import Application
        from app.modules.research.models import ResearchAward
        from app.modules.student_record.models import Programme, ResearchProject, Student

        rows = (await self.session.execute(
            select(Student, Person).join(Person, Person.id == Student.person_id)
            .order_by(Student.student_ref)
        )).all()
        programmes = {p.id: p for p in (await self.session.execute(select(Programme))).scalars().all()}
        projects = {p.student_id: p for p in (await self.session.execute(select(ResearchProject))).scalars().unique().all()}
        sources = {f.id: f for f in (await self.session.execute(select(FundingSource))).scalars().all()}
        awards = {a.id: a for a in (await self.session.execute(select(ResearchAward))).scalars().all()}
        routes: dict = {}
        for a in (await self.session.execute(select(Application))).scalars().unique().all():
            routes.setdefault(a.person_id, a.route.value if hasattr(a.route, "value") else a.route)
        funding: dict = {}
        for fa in (await self.session.execute(select(FundingArrangement).where(
            FundingArrangement.status == FundingStatus.active, FundingArrangement.valid_to.is_(None)
        ))).scalars().all():
            funding.setdefault(fa.student_id, fa)

        # ICR G4 — current study intensity (FTE %) per student: the latest approved intensity
        # change, else derived from study mode. Feeds the HESA STULOAD field.
        from app.modules.student_record.constants import (
            DEFAULT_PART_TIME_INTENSITY_PCT, FULL_TIME_INTENSITY_PCT,
            LifecycleEventStatus, LifecycleEventType, StudyMode,
        )
        from app.modules.student_record.models import StudentLifecycleEvent

        latest_intensity: dict = {}
        for ev in (await self.session.execute(
            select(StudentLifecycleEvent)
            .where(StudentLifecycleEvent.event_type == LifecycleEventType.intensity_change,
                   StudentLifecycleEvent.status == LifecycleEventStatus.approved)
            .order_by(StudentLifecycleEvent.start_date)
        )).scalars().all():
            if ev.intensity_pct is not None:
                latest_intensity[ev.student_id] = ev.intensity_pct  # last by start_date wins

        # ICR G5 — HUSID is generated from the institution code + entry year + a sequence, so it is
        # never hand-keyed. The institution code is a setting (0000 until Registry sets the real one).
        from app.modules.settings.service import setting_value
        inst_code = await setting_value(self.session, "statutory.husid_institution_code")

        records = []
        for student, person in rows:
            fa = funding.get(student.id)
            proj = projects.get(student.id)
            prog = programmes.get(student.programme_id)
            award = awards.get(proj.research_award_id) if proj and proj.research_award_id else None
            records.append({
                "student": {
                    "ref": student.student_ref,
                    "status": student.status.value if hasattr(student.status, "value") else student.status,
                    "mode": student.study_mode.value if hasattr(student.study_mode, "value") else student.study_mode,
                    "startDate": student.start_date,
                    "expectedEndDate": student.expected_end_date,
                    "originalExpectedEndDate": student.original_expected_end_date,
                    "entryRoute": routes.get(student.person_id),
                    "intensityPct": latest_intensity.get(
                        student.id,
                        FULL_TIME_INTENSITY_PCT if student.study_mode is StudyMode.full_time
                        else DEFAULT_PART_TIME_INTENSITY_PCT,
                    ),
                    "husid": husid(
                        inst_code,
                        student.start_date.year if student.start_date else None,
                        student.student_ref,
                    ),
                },
                "person": {
                    "givenName": person.given_name, "familyName": person.family_name,
                    "nationality": person.nationality, "email": person.email,
                    "dateOfBirth": getattr(person, "date_of_birth", None),
                },
                "programme": {"name": prog.name if prog else None, "code": prog.code if prog else None},
                "research": {"topic": proj.research_topic if proj else None,
                             "group": proj.research_group if proj else None},
                "funding": {
                    "type": fa.funding_type.value if fa else None,
                    "source": sources[fa.funding_source_id].name if fa and fa.funding_source_id in sources else None,
                    "amount": fa.stipend_amount if fa else None,
                    "currency": fa.currency if fa else None,
                    "costCentre": fa.cost_centre if fa else None,
                },
                "award": {"ref": award.award_ref if award else None,
                          "title": award.title if award else None},
            })
        return records

    # ---------------- generate + validate ----------------

    async def generate(self, profile_id: uuid.UUID) -> dict:
        """Produce the extract and its validation report, entirely from configuration."""
        profile = await self.get_profile(profile_id)
        mappings = await self._mappings(profile_id)
        if not mappings:
            raise WorkflowError("This profile has no field mappings, so it cannot produce a return")

        records = await self.build_records()
        header = [m.target_field for m in mappings]
        rows, issues = [], []

        import re

        from app.modules.exports.spec_resolver import resolve_rules
        spec_rules = await resolve_rules(self.session, profile.code)

        for record in records:
            out_row, ref = [], record["student"]["ref"]
            values: dict[str, str] = {}
            for m in mappings:
                raw = resolve(record, m.source_expression)
                if raw is None and m.default_value is not None:
                    raw = m.default_value
                value = TRANSFORMS[m.transform](raw) if m.transform else raw
                text = "" if value is None else str(value)

                if m.required and text == "":
                    issues.append({
                        "studentRef": ref, "field": m.target_field, "severity": "error",
                        "message": f"'{m.target_field}' is required by {profile.code} but is empty.",
                        "sourceExpression": m.source_expression,
                    })
                elif m.allowed_values and text and text not in m.allowed_values:
                    issues.append({
                        "studentRef": ref, "field": m.target_field, "severity": "error",
                        "message": f"'{text}' is not an accepted value for '{m.target_field}'.",
                        "allowed": m.allowed_values,
                    })
                values[m.target_field] = text
                out_row.append(text)

            # ICR G5 — spec-level cross-field / format rules (e.g. ENDDATE >= COMDATE). Each rule
            # carries its own severity: an "error" rule is a hard fail that blocks sign-off (HESA
            # would reject the file); a "warning" rule is advisory and surfaces for review only.
            # Default is "error" — a rule the Registry bothered to state is normally enforced.
            for rule in spec_rules:
                flds = rule.get("fields", [])
                sev = rule.get("severity", "error")
                if rule["kind"] == "order" and len(flds) == 2:
                    a, b = values.get(flds[0], ""), values.get(flds[1], "")
                    if a and b and a > b:  # YYYYMMDD compares correctly as text
                        issues.append({
                            "studentRef": ref, "field": flds[1], "severity": sev,
                            "message": f"{flds[1]} ({b}) — {rule.get('message', 'ordering rule failed')} "
                                       f"({flds[0]} is {a}).",
                        })
                elif rule["kind"] == "format_yyyymmdd":
                    for fld in flds:
                        v = values.get(fld, "")
                        if v and not re.fullmatch(r"\d{8}", v):
                            issues.append({
                                "studentRef": ref, "field": fld, "severity": sev,
                                "message": f"{fld} ('{v}') {rule.get('message', 'must be YYYYMMDD')}.",
                            })
            rows.append(out_row)

        return {
            "profile": self.profile_out(profile),
            "header": header,
            "rows": rows,
            "rowCount": len(rows),
            "validation": {
                "errors": sum(1 for i in issues if i["severity"] == "error"),
                "warnings": sum(1 for i in issues if i["severity"] == "warning"),
                "issues": issues,
                # Sign-off blocks on any error — an unmapped required field, a bad coding value, or
                # a failed error-severity rule (e.g. ENDDATE < COMDATE). Warning-severity rules are
                # advisory and do not block.
                "valid": not any(i["severity"] == "error" for i in issues),
            },
        }

    # ---------------- ICR G5 — data-quality fix assistant (suggest → accept → apply) ----------------

    async def fix_suggestions(self, profile_id: uuid.UUID) -> dict:
        """Scan the return's produced values for known data-quality issues and, for each, propose a
        deterministic fix from the resolution dictionary — with affected count and before→after
        samples. Nothing is changed here; this is the 'suggest' half."""
        from app.modules.exports.resolutions import RESOLUTIONS, detect

        profile = await self.get_profile(profile_id)
        mappings = await self._mappings(profile_id)
        records = await self.build_records()

        groups: dict[tuple[str, str], dict] = {}
        for record in records:
            ref = record["student"]["ref"]
            for m in mappings:
                raw = resolve(record, m.source_expression)
                if raw is None and m.default_value is not None:
                    raw = m.default_value
                value = TRANSFORMS[m.transform](raw) if m.transform else raw
                text = "" if value is None else str(value)
                kind = detect(m, text)
                if not kind:
                    continue
                g = groups.setdefault((m.target_field, kind), {
                    "field": m.target_field, "type": kind, "count": 0, "samples": [],
                })
                g["count"] += 1
                if len(g["samples"]) < 5:
                    after = TRANSFORMS[RESOLUTIONS[kind]["transform"]](raw)
                    g["samples"].append({
                        "studentRef": ref, "before": text,
                        "after": "" if after is None else str(after),
                    })

        out = []
        for (_field, kind), g in groups.items():
            r = RESOLUTIONS[kind]
            out.append({**g, "label": r["label"], "description": r["description"],
                        "transform": r["transform"], "applicable": True})
        out.sort(key=lambda x: -x["count"])
        return {"profile": self.profile_out(profile), "suggestions": out}

    async def apply_fix(self, profile_id: uuid.UUID, *, field: str, transform: str) -> dict:
        """Apply an accepted fix: set the resolution's transform on that field's mapping. Cleans the
        return output (non-destructive, reversible); refuses on a signed-off profile."""
        from app.modules.exports.resolutions import VALID_FIX_TRANSFORMS

        if transform not in VALID_FIX_TRANSFORMS:
            raise WorkflowError(f"Unknown fix transform '{transform}'")
        mappings = await self._mappings(profile_id)
        m = next((x for x in mappings if x.target_field == field), None)
        if m is None:
            raise NotFoundError(f"No mapping for field '{field}'")
        await self.update_field(profile_id, m.id, transform=transform)
        return {"field": field, "transform": transform, "applied": True}

    # ---------------- F1 — sign-off, immutability, mandatory-spec gates ----------------

    async def compile(self, profile_id: uuid.UUID) -> dict:
        """Return the mandatory-field gap between the profile and the return's published spec.

        A profile can only be signed off when this returns no ``missing`` entries. Each entry names
        the exact spec field and the coding frame (if any) the profile would need to satisfy.
        """
        from app.modules.exports.spec_resolver import resolve_fields

        profile = await self.get_profile(profile_id)
        mappings = await self._mappings(profile_id)
        mapped = {m.target_field for m in mappings}
        spec = await resolve_fields(self.session, profile.code)
        missing = [
            {"field": s["field"], "description": s.get("description", ""),
             "allowed": s.get("allowed")}
            for s in spec if s["field"] not in mapped
        ]
        return {
            "profile": self.profile_out(profile),
            "specCode": profile.code,
            "specFieldCount": len(spec),
            "mappedFieldCount": len(mapped),
            "missing": missing,
            "signOffReady": (not missing) and bool(mappings),
        }

    async def update_field(
        self, profile_id: uuid.UUID, mapping_id: uuid.UUID, **changes,
    ) -> ReportFieldMapping:
        profile = await self.get_profile(profile_id)
        self._refuse_if_signed_off(profile, "edit a mapping")
        m = (await self.session.execute(
            select(ReportFieldMapping).where(
                ReportFieldMapping.id == mapping_id,
                ReportFieldMapping.profile_id == profile_id,
            )
        )).scalar_one_or_none()
        if m is None:
            raise NotFoundError("Field mapping not found")
        if changes.get("transform") and changes["transform"] not in TRANSFORMS:
            raise WorkflowError(
                f"Unknown transform '{changes['transform']}'. Available: {', '.join(sorted(TRANSFORMS))}"
            )
        for k, v in changes.items():
            if v is not None:
                setattr(m, k, v)
        await self.session.commit()
        await self.session.refresh(m)
        return m

    async def delete_field(self, profile_id: uuid.UUID, mapping_id: uuid.UUID) -> None:
        profile = await self.get_profile(profile_id)
        self._refuse_if_signed_off(profile, "remove a mapping")
        m = (await self.session.execute(
            select(ReportFieldMapping).where(
                ReportFieldMapping.id == mapping_id,
                ReportFieldMapping.profile_id == profile_id,
            )
        )).scalar_one_or_none()
        if m is None:
            raise NotFoundError("Field mapping not found")
        await self.session.delete(m)
        await self.session.commit()

    async def sign_off(
        self, profile_id: uuid.UUID, *, user_id: uuid.UUID, notes: str | None = None,
    ) -> ReportProfile:
        """Attest the profile is complete for the return. Blocks if the spec is not satisfied
        or if the current cohort would produce validation errors."""
        from datetime import datetime, timezone

        profile = await self.get_profile(profile_id)
        if profile.signed_off_by is not None:
            raise ConflictError("Profile is already signed off")
        report = await self.compile(profile_id)
        if not report["signOffReady"]:
            missing = ", ".join(m["field"] for m in report["missing"][:8])
            more = "" if len(report["missing"]) <= 8 else f" (+{len(report['missing'])-8} more)"
            raise WorkflowError(
                f"Cannot sign off: {len(report['missing'])} mandatory field(s) unmapped: {missing}{more}"
                if report["missing"]
                else "Cannot sign off: profile has no field mappings"
            )
        gen = await self.generate(profile_id)
        if not gen["validation"]["valid"]:
            raise WorkflowError(
                f"Cannot sign off: {gen['validation']['errors']} validation error(s) in the current "
                "cohort. Fix them, or reduce cohort scope, then retry."
            )
        profile.signed_off_by = user_id
        profile.signed_off_at = datetime.now(timezone.utc)
        profile.signed_off_notes = notes
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def unsign(self, profile_id: uuid.UUID) -> ReportProfile:
        profile = await self.get_profile(profile_id)
        if profile.signed_off_by is None:
            raise ConflictError("Profile is not signed off")
        profile.signed_off_by = None
        profile.signed_off_at = None
        profile.signed_off_notes = None
        await self.session.commit()
        await self.session.refresh(profile)
        return profile
