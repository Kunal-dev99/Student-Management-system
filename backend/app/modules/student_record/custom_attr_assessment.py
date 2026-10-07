"""Custom attribute governance, Phase 2 — is a requested attribute actually needed?

Three checks, all deterministic (no model call; plan P7: AI is advisory and never a dependency):

- **Duplicate check** — against the core record (the mapping catalogue, ``RECORD_SCHEMA``) and the
  other custom attributes. ``exact`` means the same thing already exists; ``near`` means it may.
- **HESA check** — against every active statutory spec pack (baseline + accepted advisories, via
  ``spec_resolver``). A HESA field code named in the label or reason (e.g. ``CARELEAVER``) is a
  direct match; otherwise the field descriptions are compared with the label. The result says
  whether the field is required, and whether the spec already sources it from the core record
  (in which case a custom attribute is probably not needed).
- **Type inference** — a coded HESA field suggests ``code`` plus its allowed values; otherwise the
  wording of the label suggests a type.

The outcome is a ``verdict``: ``duplicate`` (an exact match exists), ``review`` (something
needs a human look), ``supported`` (a HESA field needs it and nothing duplicates it) or
``no_hesa_basis`` (no statutory field found — may still be legitimate, e.g. an internal return).
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.exports.record_schema import RECORD_SCHEMA
from app.modules.student_record.models import StudentCustomField

# Words that carry no meaning for matching ("care leaver flag" ≈ "care leaver").
_STOP = {
    "a", "an", "and", "the", "of", "for", "to", "in", "on", "at", "by", "or", "is",
    "student", "person", "flag", "indicator", "value", "field", "hesa", "attribute", "custom",
    "record", "code", "type", "detail", "details", "yes", "no",
}
_WORD = re.compile(r"[a-z0-9]+")
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")
_HESA_CODE = re.compile(r"\b[A-Z][A-Z0-9]{3,}\b")

EXACT, NEAR = "exact", "near"


def _tokens(text: str) -> set[str]:
    out = set()
    for w in _WORD.findall(_CAMEL.sub(" ", text or "").lower()):
        if w in _STOP:
            continue
        out.add(w[:-1] if len(w) > 4 and w.endswith("s") else w)   # crude plural fold
    return out


def _same_word(a: str, b: str) -> bool:
    """Same word, allowing a shared stem ("ethnic"/"ethnicity") or a small typo."""
    if a == b:
        return True
    if min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)):
        return True
    return min(len(a), len(b)) >= 5 and SequenceMatcher(None, a, b).ratio() >= 0.88


def similarity(a: str, b: str) -> float:
    """0..1 — the share of meaningful words on each side that the other side also has.
    Word-level on purpose: character similarity over whole phrases calls "Refugee status" a
    near match for "Fee status"."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    hit_a = sum(1 for x in ta if any(_same_word(x, y) for y in tb))
    hit_b = sum(1 for y in tb if any(_same_word(x, y) for x in ta))
    return round((hit_a + hit_b) / (len(ta) + len(tb)), 3)


def coverage(label: str, text: str) -> float:
    """0..1 for matching a short label against a longer description: mostly "how much of the
    label does the description say", tempered by the symmetric score so one generic word
    doesn't match everything."""
    tl, tt = _tokens(label), _tokens(text)
    if not tl or not tt:
        return 0.0
    covered = sum(1 for x in tl if any(_same_word(x, y) for y in tt)) / len(tl)
    return round(0.7 * covered + 0.3 * similarity(label, text), 3)


def _grade(score: float) -> str | None:
    if score >= 0.99:
        return EXACT
    if score >= 0.7:
        return NEAR
    return None


def _core_candidates():
    for g in RECORD_SCHEMA:
        for f in g.fields:
            # "Student · start date" → "start date"; also the path leaf ("startDate").
            plain = f.label.split("·", 1)[-1].strip()
            yield f.path, plain, f.label, f.type


def _infer_type(label: str, hesa: dict | None) -> tuple[str, list[str]]:
    if hesa and hesa.get("allowed"):
        return "code", list(hesa["allowed"])
    words = _tokens(label) | (_tokens(hesa.get("description", "")) if hesa else set())
    text = f"{label} {hesa.get('description', '') if hesa else ''}".lower()
    if "yyyymmdd" in text or words & {"date", "dob", "birth", "dte", "dt"}:
        return "date", []
    if words & {"number", "count", "percent", "percentage", "fte", "amount", "total", "year"}:
        return "number", []
    if any(w in label.lower() for w in ("flag", "indicator", "status", "code", "marker")):
        return "code", []
    return "string", []


