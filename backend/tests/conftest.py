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


@pytest.fixture(autouse=True)
def _fresh_review_cache():
    # The weekly review queue caches candidates in-process for 30s; one test's data must not
    # answer the next test's request.
    from app.modules.reviews.service import _CANDIDATE_CACHE

    _CANDIDATE_CACHE.clear()
    yield
    _CANDIDATE_CACHE.clear()
