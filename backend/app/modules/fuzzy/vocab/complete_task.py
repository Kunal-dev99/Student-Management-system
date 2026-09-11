"""Write intent — complete the caller's next open task."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="complete_task",
    group="admin",
    description="Mark your next open task as done.",
    core_tokens=frozenset({"complete", "completed", "finish", "finished", "done"}),
    adjacent_tokens=frozenset({"task", "tasks", "todo", "to-do", "next", "my"}),
    negative_tokens=frozenset({"cancel", "delete", "who", "which", "list"}),
    examples=(
        "complete my next task",
        "mark my task done",
        "finish my next todo",
        "close the next task",
        "task done",
    ),
    optional_slots=frozenset(),
    tool="__write__",
    card="confirm_complete_task",
    write_action="complete_task",
    write_permission=None,          # anyone can act on their own inbox
)
