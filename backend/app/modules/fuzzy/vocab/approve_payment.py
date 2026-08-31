"""Write intent — approve a stipend payment."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="approve_payment",
    group="finance",
    description="Approve a stipend payment (move from scheduled to approved).",
    core_tokens=frozenset({"approve", "approving", "approval"}),
    adjacent_tokens=frozenset({
        "payment", "payments", "stipend", "stipends", "instalment",
    }),
    negative_tokens=frozenset({"reject", "hold", "cancel"}),
    examples=(
        "approve this payment",
        "approve the stipend",
        "approve alice's next instalment",
        "give approval for the payment",
        "approve stipend payment",
    ),
    optional_slots=frozenset({"person"}),
    tool="__write__",
    card="confirm_approve_payment",
    write_action="approve_payment",
    write_permission="funding.change",
)
