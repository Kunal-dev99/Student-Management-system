"""Request-verb vocabulary — verbs that signal "user wants me to do X".

Presence is a weak signal (many intents have no verb), so the classifier does not
require one. But when present, the verb helps the router pick a query intent over
a navigation intent.
"""
from __future__ import annotations

REQUEST_VERBS = frozenset({
    "show", "list", "get", "find", "pull", "display", "give", "tell",
    "fetch", "load", "search", "lookup", "grab",
    "what", "who", "which", "how", "when", "where",   # interrogative starters
    "count", "how many", "how much",
    "open", "go", "goto", "navigate", "jump", "take", "bring", "send",
    "summarise", "summarize", "summary",
})

# Verbs that specifically request action rather than a read. Written intents (CB-B)
# will use this to gate confirm-before-write.
WRITE_VERBS = frozenset({
    "approve", "reject", "decline", "hold", "release", "mark", "set",
    "assign", "add", "remove", "create", "delete", "cancel", "submit",
    "confirm", "sign", "signoff",
})


def is_request_verb(token: str) -> bool:
    return token in REQUEST_VERBS


def is_write_verb(token: str) -> bool:
    return token in WRITE_VERBS
