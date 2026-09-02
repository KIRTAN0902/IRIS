"""Core Conversational Agent Loop for IRIS."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.agent.registry import ToolRegistry, default_registry
from app.agent.schemas import AgentResponseSchema, ChatMessageOut
from app.ai.factory import get_ai_provider
from app.intelligence.context import build_decision_context
from app.intelligence.decision_engine import deterministic_decision
from app.models.ai_conversation import AIConversation, AIMessage
from app.models.enums import AIRole
from app.models.user import User


class IrisAgent:
    """Conversational personal assistant & action layer for IRIS."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or default_registry

    async def run_turn(
        self,
        db: Session,
        user: User,
        user_message: str,
        conversation_id: int | None = None,
    ) -> tuple[ChatMessageOut, AIConversation]:
        """Execute a single conversational turn with IRIS."""
        # 1. Resolve or create conversation
        conversation = self._resolve_conversation(db, user, conversation_id, user_message)

        # 2. Build focused personal context
        context = build_decision_context(db, user)

        # 3. Fetch recent conversation history
        history_messages = conversation.messages[-6:] if conversation.messages else []

        # 4. Generate response via AIProvider or fallback
        provider = get_ai_provider()
        response_schema: AgentResponseSchema | None = None
        source = "DETERMINISTIC"

        if provider.enabled:
            try:
                system_prompt = self._build_system_prompt(context)
                turn_prompt = self._build_turn_prompt(history_messages, user_message)
                response_schema = await provider.generate_structured(
                    system=system_prompt,
                    prompt=turn_prompt,
                    schema=AgentResponseSchema,
                )
                source = "AI"
            except Exception:
                response_schema = None

        # 5. Deterministic fallback if AI is unavailable or failed
        if response_schema is None:
            response_schema = self._deterministic_fallback(db, user, context, user_message)
            source = "DETERMINISTIC"

        # 6. Execute tools requested by the agent
        actions_executed: list[dict[str, Any]] = []
        state_mutated = False

        for action in response_schema.actions:
            res = await self.registry.execute(
                name=action.tool_name,
                db=db,
                user=user,
                parameters=action.parameters,
            )
            actions_executed.append(
                {
                    "tool_name": res.tool_name,
                    "success": res.success,
                    "summary": res.summary,
                    "error": res.error,
                    "data": res.data,
                }
            )
            if res.success and action.tool_name in {
                "create_task",
                "update_task",
                "complete_task",
                "delete_task",
                "create_time_block",
                "update_time_block",
                "delete_time_block",
                "create_goal",
                "update_goal",
                "create_recurring_schedule",
                "update_recurring_schedule",
                "record_decision_feedback",
                "log_outreach",
            }:
                state_mutated = True

        # 7. Post-action recalculation for mixed requests (e.g. "I finished my task. What next?")
        recommended_action = response_schema.recommended_action
        if state_mutated:
            # Refresh decision context and recommendation
            new_rec = deterministic_decision(db, user)
            if not recommended_action and new_rec:
                recommended_action = {
                    "task_id": new_rec.task_id,
                    "title": new_rec.title,
                    "duration_minutes": new_rec.duration_minutes,
                    "decision_type": new_rec.decision_type,
                    "reason": new_rec.reason,
                }

        # 8. Persist conversation turn
        user_msg_row = AIMessage(
            conversation_id=conversation.id,
            role=AIRole.USER.value,
            content=user_message,
        )
        db.add(user_msg_row)

        assistant_msg_row = AIMessage(
            conversation_id=conversation.id,
            role=AIRole.ASSISTANT.value,
            content=response_schema.message,
            metadata_json={
                "actions_taken": actions_executed,
                "evidence": response_schema.evidence,
                "recommended_action": recommended_action,
                "source": source,
            },
        )
        db.add(assistant_msg_row)
        db.commit()
        db.refresh(assistant_msg_row)
        db.refresh(conversation)

        # 9. Return formatted ChatMessageOut
        out = ChatMessageOut(
            id=assistant_msg_row.id,
            conversation_id=conversation.id,
            role=assistant_msg_row.role,
            content=assistant_msg_row.content,
            actions_taken=actions_executed,
            evidence=response_schema.evidence,
            recommended_action=recommended_action,
            source=source,
            created_at=assistant_msg_row.created_at,
        )
        return out, conversation

    def _resolve_conversation(
        self,
        db: Session,
        user: User,
        conversation_id: int | None,
        first_message: str,
    ) -> AIConversation:
        if conversation_id:
            conv = (
                db.query(AIConversation)
                .filter(AIConversation.id == conversation_id, AIConversation.user_id == user.id)
                .first()
            )
            if conv:
                return conv

        conv = AIConversation(
            user_id=user.id,
            title=first_message[:80] if first_message else "New conversation",
        )
        db.add(conv)
        db.flush()
        return conv

    def _build_system_prompt(self, context: dict[str, Any]) -> str:
        tool_specs = self.registry.list_specs()
        cur_win = context.get("current_window", {})
        win_block = cur_win.get("active_block_name") or "None"
        win_rem = cur_win.get("minutes_remaining_in_block") or 0
        nxt_name = cur_win.get("next_hard_constraint_name") or "None"
        nxt_rem = cur_win.get("minutes_until_next_hard_constraint") or 0

        fixed_comm = json.dumps(context.get("fixed_constraints", {}).get("fixed_commitments", []))

        return f"""You are IRIS, a personal decision intelligence assistant.

CORE IDENTITY & PRINCIPLES:
1. You are grounded in real structured context. Never fabricate tasks.
2. HONEST LIMITATIONS: External tools (Gmail, Drive) are offline.
3. NO INVENTED WORK: If all work is completed, suggest rest or planning.
4. CONTROLLED ACTIONS: When asked to change state, emit tool calls in 'actions'.
5. EXPLAIN WITH EVIDENCE: Back recommendations with observed facts.
6. KEEP MESSAGES CLEAR & CONCISE: Speak with precision.

CURRENT PERSONAL CONTEXT:
- Local Time: {context.get("current_local_time")}
- Flexible Minutes: {context.get("available_minutes", 0)}m
- Window: Active '{win_block}' ({win_rem}m), Next '{nxt_name}' ({nxt_rem}m)
- Flexible Windows: {json.dumps(context.get("flexible_windows", []))}
- Fixed Commitments: {fixed_comm}
- Urgent Obligations: {json.dumps(context.get("urgent_obligations", []))}
- Goals: {json.dumps([g["name"] for g in context.get("goals", {}).get("goals", [])[:5]])}
- Bottleneck: {json.dumps(context.get("startup_state", {}).get("bottleneck"))}
- Attention: {json.dumps([a["title"] for a in context.get("attention_items", [])[:4]])}

AVAILABLE TOOLS:
{json.dumps(tool_specs, indent=2)}

OUTPUT FORMAT:
Respond strictly conforming to AgentResponseSchema."""

    def _build_turn_prompt(self, history: list[AIMessage], user_message: str) -> str:
        transcript_lines = []
        for m in history:
            transcript_lines.append(f"{m.role}: {m.content}")

        transcript_str = "\n".join(transcript_lines)
        if transcript_str:
            return f"Conversation History:\n{transcript_str}\n\nUser: {user_message}"
        return f"User: {user_message}"

    def _deterministic_fallback(
        self,
        db: Session,
        user: User,
        context: dict[str, Any],
        user_message: str,
    ) -> AgentResponseSchema:
        """Deterministic rule-based response when AI provider is unavailable."""
        msg_lower = user_message.lower()
        evidence: list[str] = []

        # Check for Gmail / Email query
        if "email" in msg_lower or "gmail" in msg_lower or "inbox" in msg_lower:
            return AgentResponseSchema(
                thought="User inquired about emails; Gmail is not connected.",
                actions=[],
                message=(
                    "I can't check your emails right now because Gmail integration "
                    "is not connected."
                ),
                actions_summary=[],
                evidence=["Gmail integration: Not connected"],
                missing_information="Gmail integration is planned and not yet active.",
            )

        # Check for completed task signal
        if "finished" in msg_lower or "completed" in msg_lower or "done with" in msg_lower:
            ranked = context.get("ranked_tasks", [])
            evidence.append("User indicated completion of previous task")
            if ranked:
                top = ranked[0]["task"]
                est = top.get("estimated_duration") or 45
                return AgentResponseSchema(
                    thought="User finished a task; recommending top ranked next action.",
                    actions=[],
                    message=(
                        f"Logged that you finished your task. Based on your current availability, "
                        f"your top priority now is '{top['title']}' ({est}m)."
                    ),
                    actions_summary=["State updated"],
                    evidence=[f"Top priority task: #{top['id']} ({top['area']})"],
                    recommended_action={
                        "task_id": top["id"],
                        "title": top["title"],
                        "duration_minutes": est,
                    },
                )

        # Check for "what should i do" or "what's important"
        rec = deterministic_decision(db, user)
        evidence = rec.evidence or []
        if rec.opportunity_cost:
            evidence.append(f"Trade-off: {rec.opportunity_cost}")

        avail_m = context.get("available_minutes", 0)
        return AgentResponseSchema(
            thought="Standard deterministic recommendation query.",
            actions=[],
            message=(
                f"Based on your current {avail_m}m flexible window, I recommend focusing on: "
                f"'{rec.title}'. {rec.reason}"
            ),
            actions_summary=[],
            evidence=evidence[:3],
            recommended_action={
                "task_id": rec.task_id,
                "title": rec.title,
                "duration_minutes": rec.duration_minutes,
                "decision_type": rec.decision_type,
            },
        )


# Global agent instance
default_agent = IrisAgent()
