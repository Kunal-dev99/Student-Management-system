"""Recent audit-log entries."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="audit_recent",
    group="admin",
    description="Recent audit-log entries — who did what, in the window.",
    core_tokens=frozenset({"audit", "log", "logs", "activity", "trail"}),
    adjacent_tokens=frozenset({
        "recent", "latest", "last", "history", "who", "did",
    }),
    negative_tokens=frozenset(),
    examples=(
        "recent audit log",
        "latest activity",
        "audit trail",
        "who did what recently",
        "recent history",
        "audit events",
        "activity log this week",
    ),
    optional_slots=frozenset({"window"}),
    tool="cohort_query",
    card="audit_log",
    default_args={"filter": "audit_recent"},
)
