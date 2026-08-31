"""Integration hub — dead letters and failed messages awaiting replay."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="integration_failures",
    group="admin",
    description="Failed inbound/outbound integration messages — dead-lettered, awaiting replay.",
    core_tokens=frozenset({"dead", "letters", "failures", "failed", "letter"}),
    adjacent_tokens=frozenset({
        "integration", "webhook", "webhooks", "message", "messages", "replay",
        "queue", "hub",
    }),
    negative_tokens=frozenset({"student", "supervisor"}),
    examples=(
        "integration failures",
        "dead letters",
        "failed webhook messages",
        "what needs to be replayed",
        "integration queue",
        "failed integration events",
        "dead letter queue",
    ),
    optional_slots=frozenset(),
    tool="cohort_query",
    card="dead_letter_list",
    default_args={"filter": "integration_failures"},
)
