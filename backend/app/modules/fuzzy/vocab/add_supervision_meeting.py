"""Write intent — record a supervision meeting note against a student."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="add_supervision_meeting",
    group="progression",
    description="Log a supervision meeting for the named student (dated today).",
    core_tokens=frozenset({"log", "record", "add", "note"}),
    adjacent_tokens=frozenset({
        "supervision", "meeting", "meetings", "supervisor",
        "note", "minutes",
    }),
    negative_tokens=frozenset({"cancel", "delete", "who", "list"}),
    examples=(
        "log a supervision meeting with Marcus Bell",
        "add a supervision note for Priya Nair: discussed timeline",
        "record meeting with alice",
        "note down today's supervision for Marcus Bell",
    ),
    optional_slots=frozenset({"person"}),
    tool="__write__",
    card="confirm_add_supervision_meeting",
    write_action="add_supervision_meeting",
    write_permission="student.write",
    # Kept at 1.0 — a bare name resolving should not push a write action past
    # student_summary; the write verbs ("log", "note", "record") have to appear.
    entity_weight=1.0,
)