async def _spec_fields(session: AsyncSession) -> list[dict]:
    """Every field of every active spec pack, tagged with the pack it came from."""
    from app.modules.exports.spec_resolver import resolve_list_packs, resolve_pack

    out = []
    for p in await resolve_list_packs(session):
        pack = await resolve_pack(session, p["key"])
        if not pack:
            continue
        for f in pack.get("fields", []):
            out.append({
                "pack": pack["code"], "academicYear": pack["academic_year"], "version": pack["version"],
                "field": f.get("field", ""), "description": f.get("description", ""),
                "allowed": list(f.get("allowed") or []), "required": f.get("required", True),
                "source": f.get("source", "") or "", "keyedAt": f.get("keyed_at", ""),
            })
    return out


async def assess(
    session: AsyncSession, *, label: str, reason: str = "", data_type: str | None = None,
    exclude_field_id=None,
) -> dict:
    label = (label or "").strip()
    reason = (reason or "").strip()

    # --- duplicate check: core record ------------------------------------------------------
    core = []
    for path, plain, full, ftype in _core_candidates():
        score = max(similarity(label, plain), similarity(label, path.split(".", 1)[-1]))
        grade = _grade(score)
        if grade:
            core.append({"path": path, "label": full, "type": ftype, "score": score, "match": grade})
    core.sort(key=lambda m: -m["score"])

    # --- duplicate check: other custom attributes ------------------------------------------
    from app.modules.student_record.custom_fields import slugify

    custom = []
    key = slugify(label)
    for f in (await session.execute(select(StudentCustomField))).scalars().all():
        if exclude_field_id is not None and f.id == exclude_field_id:
            continue
        score = 1.0 if f.key == key else similarity(label, f.label)
        grade = _grade(score)
        if grade:
            custom.append({"id": str(f.id), "key": f.key, "label": f.label, "status": f.status,
                           "score": score, "match": grade})
    custom.sort(key=lambda m: -m["score"])

    # --- HESA check ------------------------------------------------------------------------
    named = set(_HESA_CODE.findall(f"{label} {reason}"))
    hesa_hits = []
    for sf in await _spec_fields(session):
        if sf["field"] in named:
            hesa_hits.append({**sf, "score": 1.0, "match": EXACT, "how": "named"})
            continue
        score = coverage(label, sf["description"])
        grade = _grade(score)
        if grade:
            hesa_hits.append({**sf, "score": score, "match": grade, "how": "description"})
    # Best first; on a tie prefer the latest academic year / version.
    hesa_hits.sort(key=lambda h: (h["score"], h["academicYear"], h["version"]), reverse=True)
    hesa = hesa_hits[0] if hesa_hits else None
    if hesa is None:
        requirement = "not_found"
    elif hesa["source"]:
        requirement = "already_sourced"
    else:
        requirement = "required" if hesa["required"] else "optional"

    suggested_type, suggested_values = _infer_type(label, hesa)

    # --- verdict ---------------------------------------------------------------------------
    flags = []
    if any(m["match"] == EXACT for m in core):
        flags.append(f"The core record already holds this: {core[0]['path']}.")
    if any(m["match"] == EXACT for m in custom):
        m = next(m for m in custom if m["match"] == EXACT)
        flags.append(f"A custom attribute already covers this: '{m['label']}' ({m['status']}).")
    near_core = [m for m in core if m["match"] == NEAR]
    near_custom = [m for m in custom if m["match"] == NEAR]
    if near_core:
        flags.append("Similar core field(s): " + ", ".join(m["path"] for m in near_core[:3]) + ".")
    if near_custom:
        flags.append("Similar custom attribute(s): " + ", ".join(m["label"] for m in near_custom[:3]) + ".")
    if requirement == "already_sourced":
        flags.append(f"HESA {hesa['field']} is already sourced from {hesa['source']} — a custom "
                     "attribute may not be needed.")
    if requirement == "not_found":
        flags.append("No HESA field found for this. Say which return needs it in the reason.")
    if data_type and data_type != suggested_type:
        flags.append(f"Requested type is '{data_type}'; the evidence suggests '{suggested_type}'.")

    if any(m["match"] == EXACT for m in core + custom):
        verdict = "duplicate"
    elif near_core or near_custom or requirement == "already_sourced":
        verdict = "review"
    elif requirement in ("required", "optional"):
        verdict = "supported"
    else:
        verdict = "no_hesa_basis"

    return {
        "verdict": verdict,
        "flags": flags,
        "coreMatches": core[:5],
        "customMatches": custom[:5],
        "hesa": {
            "requirement": requirement,
            "match": hesa,
            "alternatives": hesa_hits[1:4],
            "specification": (f"{hesa['pack']} {hesa['academicYear']} v{hesa['version']}" if hesa else None),
        },
        "suggested": {"dataType": suggested_type, "allowedValues": suggested_values},
        "method": "deterministic",
    }
