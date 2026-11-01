"""Structured logging.

Logs API errors, AI requests/failures, and important state changes.
Never logs API keys, tokens, or raw conversation content at INFO level.
"""

import logging
import sys
from contextvars import ContextVar


request_id_context: ContextVar[str] = ContextVar("iris_request_id", default="-")


class RequestContextFilter(logging.Filter):
    """Attach the current request correlation ID without logging user content."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_context.get()
        return True

from app.core.config import settings


def setup_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | request_id=%(request_id)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(RequestContextFilter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Third-party noise reduction.
    for noisy in ("httpx", "httpcore", "google_genai", "alembic"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
