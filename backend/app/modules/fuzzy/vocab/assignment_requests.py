"""Supervisor assignment requests awaiting decision."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="assignment_requests",
    group="people",
    description="Supervisor assignment requests awaiting review, approval, or academic review.",
    core_tokens=frozenset({"assignment", "assignments", "request", "requests"}),
    adjacent_tokens=frozenset({
        "supervisor", "supervisors", "supervision", "pending", "awaiting", "approval",
        "review", "queue",
    }),
    negative_tokens=frozenset({"payment", "task"}),
    examples=(
        "pending assignment requests",
        "supervisor assignment queue",
        "requests awaiting approval",
        "supervision requests to review",
        "which assignments are pending",
        "supervisor request queue",
        "assignments awaiting academic review",
    ),
    optional_slots=frozenset(),
    tool="cohort_query",
    card="assignment_request_queue",
    default_args={"filter": "assignment_requests_pending"},
)
