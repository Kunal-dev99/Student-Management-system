"""Import a FULL statutory spec pack from a structured file (ICR G5 follow-up).

Unlike an advisory (which is a *diff* against the current pack), this reads a complete field set
and writes it as a new active :class:`StatutorySpecVersion`. It sidesteps HESA's bot wall entirely:
the Registry downloads HESA's data-model export once, saves it as CSV or JSON, and uploads it here.

Two accepted formats:
  * JSON — ``{"fields": [...], "rules": [...]}`` (full control, incl. cross-field rules), or a bare
    list of field objects.
  * CSV  — one row per field; columns map to the field keys (header names are matched case- and
    space-insensitively). ``allowed`` is a list separated by ``|``, ``;`` or spaces. Rules aren't
    expressed in CSV — use JSON when the return needs them.

The parser is deterministic and permissive about column order/casing, strict about the essentials
(every field needs a code). It never touches the database — materialising the version is the
service's job, after a human has chosen to import.
"""
from __future__ import annotations

import csv
import io
import json
import re

from app.core.errors import ValidationAppError

MAX_FIELDS = 1000

# Accepted field keys (superset of specs.MandatoryField). Anything else in a row is ignored.
_FIELD_KEYS = {
    "field", "description", "allowed", "source", "transform", "default", "required", "keyed_at",
}
# CSV header aliases → canonical key. Matched after lower-casing and stripping non-alphanumerics.
_HEADER_ALIASES = {
    "field": "field", "code": "field", "fieldcode": "field", "targetfield": "field", "name": "field",
    "description": "description", "desc": "description", "label": "description",
    "allowed": "allowed", "allowedvalues": "allowed", "validentries": "allowed",
    "coding": "allowed", "codingframe": "allowed", "codes": "allowed",
    "source": "source", "sourceexpression": "source", "sourcepath": "source",
    "transform": "transform",
    "default": "default", "defaultvalue": "default",
    "required": "required", "mandatory": "required",
    "keyedat": "keyed_at", "keyedon": "keyed_at", "keyedonrecord": "keyed_at", "hint": "keyed_at",
}


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())


def _split_allowed(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    s = str(raw or "").strip()
    if not s:
        return []
    parts = re.split(r"[|;]", s) if re.search(r"[|;]", s) else re.split(r"[,\s]+", s)
    return [p.strip() for p in parts if p.strip()]


def _as_bool(raw, *, default: bool = True) -> bool:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "required", "mandatory"}


def _sanitize_field(row: dict) -> dict | None:
    """One validated MandatoryField dict from a raw row, or None if it has no field code."""
    code = str(row.get("field") or "").strip()
    if not code:
        return None
    out: dict = {"field": code, "required": _as_bool(row.get("required"))}
    if str(row.get("description") or "").strip():
        out["description"] = str(row["description"]).strip()
    allowed = _split_allowed(row.get("allowed"))
    if allowed:
        out["allowed"] = allowed
    for k in ("source", "transform", "default", "keyed_at"):
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
        elif v not in (None, "") and not isinstance(v, str):
            out[k] = str(v)
    return out


def _sanitize_rule(row: dict) -> dict | None:
    kind = str(row.get("kind") or "").strip()
    fields = row.get("fields") or []
    if not kind or not isinstance(fields, list) or not fields:
        return None
    rule: dict = {"kind": kind, "fields": [str(f).strip() for f in fields if str(f).strip()]}
    if str(row.get("message") or "").strip():
        rule["message"] = str(row["message"]).strip()
    sev = str(row.get("severity") or "").strip().lower()
    rule["severity"] = sev if sev in {"error", "warning"} else "error"
    return rule


def _dedupe(fields: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for f in fields:
        if f["field"] in seen:
            continue
        seen.add(f["field"])
        out.append(f)
    return out


def parse_spec_file(
    data: bytes, *, filename: str = "", content_type: str = "",
) -> tuple[list[dict], list[dict]]:
    """(fields, rules) from an uploaded JSON or CSV spec file. Raises ValidationAppError on a file
    that yields no usable fields."""
    if not data:
        raise ValidationAppError("The file is empty.")
    name = (filename or "").lower()
    ct = (content_type or "").lower()
    text = data.decode("utf-8-sig", errors="replace")

    is_json = "json" in ct or name.endswith(".json") or text.lstrip()[:1] in "[{"
    if is_json:
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValidationAppError(f"Could not parse JSON: {exc}") from exc
        raw_fields = doc.get("fields") if isinstance(doc, dict) else doc
        raw_rules = doc.get("rules") if isinstance(doc, dict) else []
        if not isinstance(raw_fields, list):
            raise ValidationAppError("JSON must have a 'fields' list (or be a list of fields).")
        fields = [g for g in (_sanitize_field(r) for r in raw_fields if isinstance(r, dict)) if g]
        rules = [g for g in (_sanitize_rule(r) for r in (raw_rules or []) if isinstance(r, dict)) if g]
    else:
        reader = csv.reader(io.StringIO(text))
        rows = [r for r in reader if any((c or "").strip() for c in r)]
        if not rows:
            raise ValidationAppError("The CSV has no rows.")
        header = [_norm_header(h) for h in rows[0]]
        # Map each column to a canonical field key (unknown columns become None and are skipped).
        cols = [_HEADER_ALIASES.get(h) for h in header]
        if "field" not in cols:
            raise ValidationAppError(
                "The CSV needs a 'field' (or 'code') column naming each statutory field."
            )
        fields = []
        for raw in rows[1:]:
            row = {cols[i]: raw[i] for i in range(min(len(cols), len(raw))) if cols[i]}
            g = _sanitize_field(row)
            if g:
                fields.append(g)
        rules = []

    fields = _dedupe(fields)
    if not fields:
        raise ValidationAppError("No fields with a code were found in the file.")
    if len(fields) > MAX_FIELDS:
        raise ValidationAppError(f"Too many fields ({len(fields)}); the limit is {MAX_FIELDS}.")
    return fields, rules
