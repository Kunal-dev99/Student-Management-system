"""Write intent — assign the caller as supervisor to the resolved student."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="assign_supervisor",
    group="people",
    description="Assign yourself as supervisor to the named student (primary by default; add 'co' for co-supervisor).",
    core_tokens=frozenset({"assign", "become", "add"}),
    adjacent_tokens=frozenset({
        "supervisor", "supervise", "supervising", "primary", "co", "co-supervisor",
    }),
    negative_tokens=frozenset({"remove", "end", "unassign", "delete"}),
    examples=(
        "assign me as supervisor of Marcus Bell",
        "become primary supervisor for Priya Nair",
        "add me as co-supervisor for Marcus Bell",
        "assign myself to supervise alice",
    ),
    optional_slots=frozenset({"person"}),
    tool="__write__",
    card="confirm_assign_supervisor",
    write_action="assign_supervisor",
    write_permission="student.write",
    entity_weight=1.0,
)
