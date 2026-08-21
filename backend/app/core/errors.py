"""One exception hierarchy + a single handler that renders the standard error envelope.

Arch §6.4 and Appendix B. Unhandled exceptions return a generic 500 with a request id
and never leak internals.
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    code: str = "internal_error"
    http_status: int = 500

    def __init__(self, message: str, details: list | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or []


class ValidationAppError(AppError):
    code = "validation_error"
    http_status = 400


class AuthError(AppError):
    code = "unauthenticated"
    http_status = 401


class PermissionError(AppError):  # noqa: A001 - domain name intended
    code = "permission_denied"
    http_status = 403


class NotFoundError(AppError):
    code = "not_found"
    http_status = 404


class ConflictError(AppError):
    code = "conflict"
    http_status = 409


class WorkflowError(AppError):
    code = "workflow_error"
    http_status = 422


class IntegrationError(AppError):
    code = "integration_error"
    http_status = 502


def _envelope(code: str, message: str, request_id: str, details: list) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "requestId": request_id,
            "details": details,
        }
    }


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=exc.http_status,
        content=_envelope(exc.code, exc.message, request_id, exc.details),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=500,
        content=_envelope("internal_error", "Unexpected failure", request_id, []),
    )


def register_error_handlers(app) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
