"""Post-viva corrections open — thesis corrections not yet submitted or approved."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="corrections_open",
    group="progression",
    description="Post-viva thesis corrections still open — not submitted or awaiting approval.",
    core_tokens=frozenset({"corrections", "correction"}),
    adjacent_tokens=frozenset({
        "open", "outstanding", "pending", "thesis", "post", "viva",
        "unsubmitted", "unapproved",
    }),
    negative_tokens=frozenset({"complete", "done", "closed"}),
    examples=(
        "corrections open",
        "outstanding thesis corrections",
        "post viva corrections pending",
        "who owes corrections",
        "unsubmitted corrections",
        "which students still have corrections open",
        "thesis corrections not yet approved",
    ),
    optional_slots=frozenset(),
    tool="cohort_query",
    card="corrections_queue",
    default_args={"filter": "corrections_open"},
)
