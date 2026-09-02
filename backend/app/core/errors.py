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


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        logger.info("AppError %s: %s", exc.code, exc.message)
        return error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        summary = "; ".join(
            f"{'.'.join(str(loc) for loc in err['loc'][1:])}: {err['msg']}"
            for err in exc.errors()[:5]
        )
        return error_response(422, "VALIDATION_ERROR", summary or "Invalid request.")

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("IntegrityError: %s", exc.orig if hasattr(exc, "orig") else exc)
        return error_response(
            status.HTTP_409_CONFLICT, "CONFLICT", "The request conflicts with existing data."
        )

    @app.exception_handler(NoResultFound)
    async def _no_result(_: Request, __exc: NoResultFound) -> JSONResponse:
        return error_response(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Resource not found.")

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
        }
        code = codes.get(exc.status_code, "HTTP_ERROR")
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "An unexpected internal error occurred.",
        )
