"""Environment-aware provider boundary for work that may outlive an API request.

The API process may schedule local work only when it is a persistent host. A
serverless invocation must never claim that process-local background work is
durable. A separately hosted worker can implement this contract without
coupling domain services to a deployment vendor.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, Protocol


ExecutionKind = Literal["coworker", "coding_agent", "mesh_files"]


@dataclass(frozen=True)
class ExecutionStatus:
    available: bool
    provider: str
    reason: str | None = None


class ExecutionProvider(Protocol):
    def status(self, kind: ExecutionKind) -> ExecutionStatus: ...


def is_serverless_runtime() -> bool:
    """Return whether this process has invocation-scoped serverless lifecycle."""
    return bool(
        os.environ.get("VERCEL")
        or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
        or os.environ.get("SERVERLESS", "").lower() == "true"
    )


class LocalExecutionProvider:
    """Existing local execution services, available only on a persistent host."""

    def status(self, kind: ExecutionKind) -> ExecutionStatus:
        if is_serverless_runtime():
            return ExecutionStatus(
                available=False,
                provider="unavailable",
                reason=(
                    f"{kind.replace('_', ' ').capitalize()} requires a persistent IRIS execution host. "
                    "Configure a persistent worker/API host and retry."
                ),
            )
        return ExecutionStatus(available=True, provider="local")


def get_execution_provider() -> ExecutionProvider:
    """Select the provider without binding application services to Vercel."""
    # The local provider is the current supported execution implementation.
    # Remote providers can implement this Protocol and be selected here once a
    # durable worker transport is configured; request-scoped tasks are not used
    # as a substitute in the meantime.
    return LocalExecutionProvider()


def require_execution(kind: ExecutionKind) -> ExecutionStatus:
    """Return provider status or raise when the requested execution is absent."""
    status = get_execution_provider().status(kind)
    if not status.available:
        from app.core.errors import ExecutionProviderUnavailableError

        raise ExecutionProviderUnavailableError(status.reason or "Execution is unavailable.")
    return status
