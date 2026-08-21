"""Unit tests for core helpers (BE-0.4 error envelope, BE-0.5 pagination)."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import NotFoundError, register_error_handlers
from app.core.middleware import RequestContextMiddleware
from app.core.pagination import decode_cursor, encode_cursor, list_envelope


def test_list_envelope_shape():
    env = list_envelope([{"id": "a"}], limit=25, total=1, next_cursor=None)
    assert env == {"data": [{"id": "a"}], "page": {"limit": 25, "nextCursor": None, "total": 1}}


def test_cursor_roundtrip():
    payload = {"lastId": "abc", "createdAt": "2026-01-01"}
    assert decode_cursor(encode_cursor(payload)) == payload


@pytest.mark.asyncio
async def test_error_envelope_and_status():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    @app.get("/boom")
    async def boom():
        raise NotFoundError("Student not found")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/boom")
    assert r.status_code == 404
    body = r.json()["error"]
    assert body["code"] == "not_found"
    assert body["message"] == "Student not found"
    assert body["requestId"].startswith("req_")
    assert body["details"] == []
