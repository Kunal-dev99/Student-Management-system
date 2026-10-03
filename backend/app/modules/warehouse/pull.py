"""Data warehouse export — the pull API for external systems (a warehouse loader, a BI tool).

Consumers sign in with OAuth 2.0 client credentials (RFC 6749 section 4.4):

    POST /api/v1/warehouse/oauth/token
         grant_type=client_credentials&client_id=...&client_secret=...   (or HTTP Basic)
      -> {"access_token": "...", "token_type": "Bearer", "expires_in": 900}

then read with ``Authorization: Bearer <token>``:

    GET /api/v1/warehouse/data/objects                       the catalogue they may read
    GET /api/v1/warehouse/data/objects/{name}?changedSince=  rows, paged by an opaque cursor
    GET /api/v1/warehouse/data/objects/{name}/deleted?changedSince=  ids deleted since then

A consumer belongs to one institution and reads only its data (the token names the institution,
row-level security enforces it). Tokens are type "warehouse": they don't work on the rest of the
API, and user tokens don't work here. Revoking a consumer stops its current tokens at once.

Paging: the first page fixes the window end (``windowTo``); the cursor carries it, so a consumer
paging through a large object sees one consistent window. When ``nextCursor`` is null the window
is done: keep ``windowTo`` and pass it as ``changedSince`` next time (rows near the boundary may
repeat; upsert on ``id``).
"""
from __future__ import annotations

import base64
import binascii
import hmac
import json
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.errors import AuthError, NotFoundError, PermissionError, ValidationAppError
from app.core.security import _create_token, decode_token, hash_opaque
from app.db.session import get_session
from app.modules.warehouse import catalogue, extract, files
from app.modules.warehouse.models import WarehouseConsumer

TOKEN_TTL_SECONDS = 900
MAX_LIMIT = 5000

consumers_router = APIRouter(prefix="/warehouse/consumers", tags=["warehouse"])
token_router = APIRouter(prefix="/warehouse/oauth", tags=["warehouse"])
data_router = APIRouter(prefix="/warehouse/data", tags=["warehouse"])


# ------------------------------------------------------------------ administration (institution)

class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ConsumerIn(_Camel):
    name: str = Field(min_length=1, max_length=120)
    objects: list[str] | None = None
    personal_data: bool = False


def _consumer(c: WarehouseConsumer) -> dict:
    return {"id": str(c.id), "name": c.name, "clientId": c.client_id, "objects": c.objects,
            "personalData": c.personal_data, "active": c.active,
            "lastUsedAt": c.last_used_at.isoformat() if c.last_used_at else None}


def _new_secret() -> str:
    return secrets.token_urlsafe(32)


def _check_objects(names: list[str] | None) -> None:
    if names is not None:
        if not names:
            raise ValidationAppError("Choose at least one object, or leave objects empty for all")
        try:
            catalogue.objects(names)
        except ValueError as exc:
            raise ValidationAppError(str(exc)) from exc


async def _get(session: AsyncSession, consumer_id: uuid.UUID) -> WarehouseConsumer:
    c = await session.get(WarehouseConsumer, consumer_id)
    if c is None:
        raise NotFoundError("Consumer not found")
    return c


@consumers_router.get("", summary="This institution's API consumers")
async def list_consumers(session: AsyncSession = Depends(get_session),
                         _=Depends(require_permission("admin.configure"))) -> list[dict]:
    rows = (await session.execute(select(WarehouseConsumer).order_by(WarehouseConsumer.name))).scalars()
    return [_consumer(c) for c in rows]


@consumers_router.post("", status_code=201, summary="Create a consumer (the secret is shown once)")
async def create_consumer(body: ConsumerIn, session: AsyncSession = Depends(get_session),
                          principal=Depends(require_permission("admin.configure"))) -> dict:
    _check_objects(body.objects)
    secret = _new_secret()
    c = WarehouseConsumer(name=body.name.strip(), client_id=f"pgrw_{secrets.token_hex(12)}",
                          secret_hash=hash_opaque(secret), objects=body.objects,
                          personal_data=body.personal_data, created_by_user_id=principal.user_id)
    session.add(c)
    await session.commit()
    return {**_consumer(c), "clientSecret": secret}


