"""Catalog of dotted paths a statutory mapping may read from.

This is the *authoritative* list of source expressions available on the flat student record that
:func:`app.modules.exports.statutory.StatutoryEngine.build_records` produces. The mapping form
uses it to render a dropdown, so admins never have to guess a path (and never mistype one) —
matching the "deliberately not an expression language" guarantee in `AddFieldDialog`.

Keep this in step with :meth:`StatutoryEngine.build_records` — a change there without a matching
entry here means the mapping UI won't offer that new column even though a user could still type
it in. The tests in ``tests/unit/test_record_schema.py`` pin the two together.
"""
from __future__ import annotations

from dataclasses import dataclass, field

FieldType = str   # "string" | "date" | "number" | "code" | "boolean"


@dataclass(frozen=True)
class RecordField:
    """One dotted source path available to a mapping."""
    path: str            # e.g. "student.startDate"
    label: str           # plain-English label ("Student · start date")
    type: FieldType
    hint: str = ""       # optional one-line explainer, shown as a tooltip in the picker
    nullable: bool = True   # True if the value can legitimately be None (most)


@dataclass(frozen=True)
class RecordGroup:
    """A group of related paths, rendered as a group in the picker (e.g. every `student.*`)."""
    root: str            # "student"
    label: str           # "Student record"
    description: str
    fields: list[RecordField] = field(default_factory=list)


# The catalog mirrors build_records() exactly. If a field's shape changes there, mirror it here.
RECORD_SCHEMA: list[RecordGroup] = [
    RecordGroup(
        root="student",
        label="Student record",
        description="The core student row — reference, status, mode, dates, intensity, generated HUSID.",
        fields=[
            RecordField("student.ref", "Student · reference (student_ref)", "string",
                        hint="The institution's own student identifier — the STUID row.",
                        nullable=False),
            RecordField("student.status", "Student · status", "code",
                        hint="Lifecycle status: active, suspended, withdrawn, completed."),
            RecordField("student.mode", "Student · study mode", "code",
                        hint="full_time / part_time — HESA MODE input."),
            RecordField("student.startDate", "Student · start date", "date"),
            RecordField("student.expectedEndDate", "Student · expected end date", "date"),
            RecordField("student.originalExpectedEndDate",
                        "Student · original expected end date (pre-intensity change)", "date"),
            RecordField("student.entryRoute", "Student · entry route (recruitment)", "code",
                        hint="opportunity | proposal, from the accepted application if any."),
            RecordField("student.intensityPct", "Student · study intensity (FTE %)", "number",
                        hint="Time-weighted current intensity for the academic year — feeds HESA STULOAD.",
                        nullable=False),
            RecordField("student.husid", "Student · HUSID (generated)", "string",
                        hint="13-digit HESA UID computed from the institution code + entry year + sequence + Luhn.",
                        nullable=False),
        ],
    ),
    RecordGroup(
        root="person",
        label="Person",
        description="The person the student record belongs to.",
        fields=[
            RecordField("person.givenName", "Person · given name(s)", "string", nullable=False),
            RecordField("person.familyName", "Person · family name", "string", nullable=False),
            RecordField("person.nationality", "Person · nationality", "code"),
            RecordField("person.email", "Person · email", "string"),
            RecordField("person.dateOfBirth", "Person · date of birth", "date"),
        ],
    ),
    RecordGroup(
        root="programme",
        label="Programme",
        description="The programme the student is enrolled on.",
        fields=[
            RecordField("programme.name", "Programme · name", "string"),
            RecordField("programme.code", "Programme · code", "string"),
        ],
    ),
    RecordGroup(
        root="research",
        label="Research project",
        description="The PGR project attached to a research-programme student (blank for taught).",
        fields=[
            RecordField("research.topic", "Research · project topic", "string"),
            RecordField("research.group", "Research · group", "string"),
        ],
    ),
    RecordGroup(
        root="funding",
        label="Funding arrangement",
        description="The student's active funding arrangement, if any.",
        fields=[
            RecordField("funding.type", "Funding · type", "code",
                        hint="research_council | self | scholarship | etc."),
            RecordField("funding.source", "Funding · source (funder name)", "string"),
            RecordField("funding.amount", "Funding · stipend amount", "number"),
            RecordField("funding.currency", "Funding · currency (GBP…)", "string"),
            RecordField("funding.costCentre", "Funding · cost centre", "string"),
        ],
    ),
    RecordGroup(
        root="award",
        label="Research award",
        description="The award behind the student's research project (if the project has one).",
        fields=[
            RecordField("award.ref", "Award · reference (award_ref)", "string"),
            RecordField("award.title", "Award · title", "string"),
        ],
    ),
]


def as_dict() -> dict:
    """Serialise the catalog for the API. Kept in a helper so the shape is one file to change."""
    return {
        "groups": [
            {
                "root": g.root,
                "label": g.label,
                "description": g.description,
                "fields": [
                    {"path": f.path, "label": f.label, "type": f.type,
                     "hint": f.hint, "nullable": f.nullable}
                    for f in g.fields
                ],
            }
            for g in RECORD_SCHEMA
        ],
        # Flat list of every path for quick membership checks on the client.
        "paths": [f.path for g in RECORD_SCHEMA for f in g.fields],
    }


def known_paths() -> set[str]:
    """Every dotted path the mapping form can offer. Test-facing."""
    return {f.path for g in RECORD_SCHEMA for f in g.fields}
