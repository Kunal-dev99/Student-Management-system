"""The authenticated principal — who is making the request (arch §12)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class Principal:
    user_id: uuid.UUID
    email: str
    person_id: uuid.UUID | None = None
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    # MT-1 — tenant this principal belongs to. Nullable during Phase 1 skeleton
    # so pre-migration tokens keep working. Once RLS is enabled per-table in Phase 2,
    # a null tenant_id will be refused at the middleware boundary.
    tenant_id: uuid.UUID | None = None

    def has_permission(self, code: str) -> bool:
        return code in self.permissions

    @property
    def is_superuser(self) -> bool:
        # Institution Administrator is seeded with every permission code.
        return "admin.configure" in self.permissions and "person.write" in self.permissions
