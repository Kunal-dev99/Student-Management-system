"""Funding enumerations (arch §8.2, §8.9)."""
from __future__ import annotations

import enum


class FundingType(str, enum.Enum):
    research_council = "research_council"
    university_scholarship = "university_scholarship"
    external = "external"
    self_funded = "self_funded"
    # W1.4 — three additional canonical funding shapes from the CIO plan matrix.
    # scholarship = charity / trust / external scholarship (distinct from a university one).
    # employer    = employer-sponsored (part-time PhDs on their firm's day).
    # mixed       = umbrella when a student holds multiple concurrent arrangements deliberately
    #               (this is a metadata hint on ONE row; the funding-lineage view still walks the
    #               actual concurrent arrangements to compute totals).
    scholarship = "scholarship"
    employer = "employer"
    mixed = "mixed"


class FundingStatus(str, enum.Enum):
    planned = "planned"
    active = "active"
    changed = "changed"
    ended = "ended"


class PaymentFrequency(str, enum.Enum):
    monthly = "monthly"
    quarterly = "quarterly"
    termly = "termly"
    annual = "annual"
    one_off = "one_off"


class PaymentStatus(str, enum.Enum):
    scheduled = "scheduled"
    approved = "approved"
    paid = "paid"
    held = "held"
    cancelled = "cancelled"


class WaiverKind(str, enum.Enum):
    full_fee = "full_fee"
    partial_fee = "partial_fee"
    bench_fee = "bench_fee"


# Instalments generated per year for each frequency (used to build a payment schedule).
INSTALMENTS_PER_YEAR = {
    PaymentFrequency.monthly: 12,
    PaymentFrequency.quarterly: 4,
    PaymentFrequency.termly: 3,
    PaymentFrequency.annual: 1,
    PaymentFrequency.one_off: 1,
}

# Payments in these states are considered committed spend against a funding arrangement.
COMMITTED_PAYMENT_STATES = {PaymentStatus.scheduled, PaymentStatus.approved, PaymentStatus.paid}


# A funding gap shorter than this is administrative noise (a weekend between
# arrangements), not a problem. Default for the "funding.min_gap_days" setting.
MIN_GAP_DAYS = 7
