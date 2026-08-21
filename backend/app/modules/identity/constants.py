"""Seed roles and permissions for the PGR blueprint (arch §12.2).

A compact starter set — enough to drive row-scoping and nav in Phase 1. Extend per module.
"""
from __future__ import annotations

# Permission = verb on a resource (arch §12.2).
PERMISSIONS: dict[str, str] = {
    "person.read": "Read person records",
    "person.write": "Create and update person records",
    "student.read": "Read student records",
    "student.write": "Create and update student records",
    "recruitment.read": "Read opportunities and applications",
    "recruitment.write": "Manage opportunities and applications",
    "funding.read": "Read funding arrangements",
    "funding.change": "Change funding arrangements",
    "progression.read": "Read progression milestones",
    "progression.decide": "Decide progression outcomes",
    "reporting.read": "Read dashboards and reports",
    "admin.configure": "Configure programmes, workflows, and rules",
    # Phase 4A
    "audit.read": "Read the audit trail",
    "document.read": "Read documents",
    "document.write": "Upload and delete documents",
}

# Role -> permission codes. "*" means all permissions.
ROLES: dict[str, list[str]] = {
    "Institution Administrator": ["*"],
    "PGR Administrator": [
        "person.read", "person.write", "student.read", "student.write",
        "recruitment.read", "recruitment.write", "funding.read",
        "progression.read", "reporting.read",
        "audit.read", "document.read", "document.write",
    ],
    "Supervisor": ["student.read", "progression.read", "progression.decide", "document.read"],
    "Executive": ["reporting.read"],
    # A student can read their own record (row-scoping restricts them to self).
    "Student": ["student.read", "progression.read", "funding.read", "document.read", "document.write"],
}
