"""Base Tool interface and execution primitives for the IRIS Agent."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from enum import Enum
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.ai.provider import ToolDefinition
from app.ai.structured import compact_schema
from app.core.logging import get_logger
from app.models.user import User
from app.utils.datetime import from_local, to_local

logger = get_logger("iris.agent.tools.base")

TParams = TypeVar("TParams", bound=BaseModel)


class RiskLevel(str, Enum):
    """Execution risk classification for IRIS tools."""

    READ_ONLY = "READ_ONLY"
    REVERSIBLE = "REVERSIBLE"
    ORDINARY_WRITE = "ORDINARY_WRITE"
    SENSITIVE = "SENSITIVE"


class VerificationStrategy(str, Enum):
    """Postcondition verification mechanism."""

    NONE = "none"
    DB_CHECK = "db_check"
    FILE_CHECK = "file_check"
    PROCESS_CHECK = "process_check"
    CUSTOM = "custom"

# The model works in the user's local time (that is the clock it is shown), while
# the database stores naive UTC. Tools convert at this boundary in both directions.
_NAIVE_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$")


def times_to_utc(value: Any, tz_name: str) -> Any:
    """Model input -> storage: naive times are the user's local time; aware ones are exact."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return from_local(value, tz_name)
        return value.astimezone(UTC).replace(tzinfo=None)
    if isinstance(value, dict):
        return {k: times_to_utc(v, tz_name) for k, v in value.items()}
    if isinstance(value, list):
        return [times_to_utc(v, tz_name) for v in value]
    return value


def times_to_local(value: Any, tz_name: str) -> Any:
    """Storage -> model output: stored naive-UTC times become local times with an offset."""
    if isinstance(value, datetime):
        value = value if value.tzinfo is None else value.astimezone(UTC).replace(tzinfo=None)
        return to_local(value, tz_name).isoformat(timespec="minutes")
    if isinstance(value, str) and _NAIVE_ISO.match(value):
        try:
            return to_local(datetime.fromisoformat(value), tz_name).isoformat(timespec="minutes")
        except ValueError:
            return value
    if isinstance(value, dict):
        return {k: times_to_local(v, tz_name) for k, v in value.items()}
    if isinstance(value, list):
        return [times_to_local(v, tz_name) for v in value]
    return value


class Tool(ABC):
    """Abstract base class for all IRIS Agent tools."""

    name: str
    description: str
    parameters_schema: type[BaseModel] | None = None
    is_destructive: bool = False
    # None = infer from the name (get_/list_/search_ tools are read-only).
    read_only: bool | None = None
    risk_level: RiskLevel = RiskLevel.ORDINARY_WRITE
    verification_strategy: VerificationStrategy = VerificationStrategy.NONE
    requires_approval: bool = False
    idempotent: bool = False
    category: str = "general"

    @property
    def mutates_state(self) -> bool:
        if self.read_only is not None:
            return not self.read_only
        return not self.name.startswith(("get_", "list_", "search_"))

    @abstractmethod
    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        """Execute the tool against IRIS domain services and database."""
        ...

    async def verify(self, db: Session, user: User, result: ToolResult, **kwargs: Any) -> bool:
        """Verify that the tool's intended postconditions actually occurred.

        Subclasses override this to independently inspect the database, filesystem,
        or running processes to guarantee that the mutation actually took effect.
        Returns True if verified, False if state does not match expectations.
        """
        return result.success

    async def execute(self, db: Session, user: User, **raw_params: Any) -> ToolResult:
        """Validates parameters, enforces policy/approval gates, executes tool, and verifies postconditions."""
        # 1. Deterministic Approval Gate for sensitive/destructive operations
        if (self.requires_approval or (self.risk_level == RiskLevel.SENSITIVE and self.is_destructive)) and not raw_params.get("approval_token"):
            try:
                from app.execution.policy import default_policy
                from app.execution.contracts import PermissionClass
                perm_class = PermissionClass.CLASS_C_SENSITIVE if self.risk_level == RiskLevel.SENSITIVE else PermissionClass.CLASS_B_ROUTINE
                appr_token, prompt = default_policy.issue_approval_token(
                    command=f"{self.name}({raw_params})",
                    cwd="IRIS_SYSTEM",
                    permission_class=perm_class,
                )
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="APPROVAL_REQUIRED",
                    summary=prompt or f"Action '{self.name}' requires explicit approval before execution. Approval token: `{appr_token}`.",
                    data={
                        "status": "APPROVAL_REQUIRED",
                        "approval_token": appr_token,
                        "tool_name": self.name,
                        "parameters": raw_params,
                    },
                    verified=False,
                )
            except Exception as pol_err:
                logger.warning("Could not create approval token for %s: %s", self.name, pol_err)

        # 2. Parameter Validation
        validated_params = raw_params
        if self.parameters_schema is not None:
            try:
                model_instance = self.parameters_schema.model_validate(raw_params)
                validated_params = times_to_utc(model_instance.model_dump(exclude_unset=True), user.timezone)
            except ValidationError as err:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=f"Invalid parameters for {self.name}: {err}",
                    summary=f"Failed to execute {self.name} due to invalid parameters.",
                    verified=False,
                )

        # 3. Execution
        try:
            result = await self.run(db, user, **validated_params)
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Tool execution failed: {type(exc).__name__}: {exc}",
                summary=f"Encountered an error executing {self.name}.",
                verified=False,
            )

        # 4. Authoritative Postcondition Verification
        if result.success and self.mutates_state and self.verification_strategy != VerificationStrategy.NONE:
            try:
                is_verified = await self.verify(db, user, result, **validated_params)
                result.verified = bool(is_verified)
                if not is_verified:
                    result.verification_error = f"Postcondition verification failed: Expected changes from '{self.name}' could not be verified in authoritative state."
                    logger.warning(
                        "Postcondition verification FAILED for %s (user_id=%s, params=%s)",
                        self.name,
                        user.id,
                        validated_params,
                    )
            except Exception as v_exc:
                result.verified = False
                result.verification_error = f"Postcondition verification raised an exception: {v_exc}"
                logger.warning(
                    "Postcondition verification EXCEPTION for %s: %s",
                    self.name,
                    v_exc,
                )
        elif result.success and result.verified is None:
            result.verified = True

        result.data = times_to_local(result.data, user.timezone)
        return result

    def to_spec(self) -> dict[str, Any]:
        """Export tool definition for LLM system prompt context."""
        spec = {
            "name": self.name,
            "description": self.description,
            "is_destructive": self.is_destructive,
            "risk_level": self.risk_level.value if hasattr(self.risk_level, "value") else str(self.risk_level),
            "category": self.category,
        }
        if self.parameters_schema is not None:
            spec["parameters"] = self.parameters_schema.model_json_schema()
        else:
            spec["parameters"] = {}
        return spec
        if self.parameters_schema is not None:
            spec["parameters"] = self.parameters_schema.model_json_schema()
        else:
            spec["parameters"] = {}
        return spec

    def to_tool_definition(self) -> ToolDefinition:
        """Export a provider-neutral definition for native tool calling."""
        if self.parameters_schema is not None:
            parameters = compact_schema(self.parameters_schema)
        else:
            parameters = {"type": "object", "properties": {}}
        parameters.setdefault("type", "object")
        parameters.setdefault("properties", {})
        description = self.description
        if self.is_destructive:
            description += " (Destructive: only call when the user clearly asked for it.)"
        return ToolDefinition(name=self.name, description=description, parameters=parameters)
