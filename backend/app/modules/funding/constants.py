"""Funding enumerations (arch §8.2, §8.9)."""
from __future__ import annotations

import enum


class FundingType(str, enum.Enum):
    research_council = "research_council"
    university_scholarship = "university_scholarship"
    external = "external"
    self_funded = "self_funded"


class FundingStatus(str, enum.Enum):
    planned = "planned"
    active = "active"
    changed = "changed"
    ended = "ended"
