"""Model-agnostic agent harness.

The harness is what turns "a model" into "IRIS". It owns the loop, the tools
and the safety rails; the model only decides what to say and which tool to
call next. Whatever model is configured, the harness picks the strongest way
to drive it from its ``ModelCapabilities``:

1. ``native_tools``    - the provider's own function-calling API. The model
                         sees every tool result and can chain calls
                         (read -> decide -> write) before answering.
2. ``structured_json`` - for models/providers without native tool calling. The
                         same loop, with tool calls and the
                         "I need the results first" signal carried in a JSON
                         schema (``AgentResponseSchema``).

If native tool calling fails before any action has run, the turn is retried
with ``structured_json``. If the model fails after actions ran, the actions are
reported rather than lost or repeated. Connection/configuration errors
propagate so the caller can fall back to the deterministic engine.

Safety rails that apply to every model:
- Every tool call is validated against its Pydantic parameter schema.
- Errors (bad arguments, unknown tools, failures) go back to the model so it
  can correct itself.
- A state-changing call with identical arguments never runs twice in a turn.
- Each turn gets ``AI_AGENT_MAX_STEPS`` model calls; past that it continues
  only while every step does new, successful work, up to
  ``AI_AGENT_MAX_STEPS_HARD``. Tool output is truncated to fit the context.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.agent.registry import ToolRegistry
from app.agent.schemas import AgentResponseSchema
from app.ai.provider import (
    AIConfigurationError,
    AIConnectionError,
    AIProvider,
    AIProviderError,
    ChatMessage,
    ToolDefinition,
)
from app.ai.structured import compact_schema
from app.core.config import settings
from app.core.logging import get_logger
from app.models.user import User

logger = get_logger("iris.agent.harness")

FINAL_ANSWER_TOOL = "final_answer"


class RecommendedActionArgs(BaseModel):
    task_id: int | None = Field(None, description="ID of the recommended task, if any")
    title: str = Field(..., description="What the user should do next")
    duration_minutes: int | None = Field(None, description="Suggested time to spend")
    decision_type: str | None = Field(None, description="e.g. MUST_DO, SHOULD_DO, REST")
    reason: str | None = Field(None, description="One-line justification")


class FinalAnswerArgs(BaseModel):
    message: str = Field(..., description="Your reply to the user")
    evidence: list[str] = Field(
        default_factory=list, description="Key facts/data points that support the reply"
    )
    recommended_action: RecommendedActionArgs | None = Field(
        None, description="Optional single next action for the user"
    )
    missing_information: str | None = Field(
        None, description="Honest note about missing context or unavailable integrations"
    )


FINAL_ANSWER_DEFINITION = ToolDefinition(
    name=FINAL_ANSWER_TOOL,
    description=(
        "Deliver your final reply to the user. Call this once you have everything you "
        "need; include supporting evidence and, if useful, one recommended next action."
    ),
    parameters=compact_schema(FinalAnswerArgs),
)

_SHARED_RULES = """\
- Ground every claim in the context above, stored memory, or tool results. Never invent tasks, IDs, dates or numbers.
- If you need an ID or fresh data, look it up with a get_/list_/search_ tool first.
- If a tool returns an error, read it, fix the arguments and retry if it makes sense; otherwise explain the problem honestly.
- Only change data when the user asked for it or clearly implied it. Never repeat an action that already succeeded.
- Batch work: to apply one action to several items, use the bulk tool if there is one (e.g. delete_tasks, complete_tasks) or send all the calls together in one response. Never handle one item per reply."""

NATIVE_GUIDE = f"""

HOW TO WORK:
You can call tools to read and change the user's data. Tool results come back to you, so you can chain steps (look something up, then act on it) before replying.
{_SHARED_RULES}
- When you are done, call `{FINAL_ANSWER_TOOL}` with your reply and supporting evidence. A plain-text reply is also accepted."""

STRUCTURED_GUIDE = """

AVAILABLE TOOLS:
{tools}

