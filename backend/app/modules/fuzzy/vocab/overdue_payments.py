"""Overdue stipend payments — approved by us, past due, unpaid by Finance."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="overdue_payments",
    group="finance",
    description="Stipend payments approved on our side, past due, not yet paid by Finance.",
    core_tokens=frozenset({"overdue", "late", "unpaid", "outstanding", "chase"}),
    adjacent_tokens=frozenset({
        "payment", "payments", "stipend", "stipends", "instalment", "instalments",
        "disbursement", "transfer", "money", "cashflow", "behind",
        "pay", "paying", "paid",
    }),
    negative_tokens=frozenset({"held", "rejected", "cancelled"}),
    examples=(
        "who's late paying",
        "overdue stipends this quarter",
        "unpaid payments for alice",
        "chase up outstanding transfers",
        "which payments are behind",
        "late stipends",
        "outstanding payments",
    ),
    optional_slots=frozenset({"person", "window"}),
    tool="funding_cashflow",
    card="finance_lens_overdue",
    default_args={"lens": "overdueApproved"},
)
