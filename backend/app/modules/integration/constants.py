"""Integration enumerations (arch §10)."""
from __future__ import annotations

import enum


class Direction(str, enum.Enum):
    inbound = "inbound"
    outbound = "outbound"


class IntegrationStatus(str, enum.Enum):
    success = "success"
    failed = "failed"
    skipped = "skipped"      # no external route — internal event only
    duplicate = "duplicate"  # inbound message already processed
