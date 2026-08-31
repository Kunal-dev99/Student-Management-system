"""Mandatory-field specifications for statutory returns (F1 — statutory truth).

A **spec** is what the *return* requires. A **profile** is what *we* mapped. F1's sign-off gate
compares one against the other and refuses to sign the profile off until every mandatory field in
the spec has a mapping row in the profile.

The HESA 2026 spec here is a defensible starter, not the full statutory truth — a Registry / HESA
subject-matter reviewer still owns the definitive list for a live year. Fields marked with an
`allowed` list carry the HESA coding frame; those get validated against `allowed_values` on the
mapping too.
"""
from __future__ import annotations

from typing import TypedDict


class MandatoryField(TypedDict, total=False):
    field: str
    description: str
    allowed: list[str]     # HESA coding frame if the field is coded


# ---------------------------------------------------------------------------
# HESA Student return — mandatory subset for 2026/27 (starter set of 24 fields).
# Names follow HESA convention (upper-case). Coding frames are the standard HESA
# codes; the actual return has more fields — those are configurable in the profile.
# ---------------------------------------------------------------------------
HESA_STUDENT_2026: list[MandatoryField] = [
    # Institution / return identity
    {"field": "OWNSTU",   "description": "Institution's own student identifier"},
    {"field": "HUSID",    "description": "HESA unique student identifier"},

    # Person
    {"field": "SURNAME",  "description": "Family name"},
    {"field": "FNAMES",   "description": "Forenames"},
    {"field": "BIRTHDTE", "description": "Date of birth (YYYYMMDD)"},
    {"field": "SEXID",    "description": "Sex identifier",
     "allowed": ["10", "11", "12", "13"]},        # 10=F, 11=M, 12=Other, 13=Not available
    {"field": "NATION",   "description": "Nationality (ISO alpha-2)"},
    {"field": "ETHNIC",   "description": "Ethnicity code",
     "allowed": ["10","15","16","17","18","19","20","21","22","29","31","32","33","34","41","42","43","49","50","98"]},
    {"field": "DISABLE",  "description": "Disability indicator",
     "allowed": ["00","51","53","54","55","56","57","58","96"]},

    # Programme
    {"field": "COURSEID", "description": "Programme identifier"},
    {"field": "COURSETYP","description": "Course type",
     "allowed": ["A","B","C","D","E"]},           # simplified example
    {"field": "STULOAD",  "description": "Student instance load",
     "allowed": ["01","02","31","32","33","34","41","42","43","44"]},
    {"field": "MODE",     "description": "Mode of study",
     "allowed": ["01","02","03","31"]},
    {"field": "STUDYLEVEL","description": "Level of study",
     "allowed": ["D00","M11","H11","I11"]},       # PhD / MPhil / etc.

    # Dates
    {"field": "COMDATE",  "description": "Commencement date (YYYYMMDD)"},
    {"field": "ENDDATE",  "description": "Expected end date (YYYYMMDD)"},

    # Fee / funding
    {"field": "FEESTAT",  "description": "Fee status",
     "allowed": ["1","2","3","4","9"]},
    {"field": "MSTUFEE",  "description": "Major source of tuition fee",
     "allowed": ["01","02","10","20","30","40","50","90","99"]},
    {"field": "FUNDCODE", "description": "Funding council code",
     "allowed": ["1","2","3","4","5","6","7","8","9"]},

    # Location / residence
    {"field": "DOMICILE", "description": "Domicile (ISO alpha-2)"},
    {"field": "TERMTIME", "description": "Term-time accommodation",
     "allowed": ["1","2","3","4","5","6","9"]},

    # Research
    {"field": "THESIS",   "description": "Thesis / topic reference"},
    {"field": "SUPERVISED","description":"Supervised student indicator",
     "allowed": ["Y","N"]},
    {"field": "ENTRYROUTE","description":"How the student entered the programme",
     "allowed": ["OPPORTUNITY","PROPOSAL"]},
]


PROFILE_SPECS: dict[str, list[MandatoryField]] = {
    "HESA_STUDENT": HESA_STUDENT_2026,
}


def spec_for(code: str) -> list[MandatoryField]:
    """Return the mandatory spec for a profile code, or [] if none is registered."""
    return PROFILE_SPECS.get(code, [])
