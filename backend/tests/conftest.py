from __future__ import annotations

import os

# G7 — the auth rate limit is on by default in production; disable it in tests so a whole
# suite's worth of logins from the same in-memory client doesn't get short-circuited with 429.
# The rate limiter itself is covered directly by tests/unit/test_security_middleware.py.
# Must be set BEFORE `app.main` is imported (middleware stack is built at import time).
os.environ.setdefault("AUTH_RATE_LIMIT_ENABLED", "false")

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
