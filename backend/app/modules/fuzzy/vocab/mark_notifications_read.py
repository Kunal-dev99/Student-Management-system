"""Write intent — mark every unread notification as read."""
from app.modules.fuzzy.intents import Intent

INTENT = Intent(
    name="mark_notifications_read",
    group="admin",
    description="Mark all your notifications as read.",
    core_tokens=frozenset({"mark", "clear", "read", "dismiss"}),
    adjacent_tokens=frozenset({
        "notifications", "notification", "notifs", "inbox", "alerts", "unread", "all",
    }),
    negative_tokens=frozenset({"delete", "unmark", "unread ones"}),
    examples=(
        "mark all notifications as read",
        "clear my inbox",
        "mark notifications read",
        "dismiss all alerts",
        "clear unread",
    ),
    optional_slots=frozenset(),
    tool="__write__",
    card="confirm_mark_notifications_read",
    write_action="mark_notifications_read",
    write_permission=None,
)
