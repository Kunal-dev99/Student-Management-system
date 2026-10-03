"""Which institution does a request belong to, before anyone has signed in?

On a single shared address (the SaaS deployment) the host doesn't name the institution, and
row-level security is fail-closed, so sign-in can't simply look the user up. These helpers ask
the narrow database functions from migration ``t5_pre_auth_lookups``, which return only
institution ids; the request then runs as that institution like any other. No bypass is used,
so this works under the restricted app login (pgr_app) too.

Each lookup runs in its own short transaction: callers ``rollback()`` afterwards so the next
transaction publishes the institution they set (see ``app.core.database``).

On SQLite (the test suite) there is no RLS and no functions, so the same questions are answered
with plain queries.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select, text, union
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("pgr.pre_auth")


def _pg(session: AsyncSession) -> bool:
    return session.bind is not None and session.bind.dialect.name == "postgresql"


async def _ask(session: AsyncSession, sql: str, params: dict, fallback, many: bool = False):
    """Call a lookup function. If the database predates migration t5 (code deployed before its
    migration ran), fall back to the plain query under the owner's explicit bypass so sign-in
    keeps working, and say so loudly. The restricted app login can't bypass, so for it the
    fallback finds nothing until the migration runs - never more than it should."""
    try:
        if many:
            return [r[0] for r in await session.execute(text(sql), params)]
        return await session.scalar(text(sql), params)
    except ProgrammingError as exc:
        if "does not exist" not in str(exc):
            raise
        await session.rollback()
        logger.warning("pre-sign-in lookup functions missing; run `alembic upgrade head` (t5_pre_auth_lookups)")
        from app.core.tenant_context import system_scope

        async with system_scope():
            if many:
                rows = [r[0] for r in await session.execute(fallback)]
            else:
                rows = await session.scalar(fallback)
        await session.rollback()
        return rows


async def tenant_of_email(session: AsyncSession, email: str | None) -> uuid.UUID | None:
    if not email:
        return None
    from app.modules.identity.models import User

    q = select(User.tenant_id).where(User.email == email.lower())
    if _pg(session):
        return await _ask(session, "SELECT pgr_tenant_of_email(CAST(:e AS text))", {"e": email}, q)
    return await session.scalar(q)


async def tenant_of_user(session: AsyncSession, user_id: uuid.UUID | None) -> uuid.UUID | None:
    if user_id is None:
        return None
    from app.modules.identity.models import User

    q = select(User.tenant_id).where(User.id == user_id)
    if _pg(session):
        return await _ask(session, "SELECT pgr_tenant_of_user(CAST(:u AS uuid))", {"u": user_id}, q)
    return await session.scalar(q)


async def tenant_of_reference(session: AsyncSession, token_hash: str) -> uuid.UUID | None:
    from app.modules.recruitment.f3_models import ReferenceRequest

    q = select(ReferenceRequest.tenant_id).where(ReferenceRequest.token_hash == token_hash)
    if _pg(session):
        return await _ask(session, "SELECT pgr_tenant_of_reference(CAST(:h AS text))", {"h": token_hash}, q)
    return await session.scalar(q)


async def tenants_with_email(session: AsyncSession, email: str) -> list[uuid.UUID]:
    from app.modules.identity.models import User
    from app.modules.person.models import Person

    q = union(select(User.tenant_id).where(User.email == email.lower()),
              select(Person.tenant_id).where(func.lower(Person.email) == email.lower()))
    if _pg(session):
        return await _ask(session, "SELECT pgr_tenants_with_email(CAST(:e AS text))", {"e": email}, q, many=True)
    return [r[0] for r in await session.execute(q)]


async def tenant_of_refresh_token(session: AsyncSession, token: str) -> uuid.UUID | None:
    """The institution of the user a refresh token was issued to (an invalid token gives None,
    and the service then rejects it as usual)."""
    from app.core.security import decode_token

    try:
        sub = decode_token(token, "refresh")["sub"]
        return await tenant_of_user(session, uuid.UUID(sub))
    except Exception:
        return None


async def tenant_of_reset_token(session: AsyncSession, token: str) -> uuid.UUID | None:
    """The institution of the user a password-reset token belongs to. The token table itself
    is global (no tenant column), so the app login can read it directly."""
    from app.core.security import hash_opaque
    from app.modules.identity.models import PasswordResetToken

    user_id = await session.scalar(
        select(PasswordResetToken.user_id).where(PasswordResetToken.token_hash == hash_opaque(token)))
    return await tenant_of_user(session, user_id)