@consumers_router.post("/{consumer_id}/rotate", summary="Issue a new secret (the old one stops working)")
async def rotate_consumer(consumer_id: uuid.UUID, session: AsyncSession = Depends(get_session),
                          _=Depends(require_permission("admin.configure"))) -> dict:
    c = await _get(session, consumer_id)
    secret = _new_secret()
    c.secret_hash = hash_opaque(secret)
    await session.commit()
    return {**_consumer(c), "clientSecret": secret}


@consumers_router.post("/{consumer_id}/revoke", summary="Revoke a consumer (its tokens stop at once)")
async def revoke_consumer(consumer_id: uuid.UUID, session: AsyncSession = Depends(get_session),
                          _=Depends(require_permission("admin.configure"))) -> dict:
    c = await _get(session, consumer_id)
    c.active = False
    await session.commit()
    return _consumer(c)


@consumers_router.delete("/{consumer_id}", status_code=204, summary="Delete a consumer")
async def delete_consumer(consumer_id: uuid.UUID, session: AsyncSession = Depends(get_session),
                          _=Depends(require_permission("admin.configure"))) -> Response:
    await session.delete(await _get(session, consumer_id))
    await session.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ token (client credentials)

def _oauth_error(code: str, description: str, status: int = 400) -> Response:
    # RFC 6749 section 5.2 error shape, which OAuth client libraries expect.
    return Response(json.dumps({"error": code, "error_description": description}), status_code=status,
                    media_type="application/json", headers={"Cache-Control": "no-store"})


