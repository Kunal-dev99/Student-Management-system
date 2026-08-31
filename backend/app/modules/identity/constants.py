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
    # F1 — statutory sign-off. Distinct from admin.configure: signing off attests that a
    # regulatory return is complete, and belongs to Registry / HESA owners, not any admin.
    "reports.signoff": "Sign off (or unsign) a statutory report profile",
    # F2 — GDPR person operations (merge, subject-access export, erasure). Sensitive enough
    # to sit outside admin.configure and person.write.
    "person.gdpr": "Merge duplicate persons; export or erase a person under GDPR",
    "admin.configure": "Configure programmes, workflows, and rules",
    # Phase 4A
    "audit.read": "Read the audit trail",
    "document.read": "Read documents",
    "document.write": "Upload and delete documents",
    # Phase 5 — assistant (admin pilot only)
    "assistant.use": "Use the Ask PGR assistant",
    # Phase 6.5 — approving a suspension/extension is what actually moves a student's dates,
    # so it is a separate permission from ordinary student.write.
    "student.lifecycle.approve": "Approve suspensions, extensions and mode changes",
    # Pattern Lab (PL-1) — discovery is powerful enough to deserve its own verbs; training
    # and approval permissions arrive with PL-3/PL-4.
    "ml.read": "View Pattern Lab targets, datasets, findings and predictions",
    "ml.analyse": "Build Pattern Lab datasets and run pattern discovery",
    # PL-3 — training creates versioned artifacts, a heavier act than discovery.
    "ml.train": "Train Pattern Lab model candidates",
    # PL-4 — deciding on a model (approve/decline/promote/retire) is deliberately NOT part
    # of the PGR Administrator bundle: only roles granted "*" (Institution Administrator)
    # hold it by default, and approver separation still applies on top.
    "ml.approve": "Approve, decline, promote or retire Pattern Lab model versions",
}

# Role -> permission codes. "*" means all permissions.
ROLES: dict[str, list[str]] = {
    "Institution Administrator": ["*"],
    "PGR Administrator": [
        "person.read", "person.write", "student.read", "student.write",
        "recruitment.read", "recruitment.write", "funding.read",
        "progression.read", "reporting.read", "reports.signoff",
        "audit.read", "document.read", "document.write",
        "assistant.use", "student.lifecycle.approve",
        "ml.read", "ml.analyse", "ml.train",
    ],
    "Supervisor": ["student.read", "progression.read", "progression.decide", "document.read"],
    "Executive": ["reporting.read"],
    # A student can read their own record (row-scoping restricts them to self).
    "Student": ["student.read", "progression.read", "funding.read", "document.read", "document.write"],
}
