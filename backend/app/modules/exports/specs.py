"""Mandatory-field specifications for statutory returns (F1 — statutory truth; ICR G5).

A **spec** is what the *return* requires. A **profile** is what *we* mapped. F1's sign-off gate
compares one against the other and refuses to sign the profile off until every mandatory field in
the spec has a mapping row in the profile.

ICR G5 enriches each spec field with a **best-known source expression, transform and coding
frame**, so a new profile can be created *pre-mapped from the spec* (Registry only fills the gaps)
rather than "completely custom". Fields we can't source automatically carry an empty ``source`` and
are created as required-but-unmapped, so the sign-off gate and validation surface them. Specs also
carry **cross-field / format rules** (e.g. ENDDATE ≥ COMDATE) and a **keyed_at** hint saying where
in the student record a value is captured.

Specs are versioned per academic year in ``SPEC_PACKS``; a HESA subject-matter reviewer still owns
the definitive list for a live year, and a new year's pack is added here (or imported) as data —
never scraped.
"""
from __future__ import annotations

from typing import TypedDict


class MandatoryField(TypedDict, total=False):
    field: str
    description: str
    allowed: list[str]      # HESA coding frame if the field is coded
    source: str             # best-known source expression over the flat record ("" = needs mapping)
    transform: str          # default transform to apply
    default: str            # default value when the source is empty
    required: bool          # whether the return requires it (defaults True for a mandatory spec)
    keyed_at: str           # human hint: where this value is captured in the platform


class SpecRule(TypedDict, total=False):
    kind: str               # "order" (fields[0] <= fields[1]) | "format_yyyymmdd"
    fields: list[str]
    message: str


class SpecPack(TypedDict):
    code: str
    name: str
    academic_year: str
    version: int
    fields: list[MandatoryField]
    rules: list[SpecRule]


