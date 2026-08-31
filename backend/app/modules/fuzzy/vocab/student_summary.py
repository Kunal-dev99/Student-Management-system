"""Summary of a single student — needs a person slot."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="student_summary",
    group="people",
    description="Overview of one student: programme, status, supervisors, milestones, funding.",
    core_tokens=frozenset({"summary", "overview", "state", "status", "profile", "record", "details"}),
    adjacent_tokens=frozenset({
        "student", "person", "candidate",
    }),
    negative_tokens=frozenset(),
    examples=(
        "state of alice khan",
        "overview of tom fisher",
        "summary for stu-123",
        "alice profile",
        "how is alice doing",
        "show me alice",
        "tell me about alice khan",
    ),
    optional_slots=frozenset({"person"}),
    tool="get_student_overview",
    card="student_summary",
    default_args={},
    # A resolved student IS the primary signal for this intent — outweighs weak keywords.
    entity_weight=1.5,
)
