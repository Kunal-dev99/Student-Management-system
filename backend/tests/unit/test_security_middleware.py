"""Security middleware unit tests (G7 hardening).

Both middlewares are tiny and pure-ASGI, so they're tested directly against a fake ``send`` /
``receive`` — no ASGI test client, no DB, no auth path. That way a regression fails on the
middleware itself and not on some downstream drift.
"""
from __future__ import annotations

from app.core.security_middleware import (
    AuthRateLimitMiddleware,
    SecurityHeadersMiddleware,
)


# --- helpers ------------------------------------------------------------------

async def _noop_app(scope, receive, send):
    """A tiny ASGI app that returns 200 with an empty body — the transport we're testing wraps
    around this and either lets it through or short-circuits."""
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b""})


class _Recorder:
    """Captures ``send`` messages so tests can inspect the final response."""
    def __init__(self):
        self.messages: list[dict] = []

    async def __call__(self, message):
        self.messages.append(message)

    @property
    def start(self) -> dict:
        return next(m for m in self.messages if m["type"] == "http.response.start")

    @property
    def status(self) -> int:
        return self.start["status"]

    @property
    def headers(self) -> dict[str, str]:
        return {k.decode(): v.decode() for k, v in self.start.get("headers", [])}


def _http_scope(*, path: str = "/", scheme: str = "http", client: tuple[str, int] | None = None,
                extra_headers: list[tuple[bytes, bytes]] | None = None):
    return {
        "type": "http", "method": "GET", "path": path, "scheme": scheme,
        "client": client, "headers": list(extra_headers or []),
    }


async def _dummy_receive() -> dict:
    return {"type": "http.disconnect"}


# --- SecurityHeadersMiddleware -----------------------------------------------

import pytest


@pytest.mark.asyncio
async def test_baseline_security_headers_are_added_on_every_response():
    """nosniff, DENY framing, referrer policy and permissions-policy must be on every response —
    the OWASP baseline that costs nothing to ship and covers the easy attacks."""
    r = _Recorder()
    await SecurityHeadersMiddleware(_noop_app)(_http_scope(), _dummy_receive, r)
    h = r.headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert "strict-origin-when-cross-origin" in h["referrer-policy"]
    assert "geolocation=()" in h["permissions-policy"]


@pytest.mark.asyncio
async def test_hsts_is_only_sent_over_https_not_over_plain_http():
    """HSTS on a plain-http response would ask the browser to upgrade a scheme the server can't
    serve — local dev on http://127.0.0.1 would break. Only add it when we're truly on TLS."""
    r = _Recorder()
    await SecurityHeadersMiddleware(_noop_app)(_http_scope(scheme="http"), _dummy_receive, r)
    assert "strict-transport-security" not in r.headers

    r2 = _Recorder()
    await SecurityHeadersMiddleware(_noop_app)(_http_scope(scheme="https"), _dummy_receive, r2)
    assert r2.headers.get("strict-transport-security", "").startswith("max-age=")


@pytest.mark.asyncio
async def test_hsts_is_added_when_a_reverse_proxy_signals_https():
    """Behind uvicorn --forwarded-allow-ips the scope stays 'http' but x-forwarded-proto tells us
    the real client used TLS. HSTS must respect that."""
    r = _Recorder()
    scope = _http_scope(scheme="http",
                        extra_headers=[(b"x-forwarded-proto", b"https")])
    await SecurityHeadersMiddleware(_noop_app)(scope, _dummy_receive, r)
    assert "max-age=" in r.headers.get("strict-transport-security", "")


@pytest.mark.asyncio
async def test_headers_do_not_touch_websocket_or_lifespan_scopes():
    """WS / lifespan scopes must pass through the middleware unchanged — the security-header
    additions apply only to http responses. Assert by proving no security-headers are stamped
    onto a response from a non-http scope (the middleware short-circuits before the send_wrapper
    that would add them)."""
    r = _Recorder()
    await SecurityHeadersMiddleware(_noop_app)({"type": "lifespan"}, _dummy_receive, r)
    for msg in r.messages:
        if msg["type"] == "http.response.start":
            names = {h[0].lower() for h in msg.get("headers", [])}
            assert b"x-content-type-options" not in names
            assert b"strict-transport-security" not in names


# --- AuthRateLimitMiddleware -------------------------------------------------

def _clock_from(seq: list[float]):
    """A monotonic clock that returns the next value in seq on each call — deterministic time."""
    it = iter(seq)
    return lambda: next(it)


@pytest.mark.asyncio
async def test_rate_limit_lets_normal_traffic_through():
    """A protected path called within the limit must always be allowed to reach the app."""
    calls = []

    async def app(scope, receive, send):
        calls.append(scope["path"])
        await _noop_app(scope, receive, send)

    mw = AuthRateLimitMiddleware(app, limit=3, window_secs=60,
                                 protected_paths=("/api/v1/auth/login",),
                                 clock=_clock_from([0, 1, 2]))
    for _ in range(3):
        r = _Recorder()
        await mw(_http_scope(path="/api/v1/auth/login", client=("1.2.3.4", 0)),
                 _dummy_receive, r)
        assert r.status == 200
    assert calls == ["/api/v1/auth/login"] * 3


