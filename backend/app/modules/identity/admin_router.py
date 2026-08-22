"""User & role administration (Phase 8 — the Settings screen's "Users & roles" tab).

Design decisions that matter:
- **No password field anywhere.** Creating a user sends them a password-reset email; an
  administrator never knows, sets, or sees anyone's password.
- **You cannot lock yourself out.** Deactivating your own account or removing your own
  admin permissions is refused — recovering from that requires database access, and the
  person most likely to hit it is the only administrator.
- Roles are assigned from the fixed role list; permissions belong to roles and are read-only
  here (they are code — each permission string is checked by name in routers).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.principal import Principal
from app.db.session import get_read_session, get_session
from app.modules.identity.models import Role, User
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.service import IdentityService

admin_router = APIRouter(prefix="/admin", tags=["settings"])


class UserCreate(BaseModel):
    email: EmailStr
    roleNames: list[str]
    personId: uuid.UUID | None = None


class UserUpdate(BaseModel):
    isActive: bool | None = None
    roleNames: list[str] | None = None
    personId: uuid.UUID | None = None


def _user_out(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "isActive": u.is_active,
        "roles": sorted(r.name for r in u.roles),
        "personId": str(u.person_id) if u.person_id else None,
        "lastLoginAt": u.last_login_at.isoformat() if u.last_login_at else None,
        "lockedUntil": u.locked_until.isoformat() if u.locked_until else None,
        "hasPassword": u.password_hash is not None,
    }


@admin_router.get("/users", summary="All user accounts")
async def list_users(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("admin.configure")),
) -> list[dict]:
    users = (await session.execute(
        select(User).order_by(User.email)
    )).scalars().unique().all()
    return [_user_out(u) for u in users]


@admin_router.get("/roles", summary="Roles and the permissions they carry (permissions read-only)")
async def list_roles(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("admin.configure")),
) -> list[dict]:
    from app.modules.identity.models import user_role

    roles = (await session.execute(select(Role).order_by(Role.name))).scalars().unique().all()
    counts = dict((await session.execute(
        select(user_role.c.role_id, func.count()).group_by(user_role.c.role_id)
    )).all())
    out = []
    for r in roles:
        await session.refresh(r, ["permissions"])
        out.append({
            "id": str(r.id), "name": r.name,
            "permissions": sorted(p.code for p in r.permissions),
            "userCount": int(counts.get(r.id, 0)),
        })
    return out


async def _resolve_roles(session: AsyncSession, names: list[str]) -> list[Role]:
    if not names:
        raise ValidationAppError("A user needs at least one role")
    roles = (await session.execute(select(Role).where(Role.name.in_(names)))).scalars().unique().all()
    missing = set(names) - {r.name for r in roles}
    if missing:
        raise ValidationAppError(f"Unknown role(s): {', '.join(sorted(missing))}")
    return list(roles)


@admin_router.post("/users", status_code=201,
                   summary="Create a user (they set their own password via email)")
async def create_user(
    body: UserCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    email = body.email.strip().lower()
    dup = (await session.execute(
        select(User).where(func.lower(User.email) == email)
    )).scalar_one_or_none()
    if dup is not None:
        raise ConflictError(f"A user with email {email} already exists")

    roles = await _resolve_roles(session, body.roleNames)
    user = User(email=email, password_hash=None, is_active=True, person_id=body.personId)
    session.add(user)
    await session.flush()
    await session.refresh(user, ["roles"])
    user.roles = roles
    await session.commit()

    # The invitation *is* the password-reset flow: no password ever passes through an admin.
    await IdentityService(IdentityRepository(session)).request_password_reset(email)
    return {**_user_out(user), "invited": True}


@admin_router.patch("/users/{user_id}", summary="Activate/deactivate or change roles")
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("admin.configure")),
) -> dict:
    user = (await session.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found")

    acting_on_self = user.id == principal.user_id
    if body.isActive is False and acting_on_self:
        raise ConflictError("You cannot deactivate your own account")

    if body.roleNames is not None:
        roles = await _resolve_roles(session, body.roleNames)
        if acting_on_self:
            still_admin = False
            for r in roles:
                await session.refresh(r, ["permissions"])
                if any(p.code == "admin.configure" for p in r.permissions):
                    still_admin = True
                    break
            if not still_admin:
                raise ConflictError("You cannot remove your own administrator access")
        await session.refresh(user, ["roles"])
        user.roles = roles

    if body.isActive is not None:
        user.is_active = body.isActive
        if body.isActive:
            user.failed_login_count = 0
            user.locked_until = None
    if body.personId is not None:
        user.person_id = body.personId

    await session.commit()
    await session.refresh(user, ["roles"])
    return _user_out(user)


@admin_router.post("/users/{user_id}/send-reset", summary="Send a password-reset email")
async def send_reset(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    user = (await session.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found")
    await IdentityService(IdentityRepository(session)).request_password_reset(user.email)
    return {"sent": True}
