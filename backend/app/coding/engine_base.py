"""Provider-neutral abstraction for coding engines (Antigravity, future engines)."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, AsyncIterator


@dataclass
class EngineEvent:
    event_type: str  # "token", "thought", "tool_call", "tool_result", "diff", "error", "done"
    payload: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class EngineSessionInfo:
    session_id: str
    engine_name: str
    workspace_dir: str
    conversation_id: str | None = None
    is_active: bool = False
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


class ICodingEngine(abc.ABC):
    """Abstract interface defining required capabilities for any coding engine in IRIS."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique identifier for this coding engine (e.g. 'antigravity')."""
        ...

    @abc.abstractmethod
    def detect(self) -> dict[str, Any]:
        """Detect binary, SDK presence, authenticated models, and system capabilities."""
        ...

    @abc.abstractmethod
    def start_session(
        self,
        workspace_dir: str,
        session_id: str,
        conversation_id: str | None = None,
        permissions: dict[str, Any] | None = None,
    ) -> EngineSessionInfo:
        """Initialize an execution session inside the isolated workspace."""
        ...

    @abc.abstractmethod
    def submit_prompt(self, session_id: str, prompt: str) -> None:
        """Submit a prompt or follow-up instruction to an active engine session."""
        ...

    @abc.abstractmethod
    def stream_events(self, session_id: str) -> list[EngineEvent]:
        """Retrieve new events emitted since last check."""
        ...

    @abc.abstractmethod
    def stop(self, session_id: str) -> bool:
        """Gracefully interrupt or terminate active execution processes."""
        ...

    @abc.abstractmethod
    def get_diff(self, workspace_dir: str) -> dict[str, Any]:
        """Inspect uncommitted file modifications and stats in the workspace."""
        ...
