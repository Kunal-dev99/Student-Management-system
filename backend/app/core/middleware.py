"""Request-id, timing, and one structured access-log line per request (arch §6.2, §18)."""
from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("pgr.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex}"
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request",
            extra={
                "requestId": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "durationMs": duration_ms,
            },
        )
        return response