HOW TO WORK (JSON protocol):
- Put tool calls in "actions" as {{"tool_name": ..., "parameters": {{...}}}}.
- If you need to see tool results before answering (e.g. after a get_/search_ call), set "continue_after_actions": true. You will be called again with the results.
- Otherwise "message" is your final reply to the user and "continue_after_actions" must be false.
{rules}

OUTPUT FORMAT:
Respond strictly conforming to AgentResponseSchema."""

_LAST_STEP_NUDGE = (
    "Stop working now and do not call any more tools. Reply to the user: say plainly what "
    "you completed and what is still left (if anything), and offer to continue. Do not "
    "mention steps, limits or tools."
)


@dataclass
class HarnessResult:
    response: AgentResponseSchema
    actions_executed: list[dict[str, Any]]
    strategy: str
    steps: int


@dataclass
class _RunState:
    actions_executed: list[dict[str, Any]] = field(default_factory=list)
    mutation_keys: set[str] = field(default_factory=set)
    # Calls that already ran this turn; a repeat is not progress.
    seen_calls: set[str] = field(default_factory=set)
    # Count of new, successful tool calls (drives the step budget).
    progress: int = 0
    reasoning: list[str] = field(default_factory=list)
    steps: int = 0


class AgentHarness:
    """Runs one conversational turn against any AIProvider."""

    def __init__(self, registry: ToolRegistry, max_steps: int | None = None) -> None:
        self.registry = registry
        self._max_steps = max_steps

    @property
    def max_steps(self) -> int:
        """Soft budget: model calls allowed per turn when no progress is being made."""
        return max(1, self._max_steps or settings.ai_agent_max_steps)

    @property
    def hard_max_steps(self) -> int:
        """Hard cap, reachable only while every step does new, successful work."""
        return max(self.max_steps, settings.ai_agent_max_steps_hard)

    def _is_final_step(self, step: int, progressed_last_step: bool) -> bool:
        """Past the soft budget, keep going only while the model is making progress."""
        if step == 0:
            return self.hard_max_steps == 1
        if step >= self.hard_max_steps - 1:
            return True
        return step >= self.max_steps - 1 and not progressed_last_step

    async def run(
        self,
        *,
        provider: AIProvider,
        db: Session,
        user: User,
        system_prompt: str,
        history: list[ChatMessage],
        user_message: str,
    ) -> HarnessResult:
        state = _RunState()
        caps = provider.capabilities

        if caps.native_tools and provider.supports_chat:
            try:
                return await self._run_native(
                    provider, db, user, system_prompt, history, user_message, state
                )
            except (AIConnectionError, AIConfigurationError):
                if state.actions_executed:
                    return self._salvage(state, "native_tools")
                raise
            except Exception as exc:
                if state.actions_executed:
                    logger.warning("Native tool loop failed after actions ran: %s", exc)
                    return self._salvage(state, "native_tools")
                logger.warning(
                    "Native tool loop failed (provider=%s model=%s): %s; retrying with structured JSON",
                    provider.name,
                    provider.model,
                    exc,
                )
                state = _RunState()

        try:
            return await self._run_structured(
                provider, db, user, system_prompt, history, user_message, state
            )
        except Exception as exc:
            if state.actions_executed:
                logger.warning("Structured loop failed after actions ran: %s", exc)
                return self._salvage(state, "structured_json")
            raise

    # --- Strategy 1: native tool calling ----------------------------------------

    async def _run_native(
        self,
        provider: AIProvider,
        db: Session,
        user: User,
        system_prompt: str,
        history: list[ChatMessage],
        user_message: str,
        state: _RunState,
    ) -> HarnessResult:
        caps = provider.capabilities
        tools = [*self.registry.list_tool_definitions(), FINAL_ANSWER_DEFINITION]
        messages = [
            ChatMessage(role="system", content=system_prompt + NATIVE_GUIDE),
            *history,
            ChatMessage(role="user", content=user_message),
        ]

        last_content = ""
        progressed = True
        for step in range(self.hard_max_steps):
            last_step = self._is_final_step(step, progressed)
            if last_step and step > 0:
                messages.append(ChatMessage(role="user", content=_LAST_STEP_NUDGE))

            progress_before = state.progress
            result = await provider.chat(messages, tools=None if last_step and step > 0 else tools)
            state.steps += 1
            if result.reasoning:
                state.reasoning.append(result.reasoning)
            last_content = result.content or last_content

            if not result.tool_calls:
                return self._finish(state, "native_tools", message=result.content)

            final_call = next((c for c in result.tool_calls if c.name == FINAL_ANSWER_TOOL), None)
            work_calls = [c for c in result.tool_calls if c.name != FINAL_ANSWER_TOOL]

            if work_calls:
                messages.append(
                    ChatMessage(role="assistant", content=result.content, tool_calls=work_calls)
                )
                for call in work_calls:
                    feedback = await self._execute(
                        db, user, call.name, call.arguments, state, call.argument_error
                    )
                    messages.append(
                        ChatMessage(
                            role="tool",
                            tool_call_id=call.id,
                            content=_truncate(feedback, caps.tool_result_chars),
                        )
                    )

            if final_call is not None:
                try:
                    final = FinalAnswerArgs.model_validate(final_call.arguments)
                except ValidationError as exc:
                    fallback_msg = final_call.arguments.get("message") or result.content
                    if fallback_msg:
                        return self._finish(state, "native_tools", message=str(fallback_msg))
                    messages.append(
                        ChatMessage(
                            role="assistant", content=result.content, tool_calls=[final_call]
                        )
                    )
                    messages.append(
                        ChatMessage(
                            role="tool",
                            tool_call_id=final_call.id,
                            content=f"Invalid {FINAL_ANSWER_TOOL} arguments: {exc}. Try again.",
                        )
                    )
                    continue
                return self._finish(
                    state,
                    "native_tools",
                    message=final.message,
                    evidence=final.evidence,
                    recommended_action=(
                        final.recommended_action.model_dump(exclude_none=True)
                        if final.recommended_action
                        else None
                    ),
                    missing_information=final.missing_information,
                )

            progressed = state.progress > progress_before
            if last_step:
                break

        if last_content:
            return self._finish(state, "native_tools", message=last_content)
        return self._salvage(state, "native_tools")

    # --- Strategy 2: prompted JSON loop -------------------------------------------

    async def _run_structured(
        self,
        provider: AIProvider,
        db: Session,
        user: User,
        system_prompt: str,
        history: list[ChatMessage],
        user_message: str,
        state: _RunState,
    ) -> HarnessResult:
        caps = provider.capabilities
        system = system_prompt + STRUCTURED_GUIDE.format(
            tools=json.dumps(self._compact_tool_specs(), separators=(",", ":")),
            rules=_SHARED_RULES,
        )
        transcript = [f"{m.role}: {m.content}" for m in history if m.content]
        prompt = (
            f"Conversation History:\n{chr(10).join(transcript)}\n\nUser: {user_message}"
            if transcript
            else f"User: {user_message}"
        )

        response: AgentResponseSchema | None = None
        progressed = True
        for step in range(self.hard_max_steps):
            last_step = self._is_final_step(step, progressed)
            step_prompt = f"{prompt}\n\n{_LAST_STEP_NUDGE}" if last_step and step > 0 else prompt
            progress_before = state.progress
            response = await provider.generate_structured(
                system=system, prompt=step_prompt, schema=AgentResponseSchema
            )
            state.steps += 1
            if response.thought:
                state.reasoning.append(response.thought)

            feedback_lines: list[str] = []
            for action in response.actions:
                feedback = await self._execute(db, user, action.tool_name, action.parameters, state)
                feedback_lines.append(
                    f"- {action.tool_name}({json.dumps(action.parameters, default=str)}) -> "
                    f"{_truncate(feedback, caps.tool_result_chars)}"
                )

            progressed = state.progress > progress_before
            wants_more = bool(response.actions) and (
                response.continue_after_actions or not response.message.strip()
            )
            if not wants_more or last_step:
                break

            prompt += (
                f"\n\nTool results (step {step + 1}):\n"
                + "\n".join(feedback_lines)
                + "\n\nContinue using these results. Call further tools only if needed; "
                "otherwise set continue_after_actions to false and give your final message."
            )

        assert response is not None
        final = response.model_copy(
            update={
                "actions": [],
                "continue_after_actions": False,
                "thought": "\n".join(state.reasoning)[-2000:],
                "actions_summary": response.actions_summary
                or [a["summary"] for a in state.actions_executed if a["success"] and a["summary"]],
            }
        )
        if not final.message.strip():
            return self._salvage(state, "structured_json")
        return HarnessResult(
            response=final,
            actions_executed=state.actions_executed,
            strategy="structured_json",
            steps=state.steps,
        )

    # --- Shared helpers ---------------------------------------------------------

    def _compact_tool_specs(self) -> list[dict[str, Any]]:
        specs = []
        for d in self.registry.list_tool_definitions():
            specs.append(
                {
                    "name": d.name,
                    "description": d.description,
                    "parameters": d.parameters.get("properties", {}),
                    "required": d.parameters.get("required", []),
                }
            )
        return specs

    async def _execute(
        self,
        db: Session,
        user: User,
        name: str,
        arguments: dict[str, Any] | None,
        state: _RunState,
        argument_error: str | None = None,
    ) -> str:
        """Run one tool call and return the feedback string for the model."""
        arguments = arguments or {}
        if argument_error:
            return json.dumps({"success": False, "error": argument_error})

        key = f"{name}:{json.dumps(arguments, sort_keys=True, default=str)}"
        mutating = self.registry.is_mutating(name)
        if mutating and key in state.mutation_keys:
            return json.dumps(
                {
                    "success": False,
                    "error": "This exact action already succeeded earlier in this turn; it was not repeated.",
                }
            )

        res = await self.registry.execute(name=name, db=db, user=user, parameters=arguments)
        record = {
            "tool_name": res.tool_name,
            "success": res.success,
            "summary": res.summary,
            "error": res.error,
            "data": res.data,
        }
        state.actions_executed.append(record)
        if res.success and key not in state.seen_calls:
            state.progress += 1
        state.seen_calls.add(key)
        if res.success and mutating:
            state.mutation_keys.add(key)
        return json.dumps(
            {"success": res.success, "summary": res.summary, "error": res.error, "data": res.data},
            default=str,
        )

    def _finish(
        self,
        state: _RunState,
        strategy: str,
        *,
        message: str,
        evidence: list[str] | None = None,
        recommended_action: dict[str, Any] | None = None,
        missing_information: str | None = None,
    ) -> HarnessResult:
        if not (message or "").strip():
            return self._salvage(state, strategy)
        response = AgentResponseSchema(
            thought="\n".join(state.reasoning)[-2000:],
            actions=[],
            message=message.strip(),
            actions_summary=[
                a["summary"] for a in state.actions_executed if a["success"] and a["summary"]
            ],
            evidence=evidence or [],
            recommended_action=recommended_action,
            missing_information=missing_information,
        )
        return HarnessResult(
            response=response,
            actions_executed=state.actions_executed,
            strategy=strategy,
            steps=state.steps,
        )

    def _salvage(self, state: _RunState, strategy: str) -> HarnessResult:
        """Build a truthful reply when the model stopped before answering."""
        done = [a for a in state.actions_executed if a["success"]]
        failed = [a for a in state.actions_executed if not a["success"]]
        if not state.actions_executed:
            raise AIProviderError("Model produced no usable reply")
        parts = []
        if done:
            parts.append("Done: " + "; ".join(a["summary"] or a["tool_name"] for a in done) + ".")
        if failed:
            parts.append(
                "Could not complete: "
                + "; ".join(f"{a['tool_name']} ({a['error']})" for a in failed)
                + "."
            )
        response = AgentResponseSchema(
            thought="\n".join(state.reasoning)[-2000:],
            actions=[],
            message=" ".join(parts),
            actions_summary=[a["summary"] for a in done if a["summary"]],
            evidence=[],
            missing_information="The AI model stopped before writing a full reply.",
        )
        return HarnessResult(
            response=response,
            actions_executed=state.actions_executed,
            strategy=strategy,
            steps=state.steps,
        )


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated {len(text) - limit} chars]"
