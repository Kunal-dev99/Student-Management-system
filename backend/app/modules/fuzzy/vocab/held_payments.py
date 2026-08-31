"""Finance-rejected payments — sitting on HOLD, needing triage."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="held_payments",
    group="finance",
    description="Payments Finance refused. Row is HELD, note carries the reason.",
    core_tokens=frozenset({"held", "hold", "rejected", "rejection", "rejections",
                            "blocked", "frozen", "stuck", "refused"}),
    adjacent_tokens=frozenset({
        "payment", "payments", "stipend", "stipends", "finance", "cost", "centre",
        "disbursement", "money",
    }),
    negative_tokens=frozenset({"overdue", "late", "unpaid", "approved"}),
    examples=(
        "held payments",
        "finance rejections",
        "which stipends are on hold",
        "blocked payments this quarter",
        "finance refused to pay",
        "stipends stuck at finance",
        "on hold at finance",
    ),
    optional_slots=frozenset({"person", "window"}),
    tool="funding_cashflow",
    card="finance_lens_held",
    default_args={"lens": "held"},
)
