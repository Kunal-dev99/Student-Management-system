"""Admissions enumerations (arch §8.2)."""
from __future__ import annotations

import enum


class OfferStatus(str, enum.Enum):
    draft = "draft"
    issued = "issued"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"
    withdrawn = "withdrawn"
