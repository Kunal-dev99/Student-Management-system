"""ICR module constants — the Institute of Cancer Research PGR model.

Additive: this module reads the existing student/progression/funding tables and
adds ICR-specific views over them. Nothing here changes core behaviour.
"""
from __future__ import annotations

# Programme codes seeded by scripts/seed_icr.py.
PATHWAYS: dict[str, dict] = {
    "ICR-PHD": {
        "label": "Non-Clinical PhD",
        "detail": "Science graduates — 4-year full-time laboratory or computational project.",
        "durationMonths": 48,
        "clinical": False,
    },
    "ICR-MDRES": {
        "label": "Clinical MD(Res)",
        "detail": "Practising clinicians — condensed 2-3 year model merged with Specialist "
                  "Registrar training.",
        "durationMonths": 36,
        "clinical": True,
    },
}

# The upgrade checkpoint that gates MPhil -> PhD. Matched on the milestone
# definition name seeded for the non-clinical pathway.
TRANSFER_VIVA_NAME = "Transfer Viva — MPhil to PhD Upgrade"

# The 30-month data barrier, the second hard filter in the ICR model.
DATA_BARRIER_NAME = "30-Month Data Barrier Review"

# Registration status implied by the transfer viva outcome.
PROVISIONAL_MPHIL = "Provisional MPhil"
UPGRADED_PHD = "PhD (upgraded)"

ICR_FUNDERS = [
    "Cancer Research UK (CRUK)",
    "Medical Research Council (MRC)",
    "Breast Cancer Now",
    "ICR Corporate Partnership Pool",
]
