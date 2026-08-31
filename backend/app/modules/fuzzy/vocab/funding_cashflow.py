"""Finance-lens cashflow summary — the umbrella "finance status" question."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="funding_cashflow",
    group="finance",
    description="Cashflow snapshot — paid / approved / scheduled / held totals for the window.",
    core_tokens=frozenset({"cashflow", "totals", "spend", "budget", "money", "financial"}),
    adjacent_tokens=frozenset({
        "funding", "finance", "stipend", "stipends", "payment", "payments",
        "quarter", "month", "position", "situation", "summary",
    }),
    negative_tokens=frozenset({"held", "overdue", "rejected"}),
    examples=(
        "finance summary",
        "cashflow this quarter",
        "funding totals",
        "how much have we paid this quarter",
        "budget position",
        "financial summary this month",
        "how is our funding looking",
    ),
    optional_slots=frozenset({"window"}),
    tool="funding_cashflow",
    card="finance_lens_totals",
    default_args={},
)
