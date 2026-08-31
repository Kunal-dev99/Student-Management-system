"""Person enumerations (arch §8.2)."""
from __future__ import annotations

import enum


class PersonRelationshipType(str, enum.Enum):
    applicant = "applicant"
    student = "student"
    employee = "employee"
    alumni = "alumni"
    researcher = "researcher"
    # ICR gap 2 — the ICR MD(Res) student is also a Specialist Registrar on rotation. The two
    # identities run concurrently; the person model already supports that.
    clinical_trainee = "clinical_trainee"


class PersonContactChannel(str, enum.Enum):
    """F2 — channels a person can be contacted on other than the primary email."""
    email = "email"
    phone = "phone"
    mobile = "mobile"
    address = "address"
    emergency = "emergency"