@token_router.post("/token", summary="OAuth 2.0 client-credentials grant for warehouse consumers")
async def token(request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    from app.core import pre_auth
    from app.core.tenant_context import set_current_tenant

    form = await request.form()
    grant = form.get("grant_type")
    client_id, client_secret = form.get("client_id"), form.get("client_secret")
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        try:
            client_id, _, client_secret = base64.b64decode(auth[6:]).decode().partition(":")
        except (binascii.Error, UnicodeDecodeError):
            return _oauth_error("invalid_client", "Malformed Basic credentials", 401)
    if grant != "client_credentials":
        return _oauth_error("unsupported_grant_type", "Only client_credentials is supported")
    if not client_id or not client_secret:
        return _oauth_error("invalid_client", "client_id and client_secret are required", 401)

    # No institution is known yet: a narrow lookup (ids only, no bypass) finds the client's.
    tid = await pre_auth.tenant_of_warehouse_client(session, str(client_id))
    await session.rollback()
    consumer = None
    if tid is not None:
        set_current_tenant(tid)
        consumer = (await session.execute(select(WarehouseConsumer).where(
            WarehouseConsumer.client_id == str(client_id)))).scalar_one_or_none()
    if (consumer is None or not consumer.active
            or not hmac.compare_digest(consumer.secret_hash, hash_opaque(str(client_secret)))):
        return _oauth_error("invalid_client", "Unknown client or wrong secret", 401)

    consumer.last_used_at = datetime.now(timezone.utc)
    await session.commit()
    access = _create_token(str(consumer.id), "warehouse", TOKEN_TTL_SECONDS, {"tenantId": str(consumer.tenant_id)})
    return Response(json.dumps({"access_token": access, "token_type": "Bearer", "expires_in": TOKEN_TTL_SECONDS}),
                    media_type="application/json", headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ data (consumers)

async def current_consumer(request: Request, session: AsyncSession = Depends(get_session)) -> WarehouseConsumer:
    from app.core.tenant_context import set_current_tenant

    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise AuthError("A warehouse access token is required")
    try:
        claims = decode_token(auth[7:].strip(), "warehouse")
        tid, cid = uuid.UUID(claims["tenantId"]), uuid.UUID(claims["sub"])
    except Exception as exc:
        raise AuthError("Invalid or expired token") from exc
    set_current_tenant(tid)
    consumer = await session.get(WarehouseConsumer, cid)
    if consumer is None or not consumer.active:
        raise AuthError("This consumer has been revoked")
    return consumer


def _allowed(consumer: WarehouseConsumer, name: str):
    try:
        obj = catalogue.objects([name])[0]
    except ValueError as exc:
        raise NotFoundError(f"No object named {name!r}") from exc
    if consumer.objects is not None and name not in consumer.objects:
        raise PermissionError(f"This consumer may not read {name!r}")
    return obj


def _json_value(v, type_: str):
    v = files._plain(v, type_)
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if type_ == "decimal" and v is not None:
        return str(v)          # exact, as text
    return v


def _encode_cursor(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")


def _decode_cursor(c: str) -> dict:
    try:
        return json.loads(base64.urlsafe_b64decode(c + "=" * (-len(c) % 4)))
    except Exception as exc:
        raise ValidationAppError("Invalid cursor") from exc


def _parse_time(value: str | None, name: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationAppError(f"{name} must be an ISO-8601 timestamp") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@data_router.get("/objects", summary="The objects this consumer may read, with their columns")
async def consumer_catalogue(consumer: WarehouseConsumer = Depends(current_consumer)) -> list[dict]:
    return [catalogue.describe(o, consumer.personal_data) for o in catalogue.objects(consumer.objects)]


@data_router.get("/objects/{name}", summary="Rows of one object, optionally only those changed since a time")
async def object_rows(name: str, changedSince: str | None = Query(None), cursor: str | None = Query(None),
                      limit: int = Query(1000, ge=1, le=MAX_LIMIT), format: str = Query("json"),
                      consumer: WarehouseConsumer = Depends(current_consumer),
                      session: AsyncSession = Depends(get_session)):
    obj = _allowed(consumer, name)
    if format not in ("json", "csv"):
        raise ValidationAppError("format is json or csv")
    if cursor:
        cur = _decode_cursor(cursor)
        if cur.get("o") != name:
            raise ValidationAppError("This cursor belongs to another object")
        since, until = _parse_time(cur.get("s"), "cursor"), _parse_time(cur["u"], "cursor")
        after = (_parse_time(cur["c"], "cursor"), uuid.UUID(cur["i"]))
    else:
        since, until, after = _parse_time(changedSince, "changedSince"), await extract.database_now(session), None

    cols = catalogue.columns(obj, consumer.personal_data)
    page = []
    async for batch in extract.rows(session, consumer.tenant_id, obj, personal=consumer.personal_data,
                                    since=since, until=until, page=limit, after=after):
        page = batch
        break
    next_cursor = None
    if len(page) == limit:
        last = page[-1]
        changed = last[catalogue.CHANGE_FIELD]
        changed = changed if changed.tzinfo else changed.replace(tzinfo=timezone.utc)
        next_cursor = _encode_cursor({"o": name, "s": since.isoformat() if since else None,
                                      "u": until.isoformat(), "c": changed.isoformat(), "i": str(last["id"])})
    if format == "csv":
        headers = {"X-Window-To": until.isoformat()}
        if next_cursor:
            headers["X-Next-Cursor"] = next_cursor
        return Response(files.to_csv(page, cols), media_type="text/csv", headers=headers)
    return {
        "object": name,
        "windowFrom": since.isoformat() if since else None,
        "windowTo": until.isoformat(),
        "rows": [{c.name: _json_value(r.get(c.name), c.type) for c in cols} for r in page],
        "nextCursor": next_cursor,
    }


@data_router.get("/objects/{name}/deleted", summary="Ids deleted from an object since a time")
async def object_deleted(name: str, changedSince: str = Query(...),
                         consumer: WarehouseConsumer = Depends(current_consumer),
                         session: AsyncSession = Depends(get_session)) -> dict:
    obj = _allowed(consumer, name)
    since, until = _parse_time(changedSince, "changedSince"), await extract.database_now(session)
    gone = await extract.deleted(session, consumer.tenant_id, obj, since=since, until=until)
    return {"object": name, "windowFrom": since.isoformat(), "windowTo": until.isoformat(),
            "rows": [{"id": str(g["id"]), "deletedAt": _json_value(g["deleted_at"], "timestamp")} for g in gone]}
