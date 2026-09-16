"""Export enumerations (arch §13.4)."""
from __future__ import annotations

import enum


class ExportStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    complete = "complete"
    failed = "failed"


# Supported export kinds.
EXPORT_KINDS = {"students_statutory", "pgr_enterprise_360"}


# --- ICR G5 — statutory advisory ingestion ---------------------------------

class AdvisoryStatus(str, enum.Enum):
    """Lifecycle of an ingested advisory: parsed, then a Registry owner accepts or rejects it."""
    ingested = "ingested"
    accepted = "accepted"
    rejected = "rejected"


class SpecVersionStatus(str, enum.Enum):
    """A DB-backed spec-pack version is the live one (active) or has been superseded by a later accept."""
    active = "active"
    superseded = "superseded"


# The kinds of change an advisory can propose against the current pack. Deterministic;
# the differ emits exactly these so the review UI and tests can rely on the vocabulary.
CHANGE_FIELD_ADDED = "field_added"
CHANGE_FIELD_REMOVED = "field_removed"
CHANGE_CODING_CHANGED = "coding_changed"
CHANGE_DESCRIPTION_CHANGED = "description_changed"
CHANGE_RULE_ADDED = "rule_added"
CHANGE_RULE_REMOVED = "rule_removed"