# ---------------------------------------------------------------------------
# HESA Student return — mandatory subset for 2026/27 (starter set of 24 fields).
# `source` paths resolve against StatutoryEngine.build_records().
# ---------------------------------------------------------------------------
HESA_STUDENT_2026: list[MandatoryField] = [
    # Institution / return identity
    {"field": "OWNSTU",   "description": "Institution's own student identifier",
     "source": "student.ref", "keyed_at": "Student record › reference"},
    {"field": "HUSID",    "description": "HESA unique student identifier",
     "source": "student.husid", "keyed_at": "Generated (institution code + year + sequence + check digit)"},

    # Person
    {"field": "SURNAME",  "description": "Family name",
     "source": "person.familyName", "transform": "upper", "keyed_at": "Person › family name"},
    {"field": "FNAMES",   "description": "Forenames",
     "source": "person.givenName", "keyed_at": "Person › given name"},
    {"field": "BIRTHDTE", "description": "Date of birth (YYYYMMDD)",
     "source": "person.dateOfBirth", "transform": "date_compact", "keyed_at": "Person › date of birth"},
    {"field": "SEXID",    "description": "Sex identifier",
     "allowed": ["10", "11", "12", "13"], "source": "", "keyed_at": "Person › sex (not yet captured)"},
    {"field": "NATION",   "description": "Nationality (ISO alpha-2)",
     "source": "person.nationality", "transform": "upper", "keyed_at": "Person › nationality"},
    {"field": "ETHNIC",   "description": "Ethnicity code",
     "allowed": ["10","15","16","17","18","19","20","21","22","29","31","32","33","34","41","42","43","49","50","98"],
     "source": "", "keyed_at": "Person › ethnicity (not yet captured)"},
    {"field": "DISABLE",  "description": "Disability indicator",
     "allowed": ["00","51","53","54","55","56","57","58","96"],
     "source": "", "keyed_at": "Person › disability (not yet captured)"},

    # Programme
    {"field": "COURSEID", "description": "Programme identifier",
     "source": "programme.code", "keyed_at": "Programme › code"},
    {"field": "COURSETYP","description": "Course type",
     "allowed": ["A","B","C","D","E"], "source": "", "keyed_at": "Programme (not yet captured)"},
    {"field": "STULOAD",  "description": "Student instance load (FTE)",
     "source": "student.intensityPct", "transform": "int", "keyed_at": "Lifecycle › study intensity (ICR G4)"},
    {"field": "MODE",     "description": "Mode of study",
     "allowed": ["01","02","03","31"], "source": "student.mode", "transform": "hesa_mode",
     "keyed_at": "Student record › study mode"},
    {"field": "STUDYLEVEL","description": "Level of study",
     "allowed": ["D00","M11","H11","I11"], "source": "", "keyed_at": "Programme › level (not yet captured)"},

    # Dates
    {"field": "COMDATE",  "description": "Commencement date (YYYYMMDD)",
     "source": "student.startDate", "transform": "date_compact", "keyed_at": "Student record › start date"},
    {"field": "ENDDATE",  "description": "Expected end date (YYYYMMDD)",
     "source": "student.expectedEndDate", "transform": "date_compact", "keyed_at": "Student record › expected end"},

    # Fee / funding
    {"field": "FEESTAT",  "description": "Fee status",
     "allowed": ["1","2","3","4","9"], "source": "", "keyed_at": "Funding (not yet captured)"},
    {"field": "MSTUFEE",  "description": "Major source of tuition fee",
     "allowed": ["01","02","10","20","30","40","50","90","99"], "source": "", "keyed_at": "Funding (not yet captured)"},
    {"field": "FUNDCODE", "description": "Funding council code",
     "allowed": ["1","2","3","4","5","6","7","8","9"], "source": "", "keyed_at": "Funding (not yet captured)"},

    # Location / residence
    {"field": "DOMICILE", "description": "Domicile (ISO alpha-2)",
     "source": "", "keyed_at": "Person › domicile (not yet captured)"},
    {"field": "TERMTIME", "description": "Term-time accommodation",
     "allowed": ["1","2","3","4","5","6","9"], "source": "", "keyed_at": "Not yet captured"},

    # Research
    {"field": "THESIS",   "description": "Thesis / topic reference",
     "source": "research.topic", "keyed_at": "Research project › topic"},
    {"field": "SUPERVISED","description":"Supervised student indicator",
     "allowed": ["Y","N"], "source": "", "default": "Y", "keyed_at": "Supervision (PGR = Y)"},
    {"field": "ENTRYROUTE","description":"How the student entered the programme",
     "allowed": ["OPPORTUNITY","PROPOSAL"], "source": "student.entryRoute", "transform": "hesa_route",
     "keyed_at": "Recruitment › entry route"},
]

HESA_STUDENT_RULES: list[SpecRule] = [
    {"kind": "order", "fields": ["COMDATE", "ENDDATE"],
     "message": "ENDDATE must be on or after COMDATE"},
    {"kind": "format_yyyymmdd", "fields": ["BIRTHDTE", "COMDATE", "ENDDATE"],
     "message": "must be a valid YYYYMMDD date"},
]


SPEC_PACKS: dict[str, SpecPack] = {
    "HESA_STUDENT:2026/27": {
        "code": "HESA_STUDENT", "name": "HESA Student", "academic_year": "2026/27",
        "version": 1, "fields": HESA_STUDENT_2026, "rules": HESA_STUDENT_RULES,
    },
}

# Backward-compatible view: {code: fields} used by the sign-off compile gate.
PROFILE_SPECS: dict[str, list[MandatoryField]] = {
    "HESA_STUDENT": HESA_STUDENT_2026,
}


def spec_for(code: str) -> list[MandatoryField]:
    """The mandatory field list for a profile code (latest pack), or [] if none is registered."""
    return PROFILE_SPECS.get(code, [])


def list_spec_packs() -> list[dict]:
    """Every available spec pack, for the 'new profile from spec' picker."""
    return [
        {"key": key, "code": p["code"], "name": p["name"],
         "academicYear": p["academic_year"], "version": p["version"],
         "fieldCount": len(p["fields"])}
        for key, p in SPEC_PACKS.items()
    ]


def spec_pack(key: str) -> SpecPack | None:
    return SPEC_PACKS.get(key)


def rules_for(code: str) -> list[SpecRule]:
    for p in SPEC_PACKS.values():
        if p["code"] == code:
            return p["rules"]
    return []
