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
