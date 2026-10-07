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

import logging
import time
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationAppError, WorkflowError
from app.modules.exports.models import ReportFieldMapping, ReportProfile

log = logging.getLogger("pgr.statutory")


def mapped_custom_keys(mappings) -> set[str]:
    """The custom attributes a set of mappings reads — ``custom.<key>`` source paths
    (custom attribute governance, Phase 5: a return loads only these)."""
    out = set()
    for m in mappings:
        src = (getattr(m, "source_expression", m) or "").strip()
        if src.startswith("custom."):
            out.add(src[len("custom."):])
    return out

# --- transforms available to a mapping. Pure, total functions: no I/O, no failure. ---

def _t_upper(v): return str(v).upper() if v is not None else None
def _t_lower(v): return str(v).lower() if v is not None else None
def _t_date_iso(v): return v.isoformat() if isinstance(v, (date, datetime)) else v
def _t_date_compact(v): return v.strftime("%Y%m%d") if isinstance(v, (date, datetime)) else v


def _rule_key(rule: dict) -> str:
    """Stable id for a cross-field/format rule. Format: '<kind>:<field1>:<field2>...'.
    Ordering rules with reversed fields get distinct keys so an admin can mute one direction
    without disabling a legitimate rule that happens to share the same kind."""
    return f"{rule['kind']}:" + ":".join(rule.get("fields", []))
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
#     untouched and the change is reversible config. Per-field "text profiles" set how strict the
#     character filter is: a name is strict, a thesis title keeps colons and more punctuation. ---
import re as _re

# profile -> disallowed-character class (everything else is kept; accents kept throughout).
STRIP_PROFILES = {
    "name": r"[^A-Za-zÀ-ÿ '\-]",                       # names: letters, space, apostrophe, hyphen
    "title": r"[^0-9A-Za-zÀ-ÿ '\-.,:;/&()]",           # titles: + digits and richer punctuation
    "general": r"[^0-9A-Za-zÀ-ÿ .,'\-/()]",            # default for other text fields
}

def _make_strip(profile: str):
    rx = _re.compile(STRIP_PROFILES[profile])
    def _fn(v):
        if v is None:
            return None
        return _re.sub(r"\s{2,}", " ", rx.sub("", str(v))).strip()
    return _fn

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
    "strip_name": _make_strip("name"), "strip_title": _make_strip("title"),
    "strip_general": _make_strip("general"),
    "strip_special": _make_strip("general"),   # back-compat alias for the original single strip
    "clamp_pct": _t_clamp_pct,
}


def apply_chain(transform: str | None, raw):
    """Apply a `|`-separated chain of transforms in order (a single name still works). Unknown
    parts are skipped so a bad chain can't crash a return."""
    value = raw
    for name in (transform or "").split("|"):
        name = name.strip()
        if name and name in TRANSFORMS:
            value = TRANSFORMS[name](value)
    return value


def _validate_transform_chain(transform: str | None) -> None:
    """Every part of a `a|b|c` transform chain must be a known transform."""
    if not transform:
        return
    unknown = [t for t in transform.split("|") if t.strip() and t.strip() not in TRANSFORMS]
    if unknown:
        raise WorkflowError(
            f"Unknown transform(s): {', '.join(unknown)}. Available: {', '.join(sorted(TRANSFORMS))}"
        )


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
        "opportunity": "OPPORTUNITY", "opportunity_led": "OPPORTUNITY", "route_a": "OPPORTUNITY",
        "proposal": "PROPOSAL", "student_led": "PROPOSAL", "route_b": "PROPOSAL",
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


def _ev_static(v):
    return v.value if hasattr(v, "value") else v


class _AsKnown:
    """A funding / supervision row as it was known at a moment: the same row with ``valid_to``
    replaced (Phase 7). Read-only, so the real row is never touched."""

    def __init__(self, obj, *, valid_to):
        self._obj = obj
        self.valid_to = valid_to

    def __getattr__(self, name):
        return getattr(self._obj, name)


