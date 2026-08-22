"""Request-id, timing, and one structured access-log line per request (arch §6.2, §18).

Implemented as **pure ASGI middleware**, deliberately not Starlette's `BaseHTTPMiddleware`:
BaseHTTPMiddleware runs each request inside an anyio task group and pumps the response body
through memory object streams. That serialises throughput, and stacking two such layers
(request-context + audit) deadlocked the app under concurrency. Pure ASGI wraps `send` to observe
the status code and adds no per-request task or stream.
"""
from __future__ import annotations

import logging
import time
import uuid

logger = logging.getLogger("pgr.access")


class RequestContextMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers") or [])
        raw_id = headers.get(b"x-request-id")
        request_id = raw_id.decode("latin-1") if raw_id else f"req_{uuid.uuid4().hex}"
        # Starlette's `request.state` reads scope["state"], so routes can use request.state.request_id.
        scope.setdefault("state", {})["request_id"] = request_id

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", [])
                message["headers"].append((b"x-request-id", request_id.encode("latin-1")))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "request",
                extra={
                    "requestId": request_id,
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status_code,
                    "durationMs": duration_ms,
                },
            )
