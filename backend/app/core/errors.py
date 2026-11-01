"""Consistent application error types and the global error envelope.

Every error returned by the API has the shape::

    {"error": {"code": "...", "message": "..."}}

Internal stack traces are never exposed to API consumers.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, NoResultFound
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger("iris.errors")


class AppError(Exception):
    """Base class for all expected application errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "BAD_REQUEST"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        self.message = message
        if code:
            self.code = code
        super().__init__(message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"


class ValidationAppError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"


class AIServiceError(AppError):
    """Raised when Gemini is unavailable/invalid AND no fallback exists."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "AI_UNAVAILABLE"


def _error_metadata(status_code: int, code: str) -> tuple[str, bool, str | None]:
    code_upper = code.upper()
    if status_code == 422 or code_upper in {"VALIDATION_ERROR", "BAD_REQUEST"}:
        return "validation", False, "Correct the highlighted input and retry."
    if status_code == 401:
        return "authentication", False, "Sign in again, then retry."
    if status_code == 403:
        return "permission_denied", False, "Review the required permission or ask an administrator."
    if status_code == 404:
        return "not_found", False, None
    if status_code == 409:
        return "conflict", False, "Refresh the affected item and review its current state."
    if status_code == 429:
        return "rate_limited", True, "Wait briefly before retrying."
    if status_code == 502:
        return "upstream_failure", True, "Check the connected provider and retry."
    if status_code == 503:
        return "service_unavailable", True, "Check service status and retry when it is available."
    if status_code == 504:
        return "timeout", True, "The operation timed out; check its status before retrying."
    if status_code >= 500:
        return "internal", False, "Use the request ID when contacting support."
    return "request", False, None


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    request_id: str | None = None,
    category: str | None = None,
    retryable: bool | None = None,
    recovery_action: str | None = None,
) -> JSONResponse:
    default_category, default_retryable, default_recovery = _error_metadata(status_code, code)
    error = {
        "code": code,
        "message": message,
        "category": category or default_category,
        "retryable": default_retryable if retryable is None else retryable,
        "recovery_action": recovery_action if recovery_action is not None else default_recovery,
    }
    if request_id:
        error["correlation_id"] = request_id
    return JSONResponse(
        status_code=status_code,
        content={"error": error},
        headers={"X-Request-ID": request_id} if request_id else None,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.info("application_error code=%s status=%s", exc.code, exc.status_code)
        return error_response(
            exc.status_code,
            exc.code,
            exc.message,
            request_id=getattr(request.state, "correlation_id", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        summary = "; ".join(
            f"{'.'.join(str(loc) for loc in err['loc'][1:])}: {err['msg']}"
            for err in exc.errors()[:5]
        )
        return error_response(
            422,
            "VALIDATION_ERROR",
            summary or "Invalid request.",
            request_id=getattr(request.state, "correlation_id", None),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("database_integrity_error")
        return error_response(
            status.HTTP_409_CONFLICT,
            "CONFLICT",
            "The request conflicts with existing data.",
            request_id=getattr(request, "state", None) and getattr(request.state, "correlation_id", None),
        )

    @app.exception_handler(NoResultFound)
    async def _no_result(request: Request, __exc: NoResultFound) -> JSONResponse:
        return error_response(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            "Resource not found.",
            request_id=getattr(request.state, "correlation_id", None),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
        }
        code = codes.get(exc.status_code, "HTTP_ERROR")
        # Provider/SQL/server details may include user content, secrets, URLs,
        # and internal host paths. They belong in server diagnostics only.
        safe_message = (
            "An upstream service failed."
            if exc.status_code == 502
            else "The service is temporarily unavailable."
            if exc.status_code == 503
            else "The operation timed out."
            if exc.status_code == 504
            else "An unexpected internal error occurred."
            if exc.status_code >= 500
            else str(exc.detail)
        )
        return error_response(
            exc.status_code,
            code,
            safe_message,
            request_id=getattr(request.state, "correlation_id", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "An unexpected internal error occurred.",
            request_id=getattr(request.state, "correlation_id", None),
        )
