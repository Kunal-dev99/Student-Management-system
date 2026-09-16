"""Deterministic parser for an ingested statutory advisory (ICR G5).

The Registry pastes a published advisory as a set of **directives**, one per line, and this module
turns them into (a) the full field/rule lists that would result, and (b) a diff of ``changes``
against the current pack, using the fixed change vocabulary in ``constants``. It is deliberately
deterministic and side-effect free so the review UI and tests can rely on exactly what it emits.

Directive grammar (keywords are case-insensitive; blank lines and ``#`` comments are ignored)::

    YEAR: 2027/28
    ADD FIELD SEXID2 "Revised sex identifier" coding=[10,11,12,13] source=person.sex keyed_at="Person › sex"
    REMOVE FIELD SEXID
    CODING MODE = [01,02,03,31,99]
    DESC STULOAD "Student instance load (FTE, revised)"
    RULE order COMDATE ENDDATE "ENDDATE must be on or after COMDATE"
    REMOVE RULE order COMDATE ENDDATE

Free-prose advisories that aren't in directive form are handled a layer up (the service can ask the
AI ``read`` shape to extract directives), but the diff itself always runs through this deterministic
core, so acceptance never depends on the model being on.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field

from app.modules.exports.constants import (
    CHANGE_CODING_CHANGED,
    CHANGE_DESCRIPTION_CHANGED,
    CHANGE_FIELD_ADDED,
    CHANGE_FIELD_REMOVED,
    CHANGE_RULE_ADDED,
    CHANGE_RULE_REMOVED,
)


@dataclass
class ParsedAdvisory:
    academic_year: str | None = None
    proposed_fields: list[dict] = dc_field(default_factory=list)
    proposed_rules: list[dict] = dc_field(default_factory=list)
    changes: list[dict] = dc_field(default_factory=list)
    warnings: list[str] = dc_field(default_factory=list)
    directive_count: int = 0


_YEAR = re.compile(r"^YEAR\s*:\s*(\S+)", re.I)
_ADD = re.compile(r'^ADD\s+FIELD\s+(\S+)\s+"([^"]*)"\s*(.*)$', re.I)
_REMOVE_FIELD = re.compile(r"^REMOVE\s+FIELD\s+(\S+)\s*$", re.I)
_CODING = re.compile(r"^CODING\s+(\S+)\s*=\s*\[([^\]]*)\]\s*$", re.I)
_DESC = re.compile(r'^DESC\s+(\S+)\s+"([^"]*)"\s*$', re.I)
_RULE = re.compile(r'^RULE\s+(\S+)\s+(.+?)\s+"([^"]*)"\s*$', re.I)
_REMOVE_RULE = re.compile(r"^REMOVE\s+RULE\s+(\S+)\s+(.+?)\s*$", re.I)

# key=value options on an ADD FIELD line: coding=[...], source=..., transform=..., default=...,
# keyed_at="..." (quoted, may contain spaces).
_KV = re.compile(r'(\w+)\s*=\s*(\[[^\]]*\]|"[^"]*"|\S+)')


def _coding_list(raw: str) -> list[str]:
    return [tok.strip() for tok in raw.split(",") if tok.strip()]


def _find(fields: list[dict], name: str) -> dict | None:
    for f in fields:
        if f.get("field") == name:
            return f
    return None


def _rule_key(rule: dict) -> tuple:
    return (rule.get("kind"), tuple(rule.get("fields", [])))


def parse_advisory(
    text: str, base_fields: list[dict], base_rules: list[dict]
) -> ParsedAdvisory:
    """Apply the advisory's directives to the base pack, returning the result + a diff."""
    # Work on copies so the caller's baseline is never mutated.
    fields = [dict(f) for f in base_fields]
    rules = [dict(r) for r in base_rules]
    out = ParsedAdvisory()

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        if m := _YEAR.match(line):
            out.academic_year = m.group(1)
            continue

        if m := _ADD.match(line):
            name, desc, rest = m.group(1), m.group(2), m.group(3)
            if _find(fields, name):
                out.warnings.append(f"line {lineno}: field {name} already exists — ignored")
                continue
            new: dict = {"field": name, "description": desc, "source": "", "required": True}
            for key, val in _KV.findall(rest):
                key = key.lower()
                if key == "coding":
                    new["allowed"] = _coding_list(val.strip("[]"))
                elif key in ("source", "transform", "default"):
                    new[key] = val.strip('"')
                elif key == "keyed_at":
                    new["keyed_at"] = val.strip('"')
            fields.append(new)
            out.changes.append({
                "type": CHANGE_FIELD_ADDED, "field": name, "before": None,
                "after": {"description": desc, "allowed": new.get("allowed")},
                "note": f"New mandatory field {name}" + (
                    "" if new.get("source") else " — needs a source mapping"),
            })
            out.directive_count += 1
            continue

        if m := _REMOVE_FIELD.match(line):
            name = m.group(1)
            existing = _find(fields, name)
            if not existing:
                out.warnings.append(f"line {lineno}: field {name} not in pack — nothing to remove")
                continue
            fields = [f for f in fields if f.get("field") != name]
            out.changes.append({
                "type": CHANGE_FIELD_REMOVED, "field": name,
                "before": {"description": existing.get("description")}, "after": None,
                "note": f"Field {name} withdrawn from the return",
            })
            out.directive_count += 1
            continue

        if m := _CODING.match(line):
            name, raw_list = m.group(1), m.group(2)
            existing = _find(fields, name)
            if not existing:
                out.warnings.append(f"line {lineno}: CODING for unknown field {name} — ignored")
                continue
            after = _coding_list(raw_list)
            before = existing.get("allowed")
            existing["allowed"] = after
            out.changes.append({
                "type": CHANGE_CODING_CHANGED, "field": name,
                "before": before, "after": after,
                "note": f"Coding frame for {name} updated",
            })
            out.directive_count += 1
            continue

        if m := _DESC.match(line):
            name, desc = m.group(1), m.group(2)
            existing = _find(fields, name)
            if not existing:
                out.warnings.append(f"line {lineno}: DESC for unknown field {name} — ignored")
                continue
            before = existing.get("description")
            existing["description"] = desc
            out.changes.append({
                "type": CHANGE_DESCRIPTION_CHANGED, "field": name,
                "before": before, "after": desc, "note": f"Description for {name} revised",
            })
            out.directive_count += 1
            continue

        if m := _REMOVE_RULE.match(line):
            kind = m.group(1).lower()
            rule_fields = m.group(2).split()
            key = (kind, tuple(rule_fields))
            match = next((r for r in rules if _rule_key(r) == key), None)
            if not match:
                out.warnings.append(f"line {lineno}: rule {kind} {' '.join(rule_fields)} not found")
                continue
            rules = [r for r in rules if _rule_key(r) != key]
            out.changes.append({
                "type": CHANGE_RULE_REMOVED, "field": None,
                "before": {"kind": kind, "fields": rule_fields}, "after": None,
                "note": f"Rule removed: {match.get('message', kind)}",
            })
            out.directive_count += 1
            continue

        if m := _RULE.match(line):
            kind = m.group(1).lower()
            rule_fields = m.group(2).split()
            message = m.group(3)
            new_rule = {"kind": kind, "fields": rule_fields, "message": message}
            if any(_rule_key(r) == _rule_key(new_rule) for r in rules):
                out.warnings.append(f"line {lineno}: rule {kind} {' '.join(rule_fields)} already present")
                continue
            rules.append(new_rule)
            out.changes.append({
                "type": CHANGE_RULE_ADDED, "field": None, "before": None,
                "after": {"kind": kind, "fields": rule_fields, "message": message},
                "note": f"New rule: {message}",
            })
            out.directive_count += 1
            continue

        out.warnings.append(f"line {lineno}: unrecognised directive — {line!r}")

    out.proposed_fields = fields
    out.proposed_rules = rules
    return out
