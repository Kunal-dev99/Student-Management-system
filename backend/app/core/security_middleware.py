"""G7 enterprise hardening — security response headers + auth rate limit.

Both are implemented as pure ASGI middleware (matching ``core/middleware.py``) so they don't add
a per-request task or memory-object stream (``BaseHTTPMiddleware`` deadlocked under concurrent
load in this app — see the comment there).

* :class:`SecurityHeadersMiddleware` — adds the OWASP baseline response headers on every
  response. HSTS is enabled only for HTTPS (the ``x-forwarded-proto`` boundary a reverse proxy
  sets, or a genuine TLS scope) so local ``http://127.0.0.1`` dev still works.

* :class:`AuthRateLimitMiddleware` — a sliding-window per-IP limiter on the auth endpoints
  most likely to be brute-forced (``/auth/login`` and ``/auth/password-reset/request``). Storage
  is in-process (fine for the single-node ICR install today); the interface is small enough that
  swapping in Redis-backed storage later is a few lines. Beyond the threshold the middleware
  short-circuits with **HTTP 429** and a ``Retry-After`` header — no DB query, no bcrypt work,
  so the limit itself doesn't become a DoS amplifier.
"""
from __future__ import annotations

import collections
import time
from collections.abc import Iterable

# --- constants ----------------------------------------------------------------

# Header set: nosniff (block MIME-sniffing), DENY framing (clickjacking), no-referrer-on-crossorigin
# (least leaky privacy-preserving default), tight Permissions-Policy (no browser sensor APIs).
_STATIC_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"geolocation=(), microphone=(), camera=(), payment=()"),
]
# HSTS: 6 months, include subdomains, and preload-eligible. Only sent over HTTPS so local dev
# on http://127.0.0.1 isn't asked to remember an https upgrade it can't satisfy.
_HSTS_HEADER: tuple[bytes, bytes] = (
    b"strict-transport-security", b"max-age=15552000; includeSubDomains; preload",
)


def _is_https(scope) -> bool:
    """True when the request reached us over TLS, either directly (scope['scheme']) or through a
    reverse proxy that set x-forwarded-proto (uvicorn --forwarded-allow-ips propagates this)."""
    if scope.get("scheme") == "https":
        return True
    for name, value in scope.get("headers") or []:
        if name == b"x-forwarded-proto" and value.lower() == b"https":
            return True
    return False


class SecurityHeadersMiddleware:
    """Add OWASP baseline response headers on every response."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        https = _is_https(scope)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                existing = {h[0].lower() for h in headers}
                for k, v in _STATIC_HEADERS:
                    if k not in existing:
                        headers.append((k, v))
                if https and _HSTS_HEADER[0] not in existing:
                    headers.append(_HSTS_HEADER)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


# --- rate limit ---------------------------------------------------------------

# Default policy — safe for interactive humans, painful for brute-force scripts.
# 10 requests / 60s per IP per endpoint means a normal user's typos are fine, but 100k
# guesses/day per IP would take about 10 000 minutes (7 days) with no burst — combined with
# bcrypt's own cost this is a hard wall in practice.
DEFAULT_RATE_LIMIT = 10
DEFAULT_WINDOW_SECS = 60.0

# Paths that get the tighter budget. Keep this list explicit — the middleware skips everything
# else so a normal API user can't be rate-limited into breaking the app.
DEFAULT_PROTECTED_PATHS: tuple[str, ...] = (
    "/api/v1/auth/login",
    "/api/v1/auth/password-reset/request",
)


def _client_ip(scope) -> str:
    """Prefer the leftmost x-forwarded-for entry when we're behind a proxy, else the raw client.
    Falls back to a stable placeholder when neither is present so keys don't collide across
    unknown clients."""
    for name, value in scope.get("headers") or []:
        if name == b"x-forwarded-for":
            first = value.split(b",", 1)[0].strip()
            if first:
                return first.decode("latin-1", errors="replace")
    client = scope.get("client")
    if client:
        return str(client[0])
    return "unknown"


class AuthRateLimitMiddleware:
    """Sliding-window per-IP per-path limiter for the auth endpoints most likely to be brute-forced.

    Storage is in-process: ``self._hits`` is a ``{(ip, path): deque[timestamps]}`` — bounded
    because we prune everything older than the window on each hit, and only the protected paths
    (a handful) create keys.
    """

    def __init__(
        self,
        app,
        *,
        limit: int = DEFAULT_RATE_LIMIT,
        window_secs: float = DEFAULT_WINDOW_SECS,
        protected_paths: Iterable[str] = DEFAULT_PROTECTED_PATHS,
        clock=time.monotonic,
    ) -> None:
        self.app = app
        self.limit = limit
        self.window = window_secs
        self.protected = frozenset(protected_paths)
        self._hits: dict[tuple[str, str], collections.deque] = {}
        self._clock = clock

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        if path not in self.protected:
            return await self.app(scope, receive, send)

        ip = _client_ip(scope)
        now = self._clock()
        cutoff = now - self.window
        bucket = self._hits.setdefault((ip, path), collections.deque())
        # Prune expired timestamps in one pass so the bucket stays bounded by `limit`.
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= self.limit:
            oldest = bucket[0]
            retry_after = max(1, int(self.window - (now - oldest)) + 1)
            return await self._reject(send, retry_after)

        bucket.append(now)
        return await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send, retry_after: int) -> None:
        body = (
            b'{"error":{"code":"rate_limited",'
            b'"message":"Too many attempts. Wait a minute and try again."}}'
        )
        await send({
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"retry-after", str(retry_after).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})
