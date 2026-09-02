"""Base Tool interface and execution primitives for the IRIS Agent."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.models.user import User

TParams = TypeVar("TParams", bound=BaseModel)


class Tool(ABC):
    """Abstract base class for all IRIS Agent tools."""

    name: str
    description: str
    parameters_schema: type[BaseModel] | None = None
    is_destructive: bool = False

    @abstractmethod
    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        """Execute the tool against IRIS domain services and database."""
        ...

    async def execute(self, db: Session, user: User, **raw_params: Any) -> ToolResult:
        """Validates parameters, enforces user boundaries, and executes tool safely."""
        validated_params = raw_params
        if self.parameters_schema is not None:
            try:
                model_instance = self.parameters_schema.model_validate(raw_params)
                validated_params = model_instance.model_dump(exclude_unset=True)
            except ValidationError as err:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=f"Invalid parameters for {self.name}: {err}",
                    summary=f"Failed to execute {self.name} due to invalid parameters.",
                )

        try:
            return await self.run(db, user, **validated_params)
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Tool execution failed: {type(exc).__name__}: {exc}",
                summary=f"Encountered an error executing {self.name}.",
            )

    def to_spec(self) -> dict[str, Any]:
        """Export tool definition for LLM system prompt context."""
        spec = {
            "name": self.name,
            "description": self.description,
            "is_destructive": self.is_destructive,
        }
        if self.parameters_schema is not None:
            spec["parameters"] = self.parameters_schema.model_json_schema()
        else:
            spec["parameters"] = {}
        return spec
