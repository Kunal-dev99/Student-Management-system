"""Write intent — put a stipend payment on hold."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="hold_payment",
    group="finance",
    description="Put a stipend payment on hold pending review.",
    core_tokens=frozenset({"hold", "halt", "pause", "freeze"}),
    adjacent_tokens=frozenset({
        "payment", "payments", "stipend", "stipends", "instalment",
    }),
    negative_tokens=frozenset({"approve", "release"}),
    examples=(
        "put this payment on hold",
        "hold the stipend",
        "halt alice's payment",
        "pause the next instalment",
        "freeze this payment",
    ),
    optional_slots=frozenset({"person"}),
    tool="__write__",
    card="confirm_hold_payment",
    write_action="hold_payment",
    write_permission="funding.change",
)
