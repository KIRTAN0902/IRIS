"""Request Deadline and Budget Management for AI Invocations.

Propagates a single unified deadline across provider retries, multi-tier
failovers, tool executions, and structured-output recovery attempts.
"""

from __future__ import annotations

import time
from contextvars import ContextVar, Token
from typing import Any

import httpx

_DEFAULT_MIN_REMAINING_FOR_ATTEMPT = 2.5
_DEFAULT_CONNECT_TIMEOUT = 5.0
_DEFAULT_WRITE_TIMEOUT = 10.0
_DEFAULT_POOL_TIMEOUT = 5.0


class RequestDeadline:
    """Tracks elapsed time and remaining budget against a fixed deadline."""

    def __init__(
        self,
        total_seconds: float,
        *,
        min_remaining_for_attempt: float = _DEFAULT_MIN_REMAINING_FOR_ATTEMPT,
    ) -> None:
        self.total_seconds = max(1.0, float(total_seconds))
        self.start_time = time.monotonic()
        self.deadline = self.start_time + self.total_seconds
        self.min_remaining_for_attempt = min_remaining_for_attempt

    @property
    def remaining(self) -> float:
        """Seconds remaining before deadline expires (non-negative)."""
        return max(0.0, self.deadline - time.monotonic())

    @property
    def elapsed(self) -> float:
        """Seconds elapsed since deadline was created."""
        return time.monotonic() - self.start_time

    @property
    def is_expired(self) -> bool:
        """True when no time budget remains."""
        return self.remaining <= 0.0

    @property
    def has_budget_for_attempt(self) -> bool:
        """True if sufficient time remains to justify starting a new network call."""
        return self.remaining >= self.min_remaining_for_attempt

    def per_attempt_timeout(self, max_per_attempt: float | None = None) -> float:
        """Compute the maximum read timeout allowable for the next attempt."""
        rem = self.remaining
        if max_per_attempt is not None and max_per_attempt > 0:
            return min(rem, max_per_attempt)
        return rem

    def httpx_timeout(
        self,
        max_read: float | None = None,
        *,
        connect: float = _DEFAULT_CONNECT_TIMEOUT,
        write: float = _DEFAULT_WRITE_TIMEOUT,
        pool: float = _DEFAULT_POOL_TIMEOUT,
    ) -> httpx.Timeout:
        """Build an httpx.Timeout object bounded by the remaining request deadline."""
        rem = self.remaining
        read_timeout = max(0.5, self.per_attempt_timeout(max_read))
        connect_timeout = min(connect, rem) if rem > 0 else 0.5
        write_timeout = min(write, rem) if rem > 0 else 0.5
        pool_timeout = min(pool, rem) if rem > 0 else 0.5
        return httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=write_timeout,
            pool=pool_timeout,
        )

    def __repr__(self) -> str:
        return f"<RequestDeadline total={self.total_seconds:.1f}s remaining={self.remaining:.1f}s elapsed={self.elapsed:.1f}s>"


current_deadline: ContextVar[RequestDeadline | None] = ContextVar(
    "current_deadline", default=None
)


def get_current_deadline() -> RequestDeadline | None:
    """Retrieve the active RequestDeadline if set in the current async context."""
    return current_deadline.get()


def set_deadline(
    total_seconds: float,
    *,
    min_remaining_for_attempt: float = _DEFAULT_MIN_REMAINING_FOR_ATTEMPT,
) -> Token:
    """Set the active RequestDeadline for the current context."""
    return current_deadline.set(
        RequestDeadline(
            total_seconds,
            min_remaining_for_attempt=min_remaining_for_attempt,
        )
    )


def reset_deadline(token: Token) -> None:
    """Reset the RequestDeadline ContextVar to its prior state."""
    current_deadline.reset(token)
