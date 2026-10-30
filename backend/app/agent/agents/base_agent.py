"""BaseSubAgent: Foundation for specialized domain worker agents."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.agent.harness import AgentHarness, HarnessResult
from app.agent.registry import ToolRegistry
from app.agent.tools.base import Tool
from app.ai.factory import create_ai_provider
from app.ai.provider import AIProvider
from app.models.user import User


@dataclass
class SubAgentReport:
    agent_name: str
    success: bool
    summary: str
    actions_executed: list[dict[str, Any]] = field(default_factory=list)
    raw_response: str = ""
    error: str | None = None


class BaseSubAgent:
    """A specialized headless agent with its own scoped tools and dedicated model."""

    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str,
        tools: list[Tool],
        model_spec: str,
        max_steps: int = 6,
    ) -> None:
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.model_spec = model_spec

        # Create isolated tool registry for this agent
        self.registry = ToolRegistry()
        for t in tools:
            self.registry.register(t)

        # Initialize dedicated AI provider
        self.provider: AIProvider = create_ai_provider(model_spec)
        self.harness = AgentHarness(self.registry, max_steps=max_steps)

    async def execute(
        self,
        db: Session,
        user: User,
        instruction: str,
        context: dict[str, Any] | None = None,
        history: list[ChatMessage] | None = None,
    ) -> SubAgentReport:
        """Run the sub-agent loop against the user instruction and return an execution report."""
        extra_ctx = ""
        if context:
            extra_ctx = f"\n\nLIVE CONTEXT:\n{json.dumps(context, default=str)}"

        full_system = f"{self.system_prompt}{extra_ctx}"

        try:
            result: HarnessResult = await self.harness.run(
                provider=self.provider,
                db=db,
                user=user,
                system_prompt=full_system,
                history=history or [],
                user_message=instruction,
            )

            msg = result.response.message or "Task completed."
            return SubAgentReport(
                agent_name=self.name,
                success=True,
                summary=msg,
                actions_executed=result.actions_executed,
                raw_response=msg,
            )
        except Exception as exc:
            return SubAgentReport(
                agent_name=self.name,
                success=False,
                summary=f"Failed to execute instruction with {self.name}: {exc}",
                error=str(exc),
            )
