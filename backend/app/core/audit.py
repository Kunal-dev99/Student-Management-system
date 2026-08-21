"""Audit trail plumbing (arch §17).

Two ways in:
- `AuditMiddleware` writes one row per successful state-changing request, resolving the actor
  straight from the JWT claims (no DB round-trip, thanks to the embedded-claims access token).
- `record_audit(session, ...)` lets a service add a richer entry (with before/after detail) inside
  its own transaction — the caller commits.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.database import SessionFactory
from app.core.security import decode_token
from app.db.session import get_session
from app.modules.audit.models import AuditLog

logger = logging.getLogger("pgr.audit")

MUTATING = {"POST", "PATCH", "PUT", "DELETE"}
# Paths that mutate but should never be audited (noise / auth internals).
SKIP_PREFIXES = ("/api/v1/auth/login", "/api/v1/auth/refresh")


def _first_uuid(parts: list[str]) -> uuid.UUID | None:
    for p in parts:
        try:
            return uuid.UUID(p)
        except (ValueError, AttributeError):
            continue
    return None


def _singular(word: str) -> str:
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def parse_entity(path: str) -> tuple[str | None, uuid.UUID | None]:
    """Best-effort (entity_type, entity_id) from a REST path like /api/v1/students/{id}/x."""
    segs = [s for s in path.split("/") if s]
    # drop api / v1 prefix
    if segs[:2] == ["api", "v1"]:
        segs = segs[2:]
    if not segs:
        return None, None
    entity_type = _singular(segs[0])
    return entity_type, _first_uuid(segs)


def _actor_from_request(request: Request) -> tuple[uuid.UUID | None, str | None]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None, None
    try:
        claims = decode_token(auth[7:], "access")
    except JWTError:
        return None, None
    uid = claims.get("sub")
    try:
        return (uuid.UUID(uid) if uid else None), claims.get("email")
    except ValueError:
        return None, claims.get("email")


async def record_audit(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_email: str | None = None,
    detail: dict | None = None,
) -> None:
    """Add an audit row to the caller's session (no commit — the caller owns the transaction)."""
    session.add(AuditLog(
        actor_user_id=actor_user_id, actor_email=actor_email, action=action, method=None,
        entity_type=entity_type, entity_id=entity_id, status_code=None,
        request_id=None, detail=detail, created_at=datetime.now(timezone.utc),
    ))


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            if (
                request.method in MUTATING
                and response.status_code < 400
                and not any(request.url.path.startswith(p) for p in SKIP_PREFIXES)
                and request.url.path.startswith("/api/")
            ):
                actor_id, actor_email = _actor_from_request(request)
                entity_type, entity_id = parse_entity(request.url.path)
                row = AuditLog(
                    actor_user_id=actor_id, actor_email=actor_email,
                    action=f"{request.method} {request.url.path}", method=request.method,
                    entity_type=entity_type, entity_id=entity_id,
                    status_code=response.status_code,
                    request_id=getattr(request.state, "request_id", None),
                    detail=None, created_at=datetime.now(timezone.utc),
                )
                # Use the same DB the request used. Under test, get_session is overridden with an
                # in-memory engine; honouring that keeps audit correct and avoids writing to the
                # live DB. In production there is no override, so we use the app SessionFactory.
                override = request.app.dependency_overrides.get(get_session)
                if override is not None:
                    agen = override()
                    session = await agen.__anext__()
                    try:
                        session.add(row)
                        await session.commit()
                    finally:
                        await agen.aclose()
                else:
                    async with SessionFactory() as session:
                        session.add(row)
                        await session.commit()
        except Exception:  # auditing must never break the request
            logger.warning("audit write failed", exc_info=True)
        return response
