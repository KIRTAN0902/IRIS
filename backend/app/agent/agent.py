"""Core Conversational Agent Loop for IRIS."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.agent.harness import AgentHarness
from app.agent.registry import ToolRegistry, default_registry
from app.agent.schemas import AgentResponseSchema, ChatMessageOut
from app.core.errors import NotFoundError
from app.ai.factory import get_ai_provider
from app.ai.provider import ChatMessage
from app.intelligence.context import build_decision_context
from app.intelligence.decision_engine import deterministic_decision
from app.intelligence.personal_model import build_personal_model, render_personal_model
from app.intelligence.situation import (
    build_situation,
    detail_for_context_window,
    last_user_message_at,
    render_situation,
)
from app.models.ai_conversation import AIConversation, AIMessage
from app.models.ai_memory import AIMemory
from app.models.enums import AIRole
from app.models.user import User
from app.services import conversation_memory
from app.services.memory_service import memory_service

# Appended to the system prompt when the user is talking, not typing.
_VOICE_MODE = """

# VOICE CONVERSATION
The user is speaking to you and will HEAR your reply through text-to-speech.
- Answer in 1-3 short, natural spoken sentences. No markdown, lists, tables, emoji or links.
- Reply in the language mix the user spoke (English, Hindi, Gujarati, or a mix such as Hinglish).
- Say dates and times the way people say them aloud, e.g. "Monday at 6 pm".
- Still use your tools to do the work; only the spoken summary is short.
- The transcript may contain recognition mistakes. If a name, date or number looks wrong, ask briefly."""


class IrisAgent:
    """Conversational personal assistant & action layer for IRIS."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or default_registry
        self.harness = AgentHarness(self.registry)

    async def run_turn(
        self,
        db: Session,
        user: User,
        user_message: str,
        conversation_id: int | None = None,
        voice: bool = False,
        defer_memory: bool = False,
    ) -> tuple[ChatMessageOut, AIConversation]:
        """Execute a single conversational turn with IRIS.

        ``defer_memory`` skips memory extraction (a slow, separate model call) so the
        reply returns sooner; the client then calls :meth:`remember_turn`.
        """
        # 1. Resolve or create conversation
        conversation = self._resolve_conversation(db, user, conversation_id, user_message)

        # 2. Build focused personal context
        context = build_decision_context(db, user)
        context["user_name"] = user.name.split(" ")[0] if user.name else None
        since = last_user_message_at(db, user.id)

        # 3. Retrieve relevant long-term memories for this turn
        relevant_memories = memory_service.search_relevant_memories(
            db=db,
            user_id=user.id,
            query=user_message,
            limit=8,
            mark_accessed=True,
        )

        # 4. Generate the reply through the model-agnostic harness, or fall back
        provider = get_ai_provider()
        response_schema: AgentResponseSchema | None = None
        actions_executed: list[dict[str, Any]] = []
        source = "DETERMINISTIC"
        harness_meta: dict[str, Any] = {}

        if provider.enabled:
            try:
                caps = provider.capabilities
                history = self._history_messages(conversation, caps.history_messages)
                detail = detail_for_context_window(caps.context_window)
                personal_model = build_personal_model(db, user)
                profile_ids = {m["id"] for m in personal_model["stated"]}
                situation = build_situation(db, user, context, since=since)
                recent = conversation_memory.recent_conversations(
                    db, user.id, user.timezone,
                    exclude_id=conversation.id,
                    limit={"compact": 3, "standard": 5, "full": 8}[detail],
                )
                related = conversation_memory.search_conversations(
                    db, user.id, user.timezone, user_message,
                    exclude_id=conversation.id,
                    exclude_ids={r["conversation_id"] for r in recent},
                    limit=3,
                )
                result = await self.harness.run(
                    provider=provider,
                    db=db,
                    user=user,
                    system_prompt=self._build_system_prompt(
                        context,
                        # Profile memories are already in the personal model.
                        [m for m in relevant_memories if m.id not in profile_ids],
                        personal_model=render_personal_model(personal_model, detail),
                        situation=render_situation(situation, detail),
                        shared=conversation_memory.render_conversations(recent, related),
                    )
                    + (_VOICE_MODE if voice else ""),
                    history=history,
                    user_message=user_message,
                )
                response_schema = result.response
                actions_executed = result.actions_executed
                source = "AI"
                harness_meta = {
                    "provider": provider.name,
                    "model": provider.model,
                    "strategy": result.strategy,
                    "steps": result.steps,
                }
            except Exception as exc:
                from app.ai.health import ai_health

                ai_health.record_failure(provider.name, provider.model, exc)
                response_schema = None

        # 5. Deterministic fallback if AI is unavailable or failed
        if response_schema is None:
            response_schema = self._deterministic_fallback(db, user, context, user_message)
            source = "DETERMINISTIC"
            if not response_schema.missing_information:
                response_schema.missing_information = "AI provider offline. Local deterministic intelligence engine active."
            for action in response_schema.actions:
                res = await self.registry.execute(
                    name=action.tool_name, db=db, user=user, parameters=action.parameters
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

        state_mutated = any(
            a["success"] and self.registry.is_mutating(a["tool_name"]) for a in actions_executed
        )

        # 6. Post-action recalculation for mixed requests (e.g. "I finished my task. What next?")
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

        # 7. Extract and persist contextual memory from this conversational turn
        memories_meta: list[dict[str, Any]] = []
        if not defer_memory:
            memories_meta = await self._extract_memories(
                db, user, user_message, response_schema.message, conversation.id
            )

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
                "memories_updated": memories_meta,
                "memory_pending": defer_memory,
                "harness": harness_meta,
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
            memories_updated=memories_meta,
            created_at=assistant_msg_row.created_at,
        )
        return out, conversation

    async def remember_turn(self, db: Session, user: User, message_id: int) -> list[dict[str, Any]]:
        """Run the deferred memory extraction for an assistant reply (idempotent)."""
        reply = (
            db.query(AIMessage)
            .join(AIConversation, AIConversation.id == AIMessage.conversation_id)
            .filter(AIMessage.id == message_id, AIConversation.user_id == user.id)
            .filter(AIMessage.role == AIRole.ASSISTANT.value)
            .first()
        )
        if reply is None:
            raise NotFoundError("Message not found.")
        meta = dict(reply.metadata_json or {})
        if not meta.get("memory_pending"):
            return meta.get("memories_updated") or []

        asked = (
            db.query(AIMessage)
            .filter(
                AIMessage.conversation_id == reply.conversation_id,
                AIMessage.role == AIRole.USER.value,
                AIMessage.id < reply.id,
            )
            .order_by(AIMessage.id.desc())
            .first()
        )
        memories = await self._extract_memories(
            db, user, asked.content if asked else "", reply.content, reply.conversation_id
        )
        reply.metadata_json = {**meta, "memories_updated": memories, "memory_pending": False}
        db.commit()
        return memories

    async def _extract_memories(
        self, db: Session, user: User, user_message: str, assistant_message: str, conversation_id: int
    ) -> list[dict[str, Any]]:
        extracted = await memory_service.extract_and_store_from_conversation(
            db=db,
            user=user,
            user_message=user_message,
            assistant_message=assistant_message,
            conversation_id=conversation_id,
        )
        return [
            {"id": m.id, "category": m.category, "key": m.key, "content": m.content, "importance": m.importance}
            for m in extracted
        ]

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

    def _build_system_prompt(
        self,
        context: dict[str, Any],
        memories: list[AIMemory] | None = None,
        *,
        personal_model: str = "",
        situation: str = "",
        shared: str = "",
    ) -> str:
        memory_section = memory_service.format_memories_for_prompt(memories or [])
        bottlenecks = (context.get("startup_state", {}) or {}).get("bottlenecks") or []
        attention = [a["title"] for a in context.get("attention_items", [])[:4]]
        unavailable = ", ".join(context.get("unavailable_domains", []) or []) or "none"

        sections = [
            f"""You are IRIS, {context.get("user_name") or "the user"}'s personal intelligence assistant, in the spirit of JARVIS: always aware of their situation, deeply familiar with how they live and work, and one step ahead.

HOW YOU OPERATE:
1. GROUNDED: Everything below is live data and real memory. Never invent tasks, IDs, times or facts; use tools to look up anything not shown.
2. AWARE: Know what is pending, what matters most, what is already done and what is next. Do not ask the user for information that is already in your context.
3. PERSONAL: Tailor every suggestion to their routine, work style, peak hours, focus length and estimation habits (e.g. pad estimates if they usually run long, put deep work in their peak window). Honour every stated preference, constraint and instruction.
4. ANTICIPATE: If something important needs attention (overdue work, a deadline today, a clash with the next commitment, working past sleep time, a goal falling behind), say so briefly even if not asked.
5. ACT: When the user asks to change something or to remember something, use the tools. When they share a lasting fact about their routine, work style, preferences or people, save it with save_memory.
6. ONE MEMORY: Every conversation with the user shares the same memory. What was discussed in other conversations (below) is something you already know; connect it naturally (e.g. relate internship plans to startup decisions). Never say you cannot see other conversations; use search_conversations / get_conversation for details.
7. HONEST: Not connected yet: {unavailable}. Say so instead of guessing.
8. CONCISE: Talk like a sharp chief of staff: direct, specific, no filler. Lead with the answer.""",
        ]
        if personal_model:
            sections.append(personal_model)
        if situation:
            sections.append(situation)
        if shared:
            sections.append(shared)
        if bottlenecks or attention:
            extra = ["SIGNALS:"]
            if bottlenecks:
                extra.append(f"- Bottlenecks: {json.dumps(bottlenecks)[:400]}")
            if attention:
                extra.append(f"- Needs attention: {json.dumps(attention)}")
            sections.append("\n".join(extra))
        if memory_section:
            sections.append(memory_section)
        return "\n\n".join(sections)

    @staticmethod
    def _history_messages(conversation: AIConversation, limit: int) -> list[ChatMessage]:
        rows = conversation.messages[-limit:] if conversation.messages and limit > 0 else []
        roles = {AIRole.USER.value: "user", AIRole.ASSISTANT.value: "assistant"}
        return [
            ChatMessage(role=roles[m.role], content=m.content)
            for m in rows
            if m.role in roles and m.content
        ]

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

        # Check for explicit memory or recall queries
        mem_queries = [
            "what do you remember",
            "what do you know about me",
            "my preferences",
            "do you remember",
            "what did i say",
            "recall my",
            "stored memory",
            "my memories",
        ]
        if any(mq in msg_lower for mq in mem_queries):
            recalled = memory_service.search_relevant_memories(db, user.id, user_message, limit=6)
            if recalled:
                bullets = "\n".join(f"- [{m.category}] {m.content}" for m in recalled)
                return AgentResponseSchema(
                    thought="User asked about memories/context; returning recalled items.",
                    actions=[],
                    message=f"Here is what I currently remember from our conversations:\n{bullets}",
                    actions_summary=[],
                    evidence=[f"Recalled {len(recalled)} memories"],
                )
            else:
                return AgentResponseSchema(
                    thought="User asked about memories, but none are stored yet.",
                    actions=[],
                    message="I don't have any specific memories stored yet. Tell me about your preferences, routine, or projects and I will remember them across all our conversations.",
                    actions_summary=[],
                    evidence=["Memory store is currently empty"],
                )

        # Check for explicit 'remember that' / 'note that'
        if msg_lower.startswith("remember that") or msg_lower.startswith("keep in mind that") or msg_lower.startswith("note that"):
            extracted = memory_service._heuristic_extract(user_message)
            if extracted:
                saved = [
                    memory_service.store_memory(
                        db,
                        user,
                        item["content"],
                        category=item["category"],
                        key=item.get("key"),
                        importance=item.get("importance", 0.8),
                        source="CONVERSATION_EXTRACTED",
                    )
                    for item in extracted
                ]
                content_preview = "; ".join(f"'{m.content}'" for m in saved)
                return AgentResponseSchema(
                    thought="User explicitly commanded IRIS to remember context in offline mode.",
                    actions=[],
                    message=f"Understood. I have committed this to memory: {content_preview}. I will keep this in mind across all our conversations.",
                    actions_summary=["Saved context to memory"],
                    evidence=[f"Stored memory #{m.id}" for m in saved],
                )

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