class StatutoryEngine:
    """Builds a statutory extract purely from configuration."""

    def __init__(self, session: AsyncSession) -> None:
        # What the last build_records() loaded (governance Phase 5 — observable runtime cost).
        self.last_build_stats: dict = {}
        self.session = session

    async def note_usage(self, profile, *, purpose: str, row_count: int) -> None:
        """Record that a return read the custom attributes the last build loaded (governance
        Phase 6). Only for real outputs — a file generated or downloaded, a sign-off — never a
        validation preview. Adds rows; the caller commits."""
        from app.modules.student_record.custom_attr_usage import record_usage

        await record_usage(self.session, keys=self.last_build_stats.get("customKeysLoaded"),
                           profile=profile, purpose=purpose, row_count=row_count)

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
        keyed = {f["field"]: f.get("keyed_at") for f in await resolve_fields(self.session, p.code, p.academic_year)}
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

    async def _check_custom_source(self, source_expression: str | None) -> None:
        """A mapping may only read a live custom attribute: not a request still awaiting a
        decision, a rejected one, or a retired one. Other paths are left to the existing checks."""
        expr = (source_expression or "").strip()
        if not expr.startswith("custom."):
            return
        from app.modules.student_record.custom_fields import Status as CustomStatus
        from app.modules.student_record.models import StudentCustomField

        key = expr[len("custom."):]
        field = (await self.session.execute(
            select(StudentCustomField).where(StudentCustomField.key == key)
        )).scalar_one_or_none()
        if field is None:
            raise ValidationAppError(f"There is no custom attribute '{key}'.")
        if field.status not in CustomStatus.LIVE:
            raise ValidationAppError(
                f"Custom attribute '{field.label}' is {field.status}; only an active attribute can be mapped."
            )

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
        _validate_transform_chain(transform)
        await self._check_custom_source(source_expression)
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

    @staticmethod
    def _year_window(academic_year: str | None) -> tuple[date, date] | None:
        """Parse a HESA-style academic year ('2026/27') into a UK-year window
        (1 Aug of the start year -> 31 Jul of the following year). Returns None for a bad or
        missing value so per-student single-record behaviour still runs."""
        if not academic_year:
            return None
        head = academic_year.split("/", 1)[0].strip()
        if not head.isdigit() or len(head) != 4:
            return None
        y = int(head)
        return date(y, 8, 1), date(y + 1, 7, 31)

    async def build_records(
        self, academic_year: str | None = None, *, as_at: date | None = None,
        known_at: datetime | None = None, custom_keys=None,
    ) -> list[dict]:
        """One flat dict per student — or, when an ``academic_year`` is supplied and the student
        transferred programme mid-year, one dict *per programme period* the student was on during
        that year. Each period's dict resolves ``programme`` from the programme in force for that
        window, so a single student can legitimately appear on the return under both programme
        codes (with the entry/end dates clipped to the period).

        ``custom_keys`` (custom attribute governance, Phase 5): the ``custom.<key>`` attributes the
        caller's mappings read. Only those are loaded and put on each record, so the cost of a
        return follows what it maps, not how many attributes the institution has ever defined.
        ``None`` loads every live attribute (callers with no profile). Either way only *live*
        attributes are read. What was loaded is left on ``self.last_build_stats``.

        This is the *only* contract mappings depend on, so the domain model can evolve without
        breaking every configured return.

        Snapshot (effective dating, Phase 7 — HESA "as at" reporting):
        - ``as_at``: the date the record's values are taken as at (default: the end of the
          reporting year, or today if sooner). Values are those in force on that date.
        - ``known_at``: build the return as the data was *recorded* at that moment. Anything
          entered later — even if back-dated — is left out, so late changes don't bleed into a
          signed-off return. Students enrolled later are left out too."""
        if known_at is not None and known_at.tzinfo is None:
            from datetime import timezone as _tz
            known_at = known_at.replace(tzinfo=_tz.utc)

        def _known(obj) -> bool:
            created = getattr(obj, "created_at", None)
            if known_at is None or created is None:
                return True
            if created.tzinfo is None:
                from datetime import timezone as _tz
                created = created.replace(tzinfo=_tz.utc)
            return created <= known_at

        def _ended_by_then(obj):
            """valid_to as known at ``known_at`` (None if it was ended later)."""
            if known_at is None or obj.valid_to is None:
                return obj
            ended = getattr(obj, "ended_at", None)
            if ended is not None and ended.tzinfo is None:
                from datetime import timezone as _tz
                ended = ended.replace(tzinfo=_tz.utc)
            if ended is not None and ended <= known_at:
                return obj
            return _AsKnown(obj, valid_to=None)
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
        rows = [(st, p) for st, p in rows if _known(st)]
        programmes = {p.id: p for p in (await self.session.execute(select(Programme))).scalars().all()}
        projects = {p.student_id: p for p in (await self.session.execute(select(ResearchProject))).scalars().unique().all()}
        sources = {f.id: f for f in (await self.session.execute(select(FundingSource))).scalars().all()}
        awards = {a.id: a for a in (await self.session.execute(select(ResearchAward))).scalars().all()}
        routes: dict = {}
        for a in (await self.session.execute(select(Application))).scalars().unique().all():
            routes.setdefault(a.person_id, a.route.value if hasattr(a.route, "value") else a.route)
        # Effective dating (Phase 4): every arrangement, so each record takes the one in force in
        # its period — funding that ended during the year is no longer dropped from that year.
        funding: dict = {}
        for fa in (await self.session.execute(
            select(FundingArrangement).order_by(FundingArrangement.valid_from)
        )).scalars().all():
            if _known(fa):
                funding.setdefault(fa.student_id, []).append(_ended_by_then(fa))
        # Supervision (Phase 4): every relationship, with supervisor names.
        from app.modules.supervision.models import SupervisorRelationship
        sup_rows = [_ended_by_then(r) for r in (await self.session.execute(
            select(SupervisorRelationship).order_by(SupervisorRelationship.valid_from)
        )).scalars().all() if _known(r)]
        supervision: dict = {}
        for r in sup_rows:
            supervision.setdefault(r.student_id, []).append(r)
        sup_names: dict = {}
        if sup_rows:
            for p in (await self.session.execute(select(Person).where(
                Person.id.in_({r.supervisor_person_id for r in sup_rows})
            ))).scalars().all():
                sup_names[p.id] = f"{p.given_name} {p.family_name}"

        # Admin-defined custom attributes (HESA gap capture): expose each student's value under the
        # `custom.<key>` path so a mapping can read it. Every key is present (None when unset) so the
        # resolve() contract is deterministic regardless of which students have data entered.
        from app.modules.student_record.custom_fields import Status as CustomStatus
        from app.modules.student_record.models import StudentCustomField, StudentCustomValue
        wanted = None if custom_keys is None else {k for k in custom_keys if k}
        custom_fields: list = []
        if wanted is None or wanted:
            q = select(StudentCustomField).where(StudentCustomField.status.in_(CustomStatus.LIVE))
            if wanted is not None:
                q = q.where(StudentCustomField.key.in_(wanted))
            custom_fields = list((await self.session.execute(q)).scalars().all())
        custom_keys = [f.key for f in custom_fields]
        custom_by_student: dict = {}
        # Effective dating, Phase 6 — attributes that keep history are read as at the record's
        # date; the rest are a single current value.
        tracked_ids = {f.id for f in custom_fields if f.track_history}
        tracked_values: dict = {}   # custom_value_id -> (student_id, key)
        values_loaded = 0
        if custom_fields:
            key_by_id = {f.id: f.key for f in custom_fields}
            for v in (await self.session.execute(
                select(StudentCustomValue).where(StudentCustomValue.custom_field_id.in_(list(key_by_id)))
            )).scalars().all():
                values_loaded += 1
                k = key_by_id.get(v.custom_field_id)
                if k is None:
                    continue
                if v.custom_field_id in tracked_ids:
                    tracked_values[v.id] = (v.student_id, k)
                else:
                    custom_by_student.setdefault(v.student_id, {})[k] = v.value
        custom_periods: dict = {}   # student_id -> key -> periods
        if tracked_values:
            from datetime import timedelta

            from app.modules.student_record.fact_history import CustomValueHistoryService
            from app.modules.student_record.fact_history import today as history_today
            win = self._year_window(academic_year)
            lo = win[0] if win else history_today()
            hi = (win[1] if win else history_today()) + timedelta(days=1)
            for vid, periods in (await CustomValueHistoryService(self.session).periods(
                    list(tracked_values), lo, hi, known_at=known_at)).items():
                sid, k = tracked_values[vid]
                custom_periods.setdefault(sid, {})[k] = periods
        self.last_build_stats = {
            "customScope": "all-live" if wanted is None else "profile",
            "customKeysRequested": sorted(wanted) if wanted is not None else None,
            "customKeysLoaded": sorted(custom_keys),
            # Requested by a mapping but not live (retired, pending, missing) — read as blank.
            "customKeysSkipped": sorted(wanted - set(custom_keys)) if wanted is not None else [],
            "customValuesLoaded": values_loaded,
            "datedCustomValues": len(tracked_values),
        }
        log.info("build_records custom attributes: %s", self.last_build_stats)

        def _custom_for(student_id, as_of: date | None = None) -> dict:
            held = custom_by_student.get(student_id, {})
            dated = custom_periods.get(student_id, {})
            out = {k: held.get(k) for k in custom_keys}
            for k, periods in dated.items():
                day = as_of or history_today()
                out[k] = next((p["value"] for p in periods
                               if p["from"] <= day and (p["to"] is None or p["to"] > day)), None)
            return out

        # ICR G4 — legacy intensity for students who predate intensity history: the latest
        # approved intensity change, else derived from study mode.
        from datetime import timedelta

        from app.modules.student_record.constants import (
            DEFAULT_PART_TIME_INTENSITY_PCT, FULL_TIME_INTENSITY_PCT, STUDYING_STATUSES,
            LifecycleEventStatus, LifecycleEventType, StudyMode,
        )
        from app.modules.student_record.fact_history import (
            IntensityHistoryService, ProgrammeHistoryService, StatusHistoryService,
            mode_for_intensity,
        )
        from app.modules.student_record.fact_history import today as history_today
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

        # Effective dating (Phase 2): status, programme and intensity are read from their history,
        # one query per fact for the whole cohort, for the reporting window [ws, we). Without an
        # academic year the window is just today, so values are as they stand now.
        from app.modules.student_record.lifecycle import LifecycleService

        window = self._year_window(academic_year)
        now = history_today()
        if known_at is not None:
            now = min(now, known_at.date())
        ws, we = (window[0], window[1] + timedelta(days=1)) if window else (now, now + timedelta(days=1))
        year_days = (we - ws).days
        ids = [st.id for st, _ in rows]
        hist_status = await StatusHistoryService(self.session).periods(ids, ws, we, known_at=known_at)
        hist_prog = await ProgrammeHistoryService(self.session).periods(ids, ws, we, known_at=known_at)
        hist_int = await IntensityHistoryService(self.session).periods(ids, ws, we, known_at=known_at)
        from app.modules.student_record.fact_history import FeeStatusHistoryService, LocationHistoryService
        hist_fee = await FeeStatusHistoryService(self.session).periods(ids, ws, we, known_at=known_at)
        hist_loc = await LocationHistoryService(self.session).periods(ids, ws, we, known_at=known_at)
        # Phase 9 — units of assessment: the student's own, and each supervisor's, by period.
        from app.modules.student_record.fact_history import PersonUoaHistoryService, StudentUoaHistoryService
        from app.modules.student_record.models import UnitOfAssessment
        uoa_codes = {u.id: u.code for u in (await self.session.execute(select(UnitOfAssessment))).scalars().all()}
        hist_uoa = await StudentUoaHistoryService(self.session).periods(ids, ws, we, known_at=known_at)
        # Phase 10 — HESA Engagement: the expected end, fee eligibility and "primarily outside the
        # UK" as held on each record's date, and the Leaver (when and why the engagement ended).
        from app.modules.student_record.constants import TERMINAL_STATUSES
        from app.modules.student_record.fact_history import (
            ExpectedEndHistoryService, FeeEligibilityHistoryService, OutsideUkHistoryService,
        )
        from app.modules.student_record.models import StudentLifecycleEvent, StudentStatusHistory
        hist_exp = await ExpectedEndHistoryService(self.session).periods(ids, ws, we, known_at=known_at)
        hist_elig = await FeeEligibilityHistoryService(self.session).periods(ids, ws, we, known_at=known_at)
        hist_ouk = await OutsideUkHistoryService(self.session).periods(ids, ws, we, known_at=known_at)
        leavers: dict = {}   # student_id -> [(left_on, status, reason)]
        if ids:
            lq = (select(StudentStatusHistory, StudentLifecycleEvent.leaver_reason)
                  .outerjoin(StudentLifecycleEvent,
                             StudentLifecycleEvent.id == StudentStatusHistory.source_event_id)
                  .where(StudentStatusHistory.student_id.in_(ids),
                         StudentStatusHistory.superseded_by.is_(None),
                         StudentStatusHistory.status.in_(list(TERMINAL_STATUSES)),
                         StudentStatusHistory.valid_from < we))
            if known_at is not None:
                lq = lq.where(StudentStatusHistory.recorded_at <= known_at)
            for row, why in (await self.session.execute(lq)).all():
                st_value = _ev_static(row.status)
                leavers.setdefault(row.student_id, []).append(
                    (row.valid_from, st_value, why or ("completed" if st_value == "completed" else None)))
        sup_uoa = await PersonUoaHistoryService(self.session).periods(
            list({r.supervisor_person_id for r in sup_rows}), ws, we, known_at=known_at)
        from app.modules.taught.models import ModuleEnrolment, TaughtModule
        from app.modules.taught.module_history import ModuleStatusHistoryService, year_window

        taught_modules = {m.id: m for m in (await self.session.execute(select(TaughtModule))).scalars().all()}
        # Demo 2 item 1.5 — a taught programme's dissertation counts toward the FTE check: the
        # credits its core modules don't cover.
        from app.modules.student_record import fte_check
        core_credits: dict = {}
        for m in taught_modules.values():
            if m.is_core:
                core_credits[m.programme_id] = core_credits.get(m.programme_id, 0) + (m.credits or 0)
        from app.modules.taught.catalogue import effective_fte
        from app.modules.taught.models import ModuleRun, ModuleVersion
        # Phase 8b — the programme version each student is on, per programme (CMA).
        from app.modules.student_record.models import ProgrammeVersion, StudentProgrammePin
        pins = {(sid, pid): f"v{n}" for sid, pid, n in (await self.session.execute(
            select(StudentProgrammePin.student_id, StudentProgrammePin.programme_id, ProgrammeVersion.version_no)
            .join(ProgrammeVersion, ProgrammeVersion.id == StudentProgrammePin.programme_version_id)
        )).all()}
        run_versions = {run_id: v for run_id, v in (await self.session.execute(
            select(ModuleRun.id, ModuleVersion).join(ModuleVersion, ModuleVersion.id == ModuleRun.module_version_id)
        )).all()}
        enrolments: dict = {}
        for e in (await self.session.execute(select(ModuleEnrolment))).scalars().all():
            if _known(e):
                enrolments.setdefault(e.student_id, []).append(e)
        module_status = await ModuleStatusHistoryService(self.session).periods(
            [e.id for es in enrolments.values() for e in es], ws, we, known_at=known_at,
        )
        lifecycle = LifecycleService(self.session) if window else None
        one_day = timedelta(days=1)

        def _slice_as_of(start_d: date, shown_end: date) -> date:
            """A programme period's record is taken as at its own end — or the snapshot date if
            that falls inside the period."""
            if as_at is not None and start_d <= as_at <= shown_end:
                return as_at
            return min(shown_end, now)

        def _on(periods: list[dict], day: date):
            return next((p["value"] for p in periods
                         if p["from"] <= day and (p["to"] is None or p["to"] > day)), None)

        def _load(int_periods: list[dict], st_periods: list[dict], lo: date, hi: date):
            """HESA STULOAD: the FTE the student completed in ``[lo, hi)`` — intensity % times the
            days they were actually studying (suspended / dormant / left days count zero), over the
            days in the reporting year. Full time all year = 100; full time for half of it = 50."""
            if not window or not int_periods or hi <= lo:
                return None
            total = 0.0
            for ip in int_periods:
                a, b = max(ip["from"], lo), min(ip["to"] or hi, hi)
                if b <= a:
                    continue
                if not st_periods:
                    total += ip["value"] * (b - a).days
                    continue
                for sp in st_periods:
                    if sp["value"] not in STUDYING_STATUSES:
                        continue
                    c, d = max(a, sp["from"]), min(b, sp["to"] or b)
                    if d > c:
                        total += ip["value"] * (d - c).days
            return round(total / year_days, 1)

        def _period_ref(base_ref: str, prog_code: str | None, period_start: date) -> str:
            # Row identity: a no-change record keeps the raw student_ref; a per-period record
            # extends it with the programme code + period start so downstream de-dup by ref works.
            return f"{base_ref}::{prog_code or 'NONE'}::{period_start.isoformat()}"

        def _ev(v):
            return v.value if hasattr(v, "value") else v

        records = []
        for student, person in rows:
            proj = projects.get(student.id)
            award = awards.get(proj.research_award_id) if proj and proj.research_award_id else None
            sp = hist_status.get(student.id, [])
            pp = hist_prog.get(student.id, [])
            ip = hist_int.get(student.id, [])
            fp = hist_fee.get(student.id, [])
            lp = hist_loc.get(student.id, [])
            up = hist_uoa.get(student.id, [])
            ep = hist_exp.get(student.id, [])
            eg = hist_elig.get(student.id, [])
            ou = hist_ouk.get(student.id, [])

            # Programme periods inside the window: (start, display end, exclusive end, programme).
            # History periods are half-open; HESA end dates are inclusive, so a period that ends
            # because the next one starts shows the day before (no shared boundary date).
            slices: list[tuple] = []
            if window and pp:
                for i, p in enumerate(pp):
                    end_x = p["to"] or we
                    shown = end_x - one_day
                    if i == len(pp) - 1 and student.expected_end_date is not None:
                        shown = min(shown, student.expected_end_date)
                    slices.append((p["from"], shown, end_x, p["value"]))
            elif window:
                for sl in await lifecycle.programme_periods_for(
                    student, year_start=window[0], year_end=window[1],
                ):
                    slices.append((sl["period_start"], sl["period_end"], sl["period_end"], sl["programme_id"]))
            # Only fan out when the student was demonstrably on more than one programme inside
            # the window; a single period (or a student with no programme change at all) keeps the
            # historical single-record shape, so existing returns validate identically.
            fan_out = len(slices) > 1

            def _student_fields(as_of: date, lo: date, hi: date) -> dict:
                """Status / intensity / mode as they stood on ``as_of`` (history first, cache for
                students who predate it), plus the completed load for ``[lo, hi)``."""
                intensity = _on(ip, as_of) if ip else None
                if intensity is None:
                    intensity = ip[0]["value"] if ip else latest_intensity.get(
                        student.id,
                        FULL_TIME_INTENSITY_PCT if student.study_mode is StudyMode.full_time
                        else DEFAULT_PART_TIME_INTENSITY_PCT,
                    )
                status = (_on(sp, as_of) if sp else None) or student.status
                mode = mode_for_intensity(intensity) if ip else student.study_mode
                return {"status": _ev(status), "mode": _ev(mode), "intensityPct": intensity,
                        "fteLoad": _load(ip, sp, lo, hi),
                        # Phase 6 — optional dated facts; None = not recorded on that date.
                        "feeStatus": _on(fp, as_of), "studyLocation": _on(lp, as_of),
                        # Phase 9 — the student's unit of assessment on that date (code).
                        "uoa": uoa_codes.get(_on(up, as_of))}

            common_student = {
                "originalExpectedEndDate": student.original_expected_end_date,
                "entryRoute": routes.get(student.person_id),
                # HUSID is per-student (not per period) — the person is one student across the
                # return, no matter how many programmes they were on that year.
                "husid": husid(
                    inst_code,
                    student.start_date.year if student.start_date else None,
                    student.student_ref,
                ),
            }
            common_person = {
                "givenName": person.given_name, "familyName": person.family_name,
                "nationality": person.nationality, "email": person.email,
                "dateOfBirth": getattr(person, "date_of_birth", None),
            }
            common_research = {"topic": proj.research_topic if proj else None,
                               "group": proj.research_group if proj else None}
            arrangements = funding.get(student.id, [])
            relationships = supervision.get(student.id, [])

            def _period_fields(lo: date, hi: date, as_of: date, prog=None) -> dict:
                """What was in force for the record's period ``[lo, hi)`` (Phase 4): the funding
                and supervision as at ``as_of``, plus child lists for HESA entity exports
                (status changes, modules, funding periods, supervisors). Child-list dates are
                inclusive like the rest of the record; ``validTo`` None = still in force at the
                end of the period."""
                def overlap(f, t):
                    return f < hi and (t is None or t > lo)

                def on(f, t):
                    return f <= as_of and (t is None or t > as_of)

                def last_day(t):
                    return t - one_day if t is not None and t <= hi else None

                covering = [a for a in arrangements if on(a.valid_from, a.valid_to)]
                within = [a for a in arrangements if overlap(a.valid_from, a.valid_to)]
                fa = (max(covering, key=lambda a: (a.contribution_pct or 100, a.valid_from)) if covering
                      else (within[-1] if within else None))
                # Phase 10 — HESA Engagement (as at the record's date) and Leaver.
                council = [a for a in covering if _ev(a.funding_type) == "research_council"]
                left = [x for x in leavers.get(student.id, []) if lo <= x[0] <= as_of]
                engagement = {
                    "numhus": student.student_ref,
                    "startDate": student.start_date,
                    "expectedEndDate": (_on(ep, as_of) if ep else None) or student.expected_end_date,
                    "feeEligibility": _on(eg, as_of),
                    "primarilyOutsideUk": _on(ou, as_of),
                    "studyIntention": student.study_intention,
                    "incomingExchange": student.incoming_exchange,
                    "researchCouncilStudent": bool(council) if covering else None,
                    "studentshipRef": council[0].funder_reference if council else None,
                }
                leaver = ({"endDate": left[-1][0], "status": left[-1][1], "reason": left[-1][2]} if left
                          else {"endDate": None, "status": None, "reason": None})
                sups_now = [r for r in relationships if on(r.valid_from, r.valid_to)]
                primary = next((r for r in sups_now if _ev(r.role) == "primary"), None)

                modules = []
                studied_fte = []   # exact FTE of the modules not withdrawn, for the FTE check
                for e in enrolments.get(student.id, []):
                    e_from = e.start_date
                    e_to = e.end_date + one_day if e.end_date else None
                    if e_from is None:
                        win = year_window(e.academic_year)
                        if win is None:
                            continue
                        e_from, e_to = win[0], win[1] + one_day
                    if not overlap(e_from, e_to):
                        continue
                    m = taught_modules.get(e.module_id)
                    # Phase 8 — what the student took: the version of their run, not today's.
                    v = run_versions.get(e.module_run_id) if e.module_run_id else None
                    st = _on(module_status.get(e.id, []), as_of) or e.status
                    # Phase 8c — module FTE (HESA): the version's own, or derived from credits.
                    home = programmes.get(m.programme_id) if m else None
                    fte = effective_fte(v if v is not None else m, home.taught_total_credits if home else None)
                    exact_fte = effective_fte(v if v is not None else m,
                                              home.taught_total_credits if home else None, exact=True)
                    if exact_fte is not None and _ev(st) != "withdrawn":
                        studied_fte.append(exact_fte)
                    modules.append({
                        "code": m.code if m else None,
                        "title": v.title if v else (m.title if m else None),
                        "credits": v.credits if v else (m.credits if m else None),
                        "version": f"v{v.version_no}" if v else None,
                        "ftePct": float(fte) if fte is not None else None,
                        "academicYear": e.academic_year,
                        "startDate": e.start_date, "endDate": e.end_date, "status": _ev(st),
                        "outcome": _ev(e.outcome), "mark": e.final_mark,
                    })

                return {
                    "funding": {
                        "type": _ev(fa.funding_type) if fa else None,
                        "source": sources[fa.funding_source_id].name if fa and fa.funding_source_id in sources else None,
                        "amount": fa.stipend_amount if fa else None,
                        "currency": fa.currency if fa else None,
                        "costCentre": fa.cost_centre if fa else None,
                    },
                    "supervision": {
                        "primaryName": sup_names.get(primary.supervisor_person_id) if primary else None,
                        "supervisorCount": len(sups_now),
                        # Phase 9 — the primary supervisor's unit of assessment on that date.
                        "primaryUoa": uoa_codes.get(_on(sup_uoa.get(primary.supervisor_person_id, []), as_of))
                        if primary else None,
                    },
                    "statusHistory": [
                        {"status": _ev(p["value"]), "validFrom": max(p["from"], lo), "validTo": last_day(p["to"])}
                        for p in sp if overlap(p["from"], p["to"])
                    ],
                    "modules": modules,
                    # Phase 8c — total module FTE in the period, for the HESA check that a
                    # student's FTE doesn't exceed the sum of their module FTEs (Demo 2 item 1.5).
                    "engagement": engagement,
                    "leaver": leaver,
                    "taught": {
                        "moduleFteTotal": (
                            round(sum(x["ftePct"] for x in modules if x["ftePct"] is not None), 2)
                            if any(x["ftePct"] is not None for x in modules) else None
                        ),
                        # Modules not withdrawn + the dissertation's share, unrounded until the end.
                        "fteCheckTotal": (
                            float(round(sum(studied_fte, Decimal(0)) + (fte_check.dissertation_fte(
                                prog.taught_total_credits, core_credits.get(prog.id, 0))
                                if prog is not None and _ev(prog.programme_type) == "taught" else 0), 2))
                            if studied_fte else None
                        ),
                    },
                    "fundingPeriods": [
                        {"type": _ev(a.funding_type),
                         "source": sources[a.funding_source_id].name if a.funding_source_id in sources else None,
                         "contributionPct": a.contribution_pct, "amount": a.stipend_amount,
                         "validFrom": max(a.valid_from, lo), "validTo": last_day(a.valid_to)}
                        for a in within
                    ],
                    "supervisors": [
                        {"name": sup_names.get(r.supervisor_person_id), "role": _ev(r.role),
                         "weightingPct": r.weighting_pct,
                         "uoa": uoa_codes.get(_on(sup_uoa.get(r.supervisor_person_id, []),
                                                  min(as_of, last_day(r.valid_to) or as_of))),
                         "validFrom": max(r.valid_from, lo), "validTo": last_day(r.valid_to)}
                        for r in relationships if overlap(r.valid_from, r.valid_to)
                    ],
                }
            common_award = {"ref": award.award_ref if award else None,
                            "title": award.title if award else None}

            if not fan_out:
                # One record for the student (no transfer inside the window).
                prog_id = (slices[0][3] if slices else None) or student.programme_id
                prog = programmes.get(prog_id)
                as_of = as_at if as_at is not None else min(we - one_day, now)
                records.append({
                    "student": {
                        "ref": student.student_ref,
                        **_student_fields(as_of, ws, we),
                        "startDate": student.start_date,
                        "expectedEndDate": student.expected_end_date,
                        **common_student,
                    },
                    "person": common_person,
                    "programme": {"name": prog.name if prog else None, "code": prog.code if prog else None,
                                  "version": pins.get((student.id, prog_id)),
                                  "type": _ev(prog.programme_type) if prog else None},
                    "research": common_research,
                    "award": common_award,
                    "custom": _custom_for(student.id, as_of),
                    **_period_fields(ws, we, as_of, prog),
                })
                continue

            # Per-period fan-out — one record per programme window inside the return year. COMDATE
            # and ENDDATE clip to the period so a student that ran on Programme A until 31 Jan and
            # Programme B from 1 Feb shows the right dates against each row.
            for start_d, shown_end, end_x, prog_id in slices:
                prog = programmes.get(prog_id)
                prog_code = prog.code if prog else None
                records.append({
                    "student": {
                        "ref": _period_ref(student.student_ref, prog_code, start_d),
                        **_student_fields(_slice_as_of(start_d, shown_end), start_d, end_x),
                        "startDate": start_d,
                        "expectedEndDate": shown_end,
                        **common_student,
                    },
                    "person": common_person,
                    "programme": {"name": prog.name if prog else None, "code": prog_code,
                                  "version": pins.get((student.id, prog_id)),
                                  "type": _ev(prog.programme_type) if prog else None},
                    "research": common_research,
                    "award": common_award,
                    "custom": _custom_for(student.id, _slice_as_of(start_d, shown_end)),
                    **_period_fields(start_d, end_x, _slice_as_of(start_d, shown_end), prog),
                })
        return records

    # ---------------- generate + validate ----------------

    async def generate(
        self, profile_id: uuid.UUID, *, as_at: date | None = None, known_at: datetime | None = None,
        issue_limit: int | None = 500, include_records: bool = False,
    ) -> dict:
        """Produce the extract and its validation report, entirely from configuration.
        ``include_records`` also returns the built records (``records[i]`` is ``rows[i]``'s source),
        for the nested XML.
        ``as_at`` / ``known_at`` take a snapshot (see ``build_records``)."""
        profile = await self.get_profile(profile_id)
        if as_at is not None:
            # A snapshot date must fall inside the return's own reporting year: a 2025/26 return
            # "as at" October 2026 would report next year's facts (e.g. a later interruption).
            from app.modules.taught.module_history import year_window

            window = year_window(profile.academic_year)
            if window and not (window[0] <= as_at <= window[1]):
                raise WorkflowError(
                    f"The snapshot date {as_at.isoformat()} is outside the {profile.academic_year} "
                    f"reporting year ({window[0].isoformat()} to {window[1].isoformat()})"
                )
        mappings = await self._mappings(profile_id)
        if not mappings:
            raise WorkflowError("This profile has no field mappings, so it cannot produce a return")

        started = time.perf_counter()
        records = await self.build_records(academic_year=profile.academic_year, as_at=as_at,
                                           known_at=known_at, custom_keys=mapped_custom_keys(mappings))
        build_ms = round((time.perf_counter() - started) * 1000, 1)
        header = [m.target_field for m in mappings]
        rows, issues = [], []

        import re

        from app.modules.exports.spec_resolver import resolve_rules
        spec_rules = await resolve_rules(self.session, profile.code, profile.academic_year)
        from app.modules.student_record import fte_check
        fte_policy = await fte_check.policy(self.session)

        for record in records:
            out_row, ref = [], record["student"]["ref"]
            values: dict[str, str] = {}
            for m in mappings:
                raw = resolve(record, m.source_expression)
                if raw is None and m.default_value is not None:
                    raw = m.default_value
                value = apply_chain(m.transform, raw)
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
            # A rule whose key is suppressed (profile-scope) is skipped entirely. Pack-scope
            # suppressions were already filtered out by resolve_rules; this only handles per-profile.
            # Entries can be dict (new audit shape) or legacy string.
            muted: set[str] = set()
            for e in (profile.muted_rule_keys or []):
                muted.add(e.get("ruleKey") if isinstance(e, dict) else e)
            for rule in spec_rules:
                flds = rule.get("fields", [])
                sev = rule.get("severity", "error")
                key = _rule_key(rule)
                if key in muted:
                    continue
                if rule["kind"] == "order" and len(flds) == 2:
                    a, b = values.get(flds[0], ""), values.get(flds[1], "")
                    if a and b and a > b:  # YYYYMMDD compares correctly as text
                        issues.append({
                            "studentRef": ref, "field": flds[1], "severity": sev,
                            "ruleKey": key,
                            "fix": {"kind": "order",
                                    "otherField": flds[0], "otherValue": a,
                                    "thisField": flds[1], "thisValue": b},
                            "message": f"{flds[1]} ({b}) — {rule.get('message', 'ordering rule failed')} "
                                       f"({flds[0]} is {a}).",
                        })
                elif rule["kind"] == "format_yyyymmdd":
                    for fld in flds:
                        v = values.get(fld, "")
                        if v and not re.fullmatch(r"\d{8}", v):
                            issues.append({
                                "studentRef": ref, "field": fld, "severity": sev,
                                "ruleKey": key,
                                "fix": {"kind": "format_date", "field": fld, "value": v},
                                "message": f"{fld} ('{v}') {rule.get('message', 'must be YYYYMMDD')}.",
                            })
            # Demo 2 item 1.5 — the student's FTE must not exceed their modules' total (setting:
            # statutory.fte_check off / warn / stop).
            if fte_policy.severity:
                msg = fte_check.evaluate(
                    record["student"].get("intensityPct"), (record.get("taught") or {}).get("fteCheckTotal"),
                    fte_policy, is_research=(record.get("programme") or {}).get("type") != "taught")
                if msg:
                    issues.append({"studentRef": ref, "field": "FTE", "severity": fte_policy.severity,
                                   "ruleKey": "fte_vs_module_fte", "message": msg})
            rows.append(out_row)

        # ruleAnalysis lets the UI say "85% of records violate this rule — probably the rule is
        # wrong (from an accepted advisory)" and offer a one-click suppress, instead of hunting
        # through 8000 error rows.
        rule_analysis: dict[str, dict] = {}
        for rule in spec_rules:
            key = _rule_key(rule)
            violations = sum(1 for i in issues if i.get("ruleKey") == key)
            if violations == 0:
                continue
            share = violations / len(rows) if rows else 0
            rule_analysis[key] = {
                "ruleKey": key, "kind": rule["kind"], "fields": rule.get("fields", []),
                "message": rule.get("message", ""), "severity": rule.get("severity", "error"),
                "violations": violations, "total": len(rows), "share": share,
                # Heuristic: if a rule fails on more than half the population, it's almost
                # certainly misconfigured (a genuine rule catches outliers, not the majority).
                "likelyMisconfigured": share > 0.5,
                "suppressed": key in muted,   # profile-scope only; pack-scope rules never appear here
            }

        # Full audit record for every suppression (profile + pack), for the sign-off card.
        suppressions = await self._collect_suppressions(profile)

        # Cap the raw issue list returned to the UI — on a real cohort with several unmapped
        # mandatory fields this is tens of thousands of rows. Counts, valid and ruleAnalysis are
        # computed from the FULL list above, so nothing is lost; the UI shows the first slice and
        # (via issuesTruncated/issueCount) offers to download the rest.
        MAX_ISSUES = issue_limit if issue_limit is not None else len(issues)
        errors = sum(1 for i in issues if i["severity"] == "error")
        warnings = sum(1 for i in issues if i["severity"] == "warning")
        extra = {"records": records} if include_records else {}
        return {
            **extra,
            "profile": self.profile_out(profile),
            # What the return actually loaded and how long building the records took.
            "runtime": {**self.last_build_stats, "recordCount": len(records), "buildMs": build_ms},
            "asAt": as_at.isoformat() if as_at else None,
            "knownAt": known_at.isoformat() if known_at else None,
            "header": header,
            "rows": rows,
            "rowCount": len(rows),
            "validation": {
                "errors": errors,
                "warnings": warnings,
                "issueCount": len(issues),
                "issuesTruncated": len(issues) > MAX_ISSUES,
                "issues": issues[:MAX_ISSUES],
                # Sign-off blocks on any error — an unmapped required field, a bad coding value, or
                # a failed error-severity rule (e.g. ENDDATE < COMDATE). Warning-severity rules are
                # advisory and do not block.
                "valid": errors == 0,
                "ruleAnalysis": list(rule_analysis.values()),
                "suppressions": suppressions,
            },
        }

    async def suppress_rule(
        self,
        profile_id: uuid.UUID,
        *,
        rule_key: str,
        reason: str,
        scope: str,          # 'profile' | 'pack'
        user_id: uuid.UUID,
        user_name: str,
    ) -> dict:
        """Suppress a validation rule with a full audit record. Reason is REQUIRED — a suppression
        without a stated reason is a silent workaround, not a decision the auditor can review.

        Two scopes:
          - ``profile``: inhibits the rule for THIS profile only. Original spec pack untouched, so
            other profiles keep enforcing it. Refused on a signed-off profile.
          - ``pack``:    inhibits the rule for EVERY profile that uses the pack's currently active
            version. This is the right fix when the rule is broken for everyone (typical case: an
            accepted advisory shipped an inverted rule). Requires an accepted spec version — if
            only the baseline (code constant) is in play there's no DB row to edit, and we refuse
            with a clear message.
        """
        from datetime import datetime, timezone

        from sqlalchemy.orm.attributes import flag_modified

        from app.modules.exports.spec_resolver import active_version_for_code

        reason = (reason or "").strip()
        if not reason:
            raise ValidationAppError("A reason is required — say why the rule is being suppressed.")
        if scope not in {"profile", "pack"}:
            raise ValidationAppError(f"Unknown suppression scope '{scope}'.")

        profile = await self.get_profile(profile_id)
        if profile.signed_off_at is not None:
            raise WorkflowError(f"Profile {profile.code} is signed off — unsign first.")
        now = datetime.now(timezone.utc).isoformat()

        if scope == "profile":
            current = list(profile.muted_rule_keys or [])
            # Skip duplicates by ruleKey so re-clicking Suppress doesn't stack records.
            if not any(isinstance(e, dict) and e.get("ruleKey") == rule_key for e in current):
                current.append({
                    "ruleKey": rule_key, "reason": reason, "at": now,
                    "byUserId": str(user_id), "byUserName": user_name,
                })
            profile.muted_rule_keys = current
            flag_modified(profile, "muted_rule_keys")
        else:  # scope == 'pack'
            version = await active_version_for_code(self.session, profile.code, profile.academic_year)
            if version is None:
                raise WorkflowError(
                    "Pack-level suppression needs an accepted spec version — this pack is still "
                    "on the shipped baseline. Suppress per profile, or accept an advisory that "
                    "removes the rule."
                )
            # Promote to a dict shape carrying the same audit fields as profile-scope suppressions.
            # Legacy string entries persist as-is (see _collect_suppressions for the read side);
            # we only skip duplicates so re-clicking Suppress doesn't stack records.
            entries = list(version.disabled_rule_keys or [])
            already = any(
                (isinstance(e, dict) and e.get("ruleKey") == rule_key) or e == rule_key
                for e in entries
            )
            if not already:
                entries.append({
                    "ruleKey": rule_key, "reason": reason, "at": now,
                    "byUserId": str(user_id), "byUserName": user_name,
                })
            version.disabled_rule_keys = entries
            flag_modified(version, "disabled_rule_keys")

        await self.session.commit()
        await self.session.refresh(profile)
        return {"profileId": str(profile.id), "scope": scope, "ruleKey": rule_key,
                "suppressions": await self._collect_suppressions(profile)}

    async def remove_suppression(
        self, profile_id: uuid.UUID, *, rule_key: str, scope: str,
    ) -> dict:
        """Undo a suppression at the given scope. Refused on a signed-off profile for scope=profile
        (it would change what was attested to); pack-level undo is always allowed since a pack version
        isn't itself signed off."""
        from sqlalchemy.orm.attributes import flag_modified

        from app.modules.exports.spec_resolver import active_version_for_code

        profile = await self.get_profile(profile_id)

        if scope == "profile":
            if profile.signed_off_at is not None:
                raise WorkflowError(f"Profile {profile.code} is signed off — unsign first.")
            kept = [e for e in (profile.muted_rule_keys or [])
                    if not (isinstance(e, dict) and e.get("ruleKey") == rule_key) and e != rule_key]
            profile.muted_rule_keys = kept
            flag_modified(profile, "muted_rule_keys")
        elif scope == "pack":
            version = await active_version_for_code(self.session, profile.code, profile.academic_year)
            if version is not None:
                # Handle both new dict entries and legacy string entries.
                kept = [
                    e for e in (version.disabled_rule_keys or [])
                    if not (isinstance(e, dict) and e.get("ruleKey") == rule_key) and e != rule_key
                ]
                version.disabled_rule_keys = kept
                flag_modified(version, "disabled_rule_keys")
        else:
            raise ValidationAppError(f"Unknown suppression scope '{scope}'.")

        await self.session.commit()
        await self.session.refresh(profile)
        return {"profileId": str(profile.id), "scope": scope, "ruleKey": rule_key,
                "suppressions": await self._collect_suppressions(profile)}

    async def _collect_suppressions(self, profile: ReportProfile) -> list[dict]:
        """Merge profile-level and pack-level suppressions into one auditable list. Legacy string
        entries (from before the audit column existed) come back as reason=None with a note."""
        from app.modules.exports.spec_resolver import active_version_for_code

        out: list[dict] = []
        for e in profile.muted_rule_keys or []:
            if isinstance(e, dict):
                out.append({**e, "scope": "profile"})
            else:
                # Legacy string entry — synthesise a placeholder record for the audit UI.
                out.append({"ruleKey": e, "reason": None, "at": None,
                            "byUserId": None, "byUserName": "legacy (before audit)",
                            "scope": "profile"})
        version = await active_version_for_code(self.session, profile.code, profile.academic_year)
        if version is not None:
            for e in (version.disabled_rule_keys or []):
                if isinstance(e, dict):
                    out.append({**e, "scope": "pack"})
                else:
                    # Legacy string entry from before the pack-scope audit trail existed.
                    out.append({"ruleKey": e, "reason": None, "at": None,
                                "byUserId": None, "byUserName": "legacy (before audit)",
                                "scope": "pack"})
        return out

    # ---------------- ICR G5 — data-quality fix assistant (suggest → accept → apply) ----------------

    async def fix_suggestions(self, profile_id: uuid.UUID) -> dict:
        """Scan the return's produced values for known data-quality issues and, for each, propose a
        deterministic fix from the resolution dictionary — with affected count and before→after
        samples. Nothing is changed here; this is the 'suggest' half."""
        from app.modules.exports.resolutions import RESOLUTIONS, detect

        profile = await self.get_profile(profile_id)
        mappings = await self._mappings(profile_id)
        records = await self.build_records(custom_keys=mapped_custom_keys(mappings))

        groups: dict[tuple[str, str], dict] = {}
        for record in records:
            ref = record["student"]["ref"]
            for m in mappings:
                raw = resolve(record, m.source_expression)
                if raw is None and m.default_value is not None:
                    raw = m.default_value
                value = apply_chain(m.transform, raw)
                text = "" if value is None else str(value)
                found = detect(m, text)   # {"type", "transform"} per field, or None
                if not found:
                    continue
                kind, fix_t = found["type"], found["transform"]
                g = groups.setdefault((m.target_field, kind), {
                    "field": m.target_field, "type": kind, "transform": fix_t, "count": 0, "samples": [],
                })
                g["count"] += 1
                if len(g["samples"]) < 5:
                    # Preview the fix chained onto the field's existing transforms, not in isolation.
                    chained = f"{m.transform}|{fix_t}" if m.transform else fix_t
                    after = apply_chain(chained, raw)
                    g["samples"].append({
                        "studentRef": ref, "before": text,
                        "after": "" if after is None else str(after),
                    })

        out = []
        for (_field, kind), g in groups.items():
            r = RESOLUTIONS[kind]
            out.append({**g, "label": r["label"], "description": r["description"],
                        "applicable": True})
        out.sort(key=lambda x: -x["count"])
        return {"profile": self.profile_out(profile), "suggestions": out}

    async def apply_fix(self, profile_id: uuid.UUID, *, field: str, transform: str) -> dict:
        """Apply an accepted fix by APPENDING its transform to the field's chain (so a cleaning fix
        adds to, rather than replaces, any existing transform like upper/date). Cleans the return
        output (non-destructive, reversible); refuses on a signed-off profile."""
        from app.modules.exports.resolutions import VALID_FIX_TRANSFORMS

        if transform not in VALID_FIX_TRANSFORMS:
            raise WorkflowError(f"Unknown fix transform '{transform}'")
        mappings = await self._mappings(profile_id)
        m = next((x for x in mappings if x.target_field == field), None)
        if m is None:
            raise NotFoundError(f"No mapping for field '{field}'")
        chain = [t for t in (m.transform or "").split("|") if t]
        if transform not in chain:
            chain.append(transform)
        new_chain = "|".join(chain)
        await self.update_field(profile_id, m.id, transform=new_chain)
        return {"field": field, "transform": transform, "chain": new_chain, "applied": True}

    # ---------------- ICR — intelligent default suggestions ----------------

    async def suggest_defaults(self, profile_id: uuid.UUID) -> dict:
        """Evidence-based default suggestions — the system inspects the actual student records the
        return will cover and, per field, proposes the value the data *already* points to.

        The picks are deterministic and rooted in evidence, not opinion:

          1. **Look at the real data.** Produce every record's value for the field (via the same
             resolve/transform chain used at Generate time). Compute the distribution: total /
             populated / empty / unique / top-N values with counts.
          2. **If the population has a dominant value** (mode covers > MODE_THRESHOLD of the
             populated records), suggest it. The reason cites the evidence:
               "402 of 670 records (60%) already use this — safe default for the empty rest."
          3. **If nothing dominates** but the frame publishes a "not known"-style code
             (98 / 99 / ZZ / 00 / unknown / other), fall back to that with a clear reason.
          4. **If neither applies** — no dominant value, no unknown code, date field, or free-text
             with no coding frame — skip with a reason explaining why. The Suggested list is
             therefore never a guess.

        The AI layer is deliberately **not** in the picking loop: it was opinion-based and slow
        (4.6s per request, LLM roundtrip per field). This runs in ~one DB fetch, no roundtrips.
        """
        from app.modules.exports.spec_resolver import resolve_fields

        profile = await self.get_profile(profile_id)
        mappings = await self._mappings(profile_id)
        records = await self.build_records(custom_keys=mapped_custom_keys(mappings))
        keyed = {f["field"]: f.get("keyed_at") for f in await resolve_fields(self.session, profile.code, profile.academic_year)}

        NOT_KNOWN_HINTS = ["98", "99", "ZZ", "00", "unknown", "not known", "prefer not", "other"]
        DATE_TRANSFORMS = {"date_compact", "date_iso", "year"}
        MODE_THRESHOLD = 0.5   # mode must cover > 50% of populated records to win outright
        TOP_N = 3              # how many top values to surface as evidence

        def pick_not_known(allowed: list[str]) -> str | None:
            for hint in NOT_KNOWN_HINTS:
                for v in allowed:
                    if hint.lower() in str(v).lower():
                        return v
            return None

        suggestions = []
        for m in mappings:
            allowed = list(m.allowed_values or [])
            transform_parts = {t.strip() for t in (m.transform or "").split("|") if t.strip()}
            is_date = bool(transform_parts & DATE_TRANSFORMS) or m.target_field.upper().endswith(("DATE", "DTE", "DOB"))
            keyed_at = keyed.get(m.target_field)

            # Compute the actual value distribution across the records this return covers. We use
            # the SAME resolve/transform chain the Generate step uses, so the "existing values" are
            # exactly what the return would ship today (before any default kicks in).
            counts: dict[str, int] = {}
            populated = 0
            for record in records:
                raw = resolve(record, m.source_expression) if m.source_expression else None
                value = apply_chain(m.transform, raw) if raw is not None else None
                text = "" if value is None else str(value).strip()
                if text:
                    populated += 1
                    counts[text] = counts.get(text, 0) + 1
            total = len(records)
            empty = total - populated
            ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:TOP_N]
            evidence = {
                "total": total, "populated": populated, "empty": empty,
                "unique": len(counts),
                "topValues": [{"value": v, "count": c} for v, c in ranked],
            }

            entry = {
                "field": m.target_field,
                "mappingId": str(m.id),
                "keyedAt": keyed_at,
                "required": m.required,
                "current": m.default_value,
                "allowedValues": allowed,
                "evidence": evidence,
            }

            # Already covered — surface as info, not actionable.
            if m.default_value:
                suggestions.append({**entry, "suggested": None, "source": "skip",
                                    "reason": "Already has a default.", "applicable": False})
                continue

            # 1) Dominant value in the population.
            if ranked:
                top_val, top_count = ranked[0]
                share = top_count / populated if populated else 0
                if share > MODE_THRESHOLD and (not allowed or top_val in allowed):
                    pct = round(share * 100)
                    suggestions.append({
                        **entry, "suggested": top_val, "source": "data",
                        "reason": f"{top_count} of {populated} populated records ({pct}%) already use this — "
                                  f"safe default for the {empty} empty record{'s' if empty != 1 else ''}.",
                        "applicable": True,
                    })
                    continue

            # 2) Coded frame with an "unknown"-style code — the safe HESA fallback.
            if allowed:
                unknown = pick_not_known(allowed)
                if unknown:
                    reason = (f"No dominant value in the cohort (top: "
                              f"{', '.join(f'{v}={c}' for v, c in ranked[:2]) if ranked else 'no data'}); "
                              f"'{unknown}' is the frame's 'not known / other' code.")
                    suggestions.append({**entry, "suggested": unknown, "source": "convention",
                                        "reason": reason, "applicable": True})
                    continue
                # Coded but no unknown code and no dominant value — don't guess.
                suggestions.append({**entry, "suggested": None, "source": "skip",
                                    "reason": "No dominant value and no 'not known' code in the frame — pick manually.",
                                    "applicable": False})
                continue

            # 3) Date field — never default (a made-up date would falsify the return).
            if is_date:
                suggestions.append({**entry, "suggested": None, "source": "skip",
                                    "reason": "Date field — a fixed default would falsify the return; leave empty or fix per record.",
                                    "applicable": False})
                continue

            # 4) Free-text with no dominant value and no coding frame — no safe default.
            reason = ("Free-text field with no dominant value in the cohort — set one manually if needed."
                      if m.required else "Optional free-text field — empty is fine.")
            suggestions.append({**entry, "suggested": None, "source": "skip",
                                "reason": reason, "applicable": False})

        applicable = [s for s in suggestions if s["applicable"]]
        return {
            "profile": self.profile_out(profile),
            "suggestions": sorted(suggestions, key=lambda s: (not s["applicable"], s["field"])),
            "applicableCount": len(applicable),
        }

    async def apply_defaults(self, profile_id: uuid.UUID, picks: list[dict]) -> dict:
        """Apply the accepted suggestions in one call. Each pick is ``{field, value}``. Refused
        for a signed-off profile (via the underlying update_field guard). Returns the count applied."""
        mappings = await self._mappings(profile_id)
        by_field = {m.target_field: m for m in mappings}
        applied: list[str] = []
        for pick in picks:
            fld, val = pick.get("field"), pick.get("value")
            m = by_field.get(fld)
            if m is None or not val:
                continue
            await self.update_field(profile_id, m.id, default_value=str(val))
            applied.append(fld)
        return {"applied": applied, "count": len(applied)}

    # ---------------- F1 — sign-off, immutability, mandatory-spec gates ----------------

    async def compile(self, profile_id: uuid.UUID) -> dict:
        """Return the mandatory-field gap between the profile and the return's published spec.

        A profile can only be signed off when this returns no ``missing`` entries. Each entry names
        the exact spec field and the coding frame (if any) the profile would need to satisfy.
        """
        from app.modules.exports.spec_resolver import resolve_fields

        profile = await self.get_profile(profile_id)
        mappings = await self._mappings(profile_id)
        # A field is "missing" only when it is absent from the profile — present fields (even with
        # an empty source) are surfaced in the Fields tab. But a present-but-unmapped REQUIRED field
        # still can't be signed off, so it is tracked separately and folded into readiness. Without
        # this, adding an absent required field as an unmapped placeholder would clear `missing` and
        # the UI would wrongly say "ready to sign off".
        present = {m.target_field for m in mappings}
        mapped = {m.target_field for m in mappings if (m.source_expression or "").strip()}
        # A required field is satisfied for sign-off when it produces a value — from a source OR a
        # default (the default fills an empty source, see generate()). So it only blocks when it has
        # neither. This mirrors validation, so the readiness the UI shows matches what sign-off does.
        def _resolved(m) -> bool:
            return bool((m.source_expression or "").strip()) or bool((m.default_value or "").strip())
        unmapped_required = sorted(
            m.target_field for m in mappings if m.required and not _resolved(m)
        )
        spec = await resolve_fields(self.session, profile.code, profile.academic_year)
        from app.modules.exports.custom_mapping import obsolete_mappings
        obsolete = await obsolete_mappings(self.session, profile, mappings)
        # Carry the spec's recommended source/transform/default through so the "Map" affordance
        # on the sign-off tab can offer a one-click map for fields the spec pack already knows how
        # to source (avoids the modal-and-a-form-for-every-row UX complaint from ICR testing).
        missing = [
            {
                "field": s["field"],
                "description": s.get("description", ""),
                "allowed": s.get("allowed"),
                "specDefaultSource": s.get("source") or None,
                "specDefaultTransform": s.get("transform") or None,
                "specDefaultValue": s.get("default") or None,
            }
            for s in spec if s["field"] not in present
        ]
        return {
            "profile": self.profile_out(profile),
            "specCode": profile.code,
            "specFieldCount": len(spec),
            # Of the specification's fields, how many this profile maps (not every profile field:
            # "14 / 5" compared a count of all fields with a count of spec fields).
            "mappedFieldCount": sum(1 for f in spec if f["field"] in mapped),
            "missing": missing,
            # Present-but-unmapped required fields — not "missing" (they're in the Fields tab) but
            # they still block sign-off. The UI shows a pointer to the Fields tab for these.
            "unmappedRequired": unmapped_required,
            # Custom attribute governance, Phase 4 — a mapping to a retired / never-live / deleted
            # custom attribute would quietly read blank, so it blocks sign-off until re-mapped.
            "obsoleteMappings": obsolete,
            "signOffReady": (not missing) and (not unmapped_required) and (not obsolete) and bool(mappings),
            # Suppressed rules are attested to at sign-off, so surface them wherever the sign-off
            # UI is rendered — not only inside a validation result.
            "suppressions": await self._collect_suppressions(profile),
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
        if changes.get("transform"):
            _validate_transform_chain(changes["transform"])
        if changes.get("source_expression") and changes["source_expression"] != m.source_expression:
            await self._check_custom_source(changes["source_expression"])
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
        # A field the specification marks required must not be silently removed — dropping it
        # produces a structurally-invalid return. If the reason is that we don't hold the data,
        # add a custom student attribute and map to it instead of deleting the field.
        if m.required:
            raise ConflictError(
                f"'{m.target_field}' is required by the specification and cannot be deleted. "
                "Re-map it to a different source (or a custom student attribute) instead."
            )
        await self.session.delete(m)
        await self.session.commit()

    async def sign_off(
        self, profile_id: uuid.UUID, *, user_id: uuid.UUID, notes: str | None = None,
        as_at: date | None = None,
    ) -> ReportProfile:
        """Attest the profile is complete for the return. Blocks if the spec is not satisfied
        or if the current cohort would produce validation errors."""
        from datetime import datetime, timezone

        profile = await self.get_profile(profile_id)
        if profile.signed_off_by is not None:
            raise ConflictError("Profile is already signed off")
        report = await self.compile(profile_id)
        if not report["signOffReady"]:
            obsolete = report.get("obsoleteMappings", [])
            if obsolete:
                raise WorkflowError(
                    "Cannot sign off: " + "; ".join(f"{o['targetField']} reads {o['sourceExpression']} — {o['reason']}"
                                                   for o in obsolete[:5])
                    + " Re-map these fields first."
                )
            blockers = [m["field"] for m in report["missing"]] + report.get("unmappedRequired", [])
            if blockers:
                shown = ", ".join(blockers[:8])
                more = "" if len(blockers) <= 8 else f" (+{len(blockers) - 8} more)"
                raise WorkflowError(
                    f"Cannot sign off: {len(blockers)} mandatory field(s) unmapped: {shown}{more}"
                )
            raise WorkflowError("Cannot sign off: profile has no field mappings")
        signed_at = datetime.now(timezone.utc)
        gen = await self.generate(profile_id, as_at=as_at, known_at=signed_at)
        await self.note_usage(profile, purpose="sign_off", row_count=gen["rowCount"])
        if not gen["validation"]["valid"]:
            raise WorkflowError(
                f"Cannot sign off: {gen['validation']['errors']} validation error(s) in the current "
                "cohort. Fix them, or reduce cohort scope, then retry."
            )
        profile.signed_off_by = user_id
        profile.signed_off_at = signed_at
        profile.signed_off_notes = notes
        # Phase 7 — freeze exactly what was attested, so later data changes can't alter it.
        await self._store_version(profile, gen, as_at=as_at, known_at=signed_at, user_id=user_id)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    # ---------------- frozen returns (Phase 7) ----------------

    async def _store_version(self, profile: ReportProfile, gen: dict, *, as_at: date | None,
                             known_at: datetime, user_id: uuid.UUID | None,
                             reason: str = "sign_off") -> None:
        from sqlalchemy import func

        from app.modules.exports.models import ReportReturnVersion

        last = (await self.session.execute(
            select(func.max(ReportReturnVersion.version_no))
            .where(ReportReturnVersion.profile_id == profile.id)
        )).scalar()
        self.session.add(ReportReturnVersion(
            profile_id=profile.id, version_no=(last or 0) + 1, academic_year=profile.academic_year,
            as_at=as_at, known_at=known_at, reason=reason, created_by_user_id=user_id,
            created_at=datetime.now(timezone.utc),
            header=gen["header"], rows=gen["rows"], row_count=gen["rowCount"],
            errors=gen["validation"]["errors"], warnings=gen["validation"]["warnings"],
        ))

    @staticmethod
    def version_out(v) -> dict:
        return {
            "id": str(v.id), "profileId": str(v.profile_id), "versionNo": v.version_no,
            "academicYear": v.academic_year, "asAt": v.as_at.isoformat() if v.as_at else None,
            "knownAt": v.known_at.isoformat() if v.known_at else None, "reason": v.reason,
            "createdAt": v.created_at.isoformat() if v.created_at else None,
            "createdByUserId": str(v.created_by_user_id) if v.created_by_user_id else None,
            "rowCount": v.row_count, "errors": v.errors, "warnings": v.warnings,
        }

    async def versions(self, profile_id: uuid.UUID) -> list:
        from app.modules.exports.models import ReportReturnVersion

        await self.get_profile(profile_id)
        return list((await self.session.execute(
            select(ReportReturnVersion).where(ReportReturnVersion.profile_id == profile_id)
            .order_by(ReportReturnVersion.version_no.desc())
        )).scalars().all())

    async def get_version(self, profile_id: uuid.UUID, version_id: uuid.UUID):
        from app.modules.exports.models import ReportReturnVersion

        v = await self.session.get(ReportReturnVersion, version_id)
        if v is None or v.profile_id != profile_id:
            raise NotFoundError("Return version not found")
        return v

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
