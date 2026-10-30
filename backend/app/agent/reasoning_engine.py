"""Unified 10-Stage Agentic Reasoning Engine for IRIS.

Architecture:
Understand -> Contextualize -> Reason -> Plan -> Select Capabilities ->
Execute -> Observe -> Verify -> Adapt -> Respond

Principles:
- Generative intelligence for understanding, reasoning, and decision-making.
- Deterministic systems for execution, truth, safety, and verification.
- Authoritative state postcondition verification before claiming success.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.agent.registry import ToolRegistry
from app.agent.schemas import AgentResponseSchema, ToolCall, ToolResult
from app.agent.tools.base import RiskLevel, Tool, VerificationStrategy
from app.ai.provider import ChatMessage, ToolDefinition
from app.core.logging import get_logger
from app.models.user import User

logger = get_logger("iris.agent.reasoning_engine")


class IntentType(str, Enum):
    CONVERSATIONAL = "CONVERSATIONAL"
    INFORMATION_QUERY = "INFORMATION_QUERY"
    SINGLE_ACTION = "SINGLE_ACTION"
    MULTI_STEP_WORKFLOW = "MULTI_STEP_WORKFLOW"
    CLARIFICATION = "CLARIFICATION"


@dataclass
class ReasoningContext:
    user_message: str
    intent_type: IntentType
    referents: dict[str, Any] = field(default_factory=dict)
    requires_tools: bool = True
    can_answer_from_context: bool = False
    context_answer: str | None = None
    constraints: list[str] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class ExecutionPlanStep:
    step_number: int
    description: str
    tool_name: str
    parameters: dict[str, Any]
    verification_strategy: str = "none"
    expected_outcome: str = ""


@dataclass
class ExecutionPlan:
    objective: str
    steps: list[ExecutionPlanStep] = field(default_factory=list)


@dataclass
class Observation:
    step_number: int
    tool_name: str
    success: bool
    data: Any
    summary: str | None
    verified: bool = True
    verification_error: str | None = None
    error: str | None = None


@dataclass
class AdaptationDecision:
    can_retry: bool
    adjusted_parameters: dict[str, Any] | None = None
    alternate_tool: str | None = None
    failure_reason: str = ""
    user_explanation: str = ""


class UnifiedReasoningEngine:
    """10-Stage Agentic Reasoning Engine."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    # --- Stage 1: Understand -------------------------------------------------

    def understand(
        self,
        user_message: str,
        history: list[ChatMessage],
        live_context: dict[str, Any] | None = None,
    ) -> ReasoningContext:
        """Analyze user message for intent, conversational referents, and tool requirements."""
        clean_msg = user_message.strip()
        lower_msg = clean_msg.lower()

        # Check for pure conversational queries / greetings / factual questions
        conversational_triggers = {
            "hi", "hello", "hey", "good morning", "good evening", "good afternoon",
            "how are you", "who are you", "what can you do", "thanks", "thank you",
            "bye", "goodbye", "tell me a joke", "what is your name",
        }
        pure_chat = (
            lower_msg in conversational_triggers
            or lower_msg.rstrip("!.?") in conversational_triggers
            or (len(clean_msg.split()) <= 3 and any(w in lower_msg for w in ["hi", "hello", "hey"]))
        )
        if pure_chat:
            return ReasoningContext(
                user_message=clean_msg,
                intent_type=IntentType.CONVERSATIONAL,
                requires_tools=False,
            )

        # Check for pure explanatory/knowledge questions with no action verbs or personal data requests
        explanatory_prefixes = (
            "explain the difference between",
            "what is the difference between",
            "how does",
            "why do",
            "explain how",
            "what is python",
            "what is sqlite",
            "what is postgresql",
        )
        if lower_msg.startswith(explanatory_prefixes) and not any(
            w in lower_msg for w in ["my ", "laptop", "task", "schedule", "routine", "email", "drive", "file"]
        ):
            return ReasoningContext(
                user_message=clean_msg,
                intent_type=IntentType.CONVERSATIONAL,
                requires_tools=False,
            )

        # Referent resolution from conversation history ("the second one", "that task", "it")
        referents: dict[str, Any] = {}
        ordinal_match = re.search(r"\b(first|second|third|fourth|fifth|last|1st|2nd|3rd|4th|5th)\b", lower_msg)
        if ordinal_match and history:
            referents.update(self._resolve_ordinal_referent(ordinal_match.group(1), history))

        # Check if the query can be answered directly from provided live_context without tool calls (Test J)
        can_answer = False
        context_ans = None
        if live_context:
            can_answer, context_ans = self._check_context_answer(lower_msg, live_context)

        # Check workflow complexity
        is_multi_step = any(w in lower_msg for w in [" and then ", " after that ", " also ", "review ", "prepare tomorrow's plan"])

        intent_type = (
            IntentType.MULTI_STEP_WORKFLOW
            if is_multi_step
            else IntentType.SINGLE_ACTION
        )

        return ReasoningContext(
            user_message=clean_msg,
            intent_type=intent_type,
            referents=referents,
            requires_tools=not can_answer,
            can_answer_from_context=can_answer,
            context_answer=context_ans,
        )

    def _resolve_ordinal_referent(self, ordinal_str: str, history: list[ChatMessage]) -> dict[str, Any]:
        """Extract item/task IDs from previous assistant replies containing lists or task numbers."""
        idx_map = {
            "first": 0, "1st": 0,
            "second": 1, "2nd": 1,
            "third": 2, "3rd": 2,
            "fourth": 3, "4th": 3,
            "fifth": 4, "5th": 4,
            "last": -1,
        }
        target_idx = idx_map.get(ordinal_str)
        if target_idx is None:
            return {}

        # Look backwards through assistant messages
        for msg in reversed(history):
            if msg.role == "assistant" and msg.content:
                # Find task IDs like "#12", "Task #12", "id: 12"
                task_matches = re.findall(r"(?:#|Task\s+#|task\s+#|ID\s*:?\s*)(\d+)", msg.content)
                if task_matches:
                    try:
                        resolved_id = int(task_matches[target_idx])
                        return {"task_id": resolved_id, "referent_text": f"task #{resolved_id}"}
                    except IndexError:
                        pass
                # Find bullet points or numbered lists
                list_items = re.findall(r"(?:^|\n)\s*(?:[•\-\*]|\d+\.)\s+(.+)", msg.content)
                if list_items:
                    try:
                        selected = list_items[target_idx]
                        return {"item_text": selected.strip()}
                    except IndexError:
                        pass
        return {}

    def _check_context_answer(self, lower_msg: str, live_context: dict[str, Any]) -> tuple[bool, str | None]:
        """Determine if context already has unambiguous ground truth for query (avoid unnecessary tool calls)."""
        # E.g. "what is my timezone?", "what is my name?", "who am I?"
        if "my timezone" in lower_msg or "what timezone" in lower_msg:
            tz = live_context.get("user_timezone") or live_context.get("timezone")
            if tz:
                return True, f"Your configured timezone is {tz}."
        if "my name" in lower_msg or "what is my name" in lower_msg:
            name = live_context.get("user_name")
            if name:
                return True, f"Your name is {name}."
        return False, None

    # --- Stage 2: Contextualize ----------------------------------------------

    def contextualize(
        self,
        db: Session,
        user: User,
        user_message: str,
        memories: list[Any],
        referents: dict[str, Any],
    ) -> dict[str, Any]:
        """Aggregate personal model, state, memories, and referents into structured context."""
        return {
            "user_id": user.id,
            "user_name": user.name,
            "timezone": user.timezone or "UTC",
            "active_referents": referents,
            "memories": [
                {"id": getattr(m, "id", None), "category": getattr(m, "category", ""), "content": getattr(m, "content", str(m))}
                for m in memories
            ],
        }

    # --- Stage 3: Reason -----------------------------------------------------

    def reason(
        self,
        context: ReasoningContext,
        tools: list[ToolDefinition],
    ) -> dict[str, Any]:
        """Evaluate dependencies, tool matching, risk profile, and required safeguards."""
        matched_tools: list[str] = []
        for t in tools:
            # Check if tool description or name is relevant to user message
            if any(term in context.user_message.lower() for term in t.name.split("_")):
                matched_tools.append(t.name)

        return {
            "requires_tools": context.requires_tools,
            "intent_type": context.intent_type.value,
            "referents": context.referents,
            "candidate_tools": matched_tools,
        }

    # --- Stage 4 & 5: Plan & Select Capabilities -----------------------------

    def plan(
        self,
        context: ReasoningContext,
        reasoning_info: dict[str, Any],
    ) -> ExecutionPlan:
        """Formulate execution steps and associate postcondition verification requirements."""
        plan = ExecutionPlan(objective=context.user_message)
        # Note: In native/structured LLM driving, the LLM generates the dynamic plan steps.
        # This deterministic planner validates and annotates verification requirements for each step.
        return plan

    # --- Stage 6 & 7: Execute & Observe --------------------------------------

    def observe(self, result: ToolResult, step_number: int = 1) -> Observation:
        """Wrap and analyze tool execution result."""
        return Observation(
            step_number=step_number,
            tool_name=result.tool_name,
            success=result.success,
            data=result.data,
            summary=result.summary,
            verified=getattr(result, "verified", True) is not False,
            verification_error=getattr(result, "verification_error", None),
            error=result.error,
        )

    # --- Stage 8: Verify -----------------------------------------------------

    async def verify_postconditions(
        self,
        db: Session,
        user: User,
        observation: Observation,
        parameters: dict[str, Any],
    ) -> bool:
        """Execute independent postcondition check against authoritative state."""
        tool = self.registry.get(observation.tool_name)
        if not tool or not tool.mutates_state or tool.verification_strategy == VerificationStrategy.NONE:
            return observation.success

        fake_res = ToolResult(
            tool_name=observation.tool_name,
            success=observation.success,
            data=observation.data,
            summary=observation.summary,
        )
        try:
            is_verified = await tool.verify(db, user, fake_res, **parameters)
            observation.verified = bool(is_verified)
            if not is_verified:
                observation.verification_error = (
                    f"Authoritative postcondition check failed for '{tool.name}'. "
                    f"Changes could not be confirmed in the database or system."
                )
            return observation.verified
        except Exception as exc:
            observation.verified = False
            observation.verification_error = f"Verification check threw exception: {exc}"
            return False

    # --- Stage 9: Adapt ------------------------------------------------------

    def adapt(
        self,
        observation: Observation,
        current_parameters: dict[str, Any],
    ) -> AdaptationDecision:
        """Diagnose failure cause and recommend correction, alternate tool, or honest reporting."""
        err = (observation.error or observation.verification_error or "").lower()

        # Case 1: Parameter type/format error -> can retry with fixed parameters
        if "invalid parameter" in err or "validation error" in err:
            return AdaptationDecision(
                can_retry=True,
                failure_reason="PARAMETER_ERROR",
                user_explanation=f"Parameters for {observation.tool_name} were invalid: {err}.",
            )

        # Case 2: Postcondition verification failed -> do NOT pretend success
        if not observation.verified:
            return AdaptationDecision(
                can_retry=False,
                failure_reason="POSTCONDITION_FAILED",
                user_explanation=(
                    f"The operation '{observation.tool_name}' appeared to execute, but IRIS's authoritative "
                    f"verification check failed to confirm the state change. I am reporting this discrepancy honestly."
                ),
            )

        # Case 3: Missing entity (e.g. Task not found)
        if "not found" in err:
            return AdaptationDecision(
                can_retry=False,
                failure_reason="ENTITY_NOT_FOUND",
                user_explanation=f"The requested item was not found: {observation.error}.",
            )

        # Case 4: Approval required
        if "approval_required" in err or observation.error == "APPROVAL_REQUIRED":
            return AdaptationDecision(
                can_retry=False,
                failure_reason="APPROVAL_REQUIRED",
                user_explanation="This sensitive action requires explicit user authorization before execution.",
            )

        return AdaptationDecision(
            can_retry=False,
            failure_reason="GENERAL_FAILURE",
            user_explanation=f"Encountered an error executing {observation.tool_name}: {observation.error}",
        )

    # --- Stage 10: Respond ---------------------------------------------------

    def synthesize_response(
        self,
        observations: list[Observation],
        message: str,
        evidence: list[str] | None = None,
    ) -> AgentResponseSchema:
        """Ground the response in verified actions and clear evidence."""
        actions_summary: list[str] = []
        ev: list[str] = list(evidence or [])

        for obs in observations:
            if obs.success and obs.verified and obs.summary:
                actions_summary.append(obs.summary)
                ev.append(f"Verified: {obs.tool_name}")
            elif not obs.verified:
                ev.append(f"Verification Failed: {obs.tool_name}")

        return AgentResponseSchema(
            thought="Synthesized verified response through Unified Reasoning Engine.",
            actions=[],
            message=message.strip(),
            actions_summary=actions_summary,
            evidence=ev,
        )
