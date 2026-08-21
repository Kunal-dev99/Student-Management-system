"""Person enumerations (arch §8.2)."""
from __future__ import annotations

import enum


class PersonRelationshipType(str, enum.Enum):
    applicant = "applicant"
    student = "student"
    employee = "employee"
    alumni = "alumni"
    researcher = "researcher"
