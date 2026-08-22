"""Research context enumerations (Phase 6.1 — CIO vision GAP-01)."""
from __future__ import annotations

import enum


class AwardStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    closed = "closed"


class DemandStatus(str, enum.Enum):
    """The life of a stated need for a researcher, before any student exists."""
    identified = "identified"    # someone has said "we will need a researcher"
    approved = "approved"        # the institution has agreed to resource it
    positioned = "positioned"    # one or more PGR positions have been advertised
    filled = "filled"            # the requested places are taken
    withdrawn = "withdrawn"


DEMAND_TRANSITIONS: dict[DemandStatus, set[DemandStatus]] = {
    DemandStatus.identified: {DemandStatus.approved, DemandStatus.withdrawn},
    DemandStatus.approved: {DemandStatus.positioned, DemandStatus.withdrawn},
    DemandStatus.positioned: {DemandStatus.filled, DemandStatus.withdrawn},
    DemandStatus.filled: set(),
    DemandStatus.withdrawn: set(),
}

# An award record whose `source_system` is set is mastered elsewhere (the Research system).
# The PGR platform holds a *reference*, never the authority — it is not grants management.
EXTERNALLY_MASTERED_MESSAGE = (
    "This award is maintained in the {system} system and cannot be edited here. "
    "Update it there; the change arrives via the integration hub."
)