@pytest.mark.asyncio
async def test_rate_limit_short_circuits_beyond_the_threshold():
    """On the (limit+1)th hit within the window, respond 429 without touching the downstream app."""
    calls = []

    async def app(scope, receive, send):
        calls.append(True)
        await _noop_app(scope, receive, send)

    mw = AuthRateLimitMiddleware(app, limit=2, window_secs=60,
                                 protected_paths=("/api/v1/auth/login",),
                                 clock=_clock_from([0, 1, 2]))
    for _ in range(3):
        r = _Recorder()
        await mw(_http_scope(path="/api/v1/auth/login", client=("1.2.3.4", 0)),
                 _dummy_receive, r)
    # The third response is a 429 with Retry-After — and the app was NOT called that time.
    assert r.status == 429
    assert int(r.headers["retry-after"]) >= 1
    assert len(calls) == 2, "downstream must not run for the rate-limited attempt"


@pytest.mark.asyncio
async def test_rate_limit_recovers_after_the_window_passes():
    """A well-behaved user who waits out the window must be let in again — the limiter is a
    sliding window, not a permanent lockout."""
    async def app(scope, receive, send):
        await _noop_app(scope, receive, send)

    # 2 hits at t=0,1 fill the bucket; t=61 is outside the 60s window and must be allowed.
    mw = AuthRateLimitMiddleware(app, limit=2, window_secs=60,
                                 protected_paths=("/api/v1/auth/login",),
                                 clock=_clock_from([0, 1, 2, 61]))
    for _ in range(2):
        r = _Recorder()
        await mw(_http_scope(path="/api/v1/auth/login", client=("1.2.3.4", 0)),
                 _dummy_receive, r)
    r_blocked = _Recorder()
    await mw(_http_scope(path="/api/v1/auth/login", client=("1.2.3.4", 0)),
             _dummy_receive, r_blocked)
    assert r_blocked.status == 429
    r_ok = _Recorder()
    await mw(_http_scope(path="/api/v1/auth/login", client=("1.2.3.4", 0)),
             _dummy_receive, r_ok)
    assert r_ok.status == 200


@pytest.mark.asyncio
async def test_rate_limit_buckets_per_ip_so_one_attacker_doesnt_lock_out_everyone():
    """If IP A exhausts its budget, IP B must still be allowed through — otherwise a single
    attacker denies service to the whole tenant."""
    async def app(scope, receive, send):
        await _noop_app(scope, receive, send)

    mw = AuthRateLimitMiddleware(app, limit=1, window_secs=60,
                                 protected_paths=("/api/v1/auth/login",),
                                 clock=_clock_from([0, 1, 2, 3]))
    r_a1 = _Recorder(); r_a2 = _Recorder(); r_b1 = _Recorder()
    await mw(_http_scope(path="/api/v1/auth/login", client=("1.1.1.1", 0)), _dummy_receive, r_a1)
    await mw(_http_scope(path="/api/v1/auth/login", client=("1.1.1.1", 0)), _dummy_receive, r_a2)
    await mw(_http_scope(path="/api/v1/auth/login", client=("2.2.2.2", 0)), _dummy_receive, r_b1)
    assert r_a1.status == 200
    assert r_a2.status == 429    # A is over
    assert r_b1.status == 200    # B is untouched


@pytest.mark.asyncio
async def test_rate_limit_honours_x_forwarded_for_when_behind_a_proxy():
    """Without this, every request behind a reverse proxy appears to come from the same IP (the
    proxy's own) and the whole tenant would share one bucket."""
    async def app(scope, receive, send):
        await _noop_app(scope, receive, send)

    mw = AuthRateLimitMiddleware(app, limit=1, window_secs=60,
                                 protected_paths=("/api/v1/auth/login",),
                                 clock=_clock_from([0, 1, 2, 3]))
    proxy = ("10.0.0.1", 0)   # same proxy relaying two different real clients
    def hdr(ip: bytes) -> list:
        return [(b"x-forwarded-for", ip)]

    r1 = _Recorder()
    await mw(_http_scope(path="/api/v1/auth/login", client=proxy, extra_headers=hdr(b"1.1.1.1")),
             _dummy_receive, r1)
    r2 = _Recorder()
    await mw(_http_scope(path="/api/v1/auth/login", client=proxy, extra_headers=hdr(b"1.1.1.1")),
             _dummy_receive, r2)
    r3 = _Recorder()
    await mw(_http_scope(path="/api/v1/auth/login", client=proxy, extra_headers=hdr(b"2.2.2.2")),
             _dummy_receive, r3)
    assert r1.status == 200 and r2.status == 429 and r3.status == 200


@pytest.mark.asyncio
async def test_rate_limit_ignores_paths_it_wasnt_asked_to_protect():
    """A crawler hitting /api/v1/students isn't a brute-force risk; the limiter must not touch
    normal API paths."""
    calls = []

    async def app(scope, receive, send):
        calls.append(scope["path"])
        await _noop_app(scope, receive, send)

    mw = AuthRateLimitMiddleware(app, limit=1, window_secs=60,
                                 protected_paths=("/api/v1/auth/login",),
                                 clock=_clock_from([0, 1, 2, 3, 4]))
    for _ in range(5):
        r = _Recorder()
        await mw(_http_scope(path="/api/v1/students", client=("1.2.3.4", 0)),
                 _dummy_receive, r)
        assert r.status == 200
    assert len(calls) == 5
