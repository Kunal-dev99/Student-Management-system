"""FastAPI app factory and router registration (arch §5, §6, §18)."""
from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import text

from app.api.v1.routes import api_router
from app.core.config import get_settings
from app.core.database import engine
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.audit import AuditMiddleware
from app.core.middleware import RequestContextMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="PGR Platform API",
        version="0.1.0",
        description="Postgraduate Research Student Lifecycle Management Platform",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url=f"{settings.api_v1_prefix}/docs",
    )

    # Both are pure ASGI middleware (not BaseHTTPMiddleware) — see core/middleware for why.
    # Order matters: RequestContextMiddleware is added last so it runs *outermost*, stamping
    # request_id into the scope before AuditMiddleware reads it on the way out (arch §17).
    app.add_middleware(AuditMiddleware)
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    # Liveness: process is up. No dependencies checked (arch §18).
    @app.get("/health/live", tags=["health"])
    async def health_live() -> dict:
        return {"status": "live"}

    # Readiness: dependencies reachable (DB now; broker added with the worker tier).
    @app.get("/health/ready", tags=["health"])
    async def health_ready() -> dict:
        checks: dict[str, str] = {}
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:  # pragma: no cover - readiness surfaces the failure
            checks["database"] = f"error: {exc.__class__.__name__}"
        status = "ready" if all(v == "ok" for v in checks.values()) else "degraded"
        return {"status": status, "checks": checks}

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
