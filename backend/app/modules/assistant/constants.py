"""Assistant policy (Phase 5, see docs/PGR_ASSISTANT_DESIGN.md).

The three-tier action policy is declared here even though Phase 5.1 ships read-only, so the
boundary is explicit in code from day one and 5.2 has nothing to invent.
"""
from __future__ import annotations

import enum


class Tier(str, enum.Enum):
    read = "read"          # executes immediately
    confirm = "confirm"    # 5.2: propose -> human confirms -> execute
    blocked = "blocked"    # never executed by the assistant; deep-link to the form instead


# Actions the assistant must NEVER perform, by user decision (2026-08-22). For these it returns a
# deep link to the relevant form so the human decides with the full context in front of them.
BLOCKED_ACTIONS: dict[str, str] = {
    # Formal academic decisions
    "decide_milestone": "A progression decision must be made on the review form, where the panel, conditions and outcome letter are visible.",
    "record_examination_outcome": "An examination outcome must be recorded on the thesis form.",
    "graduate_student": "Graduation is final and closes funding; it must be confirmed on the completion form.",
    "approve_corrections": "Signing off thesis corrections must be done on the thesis form.",
    # Money
    "mark_payment_paid": "Recording a stipend payment is a financial record; it must be entered on the funding form.",
    "approve_payment": "Approving a stipend instalment must be done on the funding form.",
    "approve_fee_waiver": "Approving a fee waiver must be done on the funding form.",
    # Appeals (the action most worth attacking via injected text in a grounds field)
    "decide_appeal": "Deciding a student appeal must be done on the progression form.",
    # Destructive
    "delete_document": "Deleting a document must be done on the record itself.",
}

# Permission gating the assistant. Seeded to Institution Administrator + PGR Administrator only
# (pilot decision: admins first).
ASSISTANT_PERMISSION = "assistant.use"

# Max rows any single tool may return to the model — keeps context bounded and cost predictable.
MAX_TOOL_ROWS = 50
