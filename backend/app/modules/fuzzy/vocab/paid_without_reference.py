"""Reconciliation drift — paid on our side, no Finance reference to tie back."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="paid_without_reference",
    group="finance",
    description="Payments marked paid without a Finance reference — reconciliation drift.",
    core_tokens=frozenset({"drift", "unreconciled", "reconciliation", "unreferenced",
                            "reference", "unmatched"}),
    adjacent_tokens=frozenset({
        "payment", "payments", "stipend", "finance", "reference", "reconcile",
        "missing", "without", "paid",
    }),
    negative_tokens=frozenset({"held", "overdue"}),
    examples=(
        "unreconciled payments",
        "paid without a finance reference",
        "reconciliation drift",
        "missing finance references",
        "payments without reconciliation",
        "unreferenced stipends",
        "drift on the finance side",
    ),
    optional_slots=frozenset({"window"}),
    tool="funding_cashflow",
    card="finance_lens_drift",
    default_args={"lens": "paidWithoutFinanceReference"},
)
