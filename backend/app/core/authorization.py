"""Row scoping (arch §12.3).

A permission grants a verb; scoping decides which rows. Scoping is derived from the principal
and applied as a query filter in the repository, so it cannot be bypassed by a crafted request.

For students:
- Broad roles (administration, registry, executive, research office, panel) see all students.
- A Supervisor sees only students they currently supervise (active supervisor_relationship).
- Anyone else with student.read but no scope sees none.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from app.core.principal import Principal

# Roles whose holders are not restricted to a subset of students.
UNRESTRICTED_STUDENT_ROLES = {
    "Institution Administrator",
    "PGR Administrator",
    "Registry",
    "Executive",
    "Research Office",
    "Academic or Panel",
    "Admissions or Recruitment",
}


@dataclass
class StudentScope:
    kind: Literal["all", "supervisor", "self", "none"]
    person_id: uuid.UUID | None = None


def student_scope(principal: Principal) -> StudentScope:
    if any(role in UNRESTRICTED_STUDENT_ROLES for role in principal.roles):
        return StudentScope("all")
    if "Supervisor" in principal.roles and principal.person_id is not None:
        return StudentScope("supervisor", principal.person_id)
    if "Student" in principal.roles and principal.person_id is not None:
        return StudentScope("self", principal.person_id)  # sees only their own record
    return StudentScope("none")
