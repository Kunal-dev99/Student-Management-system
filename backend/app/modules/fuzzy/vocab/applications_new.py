"""New applications waiting for triage."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="applications_new",
    group="recruitment",
    description="Applications newly submitted, not yet reviewed.",
    core_tokens=frozenset({"applications", "application", "applicants"}),
    adjacent_tokens=frozenset({
        "new", "fresh", "recent", "incoming", "unread", "untriaged", "submitted",
        "pending", "waiting", "review",
    }),
    negative_tokens=frozenset(),
    examples=(
        "new applications",
        "recent applicants",
        "applications waiting for review",
        "fresh applications",
        "incoming applicants",
        "untriaged applications",
        "who's just applied",
    ),
    optional_slots=frozenset({"window"}),
    tool="cohort_query",
    card="application_queue",
    default_args={"filter": "applications_new"},
)
