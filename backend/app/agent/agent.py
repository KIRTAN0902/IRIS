"""Core Conversational Agent Loop for IRIS."""

from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.agent.harness import AgentHarness
from app.agent.registry import ToolRegistry, default_registry
from app.agent.schemas import AgentResponseSchema, ChatMessageOut
from app.agent.supervisor import get_iris_supervisor
from app.ai.deadline import get_current_deadline, reset_deadline, set_deadline
from app.ai.factory import get_ai_provider
from app.ai.provider import ChatMessage, fast_turn
from app.ai.providers.mock import MockProvider
from app.core.config import settings
from app.core.errors import NotFoundError
from app.core.logging import get_logger
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

logger = get_logger("iris.agent")

# Short-lived per-user cache for heavy decision/personal/situation snapshots
# when connected to a remote database (PostgreSQL/Supabase), avoiding ~40
# redundant cross-region SQL queries on back-to-back chat turns.
_USER_CONTEXT_CACHE: dict[int, tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]]] = {}
_CONTEXT_CACHE_TTL_SECONDS = 60.0


def invalidate_user_context_cache(user_id: int | None = None) -> None:
    """Invalidate cached decision/personal/situation context for a user (or all users)."""
    if user_id is None:
        _USER_CONTEXT_CACHE.clear()
    else:
        _USER_CONTEXT_CACHE.pop(user_id, None)

# Appended to the system prompt when the user is talking, not typing.
_VOICE_MODE = """

# VOICE CONVERSATION
The user is speaking to you and will HEAR your reply through text-to-speech.
- Answer in 1-3 short, natural spoken sentences. No markdown, lists, tables, emoji or links.
- Reply in the language of the user's latest message: English gets plain English; switch to Hindi,
  Gujarati or a mix such as Hinglish only when that message itself used it.
- Say dates and times the way people say them aloud, e.g. "Monday at 6 pm".
- Still use your tools to do the work; only the spoken summary is short.
- The transcript may contain recognition mistakes. If a name, date or number looks wrong, ask briefly."""


class IrisAgent:
    """Conversational personal assistant & action layer for IRIS."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        if registry is not None:
            self.registry = registry
        elif settings.ai_multi_agent_enabled:
            from app.agent.registry import orchestrator_registry
            self.registry = orchestrator_registry
        else:
            self.registry = default_registry
        self.harness = AgentHarness(self.registry)
        self.supervisor = get_iris_supervisor()

    async def run_turn(
        self,
        db: Session,
        user: User,
        user_message: str,
        conversation_id: int | None = None,
        voice: bool = False,
        defer_memory: bool = False,
        *,
        skip_fast_path: bool = False,
        skip_memory: bool = False,
        persisted_user_message: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> tuple[ChatMessageOut, AIConversation]:
        """Execute a single conversational turn with IRIS.

        ``defer_memory`` skips memory extraction (a slow, separate model call) so the
        reply returns sooner; the client then calls :meth:`remember_turn`.
        ``skip_memory`` skips extraction entirely (used by vision turns, whose
        durable context was already stored separately).

        Vision turns use ``skip_fast_path`` so the enriched visual telemetry is
        interpreted by an agent, and ``persisted_user_message`` so only the
        original prompt + a lightweight badge reaches conversation history.
        """
        stored_user_message = persisted_user_message or user_message
        # 1. Resolve or create conversation
        conversation = self._resolve_conversation(db, user, conversation_id, stored_user_message)

        is_remote_db = False
        try:
            is_remote_db = db.get_bind().dialect.name != "sqlite"
        except Exception:
            is_remote_db = False

        context: dict[str, Any] | None = None
        personal_model: dict[str, Any] | None = None
        situation: dict[str, Any] | None = None

        def _ensure_context() -> dict[str, Any]:
            nonlocal context, personal_model, situation
            if context is not None:
                return context
            if is_remote_db:
                cached = _USER_CONTEXT_CACHE.get(user.id)
                if cached and (time.monotonic() - cached[0]) < _CONTEXT_CACHE_TTL_SECONDS:
                    context, personal_model, situation = cached[1], cached[2], cached[3]
                    return context
            context = build_decision_context(db, user)
            context["user_name"] = user.name.split(" ")[0] if user.name else None
            return context

        # Fast deterministic path (e.g. "what's my task?", "task done", "gym done")
        if skip_fast_path:
            fast_resp, fast_actions = None, []
        else:
            fast_resp, fast_actions = self.supervisor.try_fast_path(
                db, user, {}, user_message
            )
        is_fast_path = bool(fast_resp is not None or getattr(fast_resp, "fast_path", False))
        if fast_resp is not None:
            response_schema = fast_resp
            actions_executed = fast_actions
            source = "DETERMINISTIC"
            harness_meta = {"strategy": "fast_path", "source": "supervisor", "fast_path": True}
            relevant_memories = []
            if fast_actions:
                invalidate_user_context_cache(user.id)
        else:
            since = last_user_message_at(db, user.id)
            # 3. Retrieve relevant long-term memories for this turn
            relevant_memories = memory_service.search_relevant_memories(
                db=db,
                user_id=user.id,
                query=user_message,
                limit=8,
                mark_accessed=True,
                commit=False,
            )

            # 4. Generate the reply through sub-agents, AI harness, or fall back
            provider = get_ai_provider()
            response_schema: AgentResponseSchema | None = None
            actions_executed: list[dict[str, Any]] = []
            source = "DETERMINISTIC"
            harness_meta: dict[str, Any] = {}

            # Voice turns trade the model's thinking phase for a faster answer.
            fast_token = fast_turn.set(voice)
            dl_token = None
            if get_current_deadline() is None:
                turn_timeout = getattr(provider, "_timeout", None) or settings.gemini_timeout_seconds or 45.0
                dl_token = set_deadline(turn_timeout)

            try:
                if provider.enabled:
                    # Check specialized sub-agent delegation (instant deterministic routing)
                    routed_domains = (
                        self.supervisor.route_intent(user_message)
                        if (not isinstance(provider, MockProvider) and settings.ai_multi_agent_enabled)
                        else []
                    )
                    if not routed_domains and not isinstance(provider, MockProvider) and settings.ai_multi_agent_enabled:
                        try:
                            routed_domains = await self.supervisor.route_intent_async(user_message)
                        except Exception as router_exc:
                            logger.debug("Async intent router skipped: %s", router_exc)
                            routed_domains = []

                    if routed_domains:
                        try:
                            reports = []
                            for dom in routed_domains:
                                rep = await self.supervisor.dispatch_to_subagent(
                                    domain=dom,
                                    db=db,
                                    user=user,
                                    instruction=user_message,
                                    context=context,
                                )
                                reports.append(rep)
                            if any(r.success for r in reports):
                                response_schema, actions_executed = self.supervisor.synthesize_reports(
                                    reports, user_message
                                )
                                source = "SUB_AGENT"
                                harness_meta = {
                                    "strategy": "multi_agent_delegation",
                                    "domains": routed_domains,
                                    "agents": [r.agent_name for r in reports],
                                }
                            else:
                                logger.warning(
                                    "Sub-agent delegation returned no successful reports; falling back to orchestrator harness"
                                )
                                response_schema = None
                        except Exception as exc:
                            logger.warning("Sub-agent delegation error: %s; falling back to orchestrator harness", exc)
                            response_schema = None

                    if response_schema is None:
                        try:
                            ctx = _ensure_context()
                            caps = provider.capabilities
                            history = self._history_messages(conversation, caps.history_messages)
                            detail = detail_for_context_window(caps.context_window)
                            if personal_model is None:
                                personal_model = build_personal_model(db, user)
                            profile_ids = {m["id"] for m in personal_model["stated"]}
                            if situation is None:
                                situation = build_situation(db, user, ctx, since=since)
                            if is_remote_db:
                                _USER_CONTEXT_CACHE[user.id] = (
                                    time.monotonic(),
                                    ctx,
                                    personal_model,
                                    situation,
                                )
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
                                    ctx,
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
                            actual_provider = provider.name
                            actual_model = provider.model
                            try:
                                from app.ai.providers.gemini import active_turn_backend
                                used_backend = active_turn_backend.get()
                                if used_backend is not None:
                                    actual_provider = used_backend.name
                                    actual_model = used_backend.model
                            except ImportError:
                                pass
                            harness_meta = {
                                "provider": actual_provider,
                                "model": actual_model,
                                "strategy": result.strategy,
                                "steps": result.steps,
                            }
                        except Exception as exc:
                            from app.ai.health import ai_health

                            logger.error(
                                "AI turn execution failed (provider=%s model=%s): %s",
                                provider.name,
                                provider.model,
                                exc,
                                exc_info=True,
                            )
                            ai_health.record_failure(provider.name, provider.model, exc)
                            response_schema = None
            finally:
                fast_turn.reset(fast_token)
                if dl_token is not None:
                    reset_deadline(dl_token)

        # 5. Deterministic fallback if AI is unavailable or failed
        if response_schema is None:
            ctx = _ensure_context()
            response_schema = self._deterministic_fallback(db, user, ctx, user_message)
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
            invalidate_user_context_cache(user.id)
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
        if not defer_memory and not skip_memory and not is_fast_path:
            memories_meta = await self._extract_memories(
                db, user, user_message, response_schema.message, conversation.id
            )

        # 8. Persist conversation turn
        user_msg_row = AIMessage(
            conversation_id=conversation.id,
            role=AIRole.USER.value,
            content=stored_user_message,
        )
        db.add(user_msg_row)

        extra = dict(extra_metadata or {})
        assistant_msg_row = AIMessage(
            conversation_id=conversation.id,
            role=AIRole.ASSISTANT.value,
            content=response_schema.message,
            metadata_json={
                **extra,
                "actions_taken": actions_executed,
                "evidence": response_schema.evidence,
                "recommended_action": recommended_action,
                "source": source,
                "memories_updated": memories_meta,
                "memory_pending": False if (is_fast_path or skip_memory) else defer_memory,
                "harness": harness_meta,
                "fast_path": is_fast_path,
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
            fast_path=is_fast_path,
            visual_context=extra.get("visual_context"),
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
        if meta.get("fast_path") or not meta.get("memory_pending"):
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
        email_accounts = context.get("connected_email_accounts") or []
        if email_accounts:
            email_summary = ", ".join(f"{a['email_address']} ({a['alias']})" for a in email_accounts)
        else:
            email_summary = "None (run `python scripts/connect_gmail.py` to link Gmail)"

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
9. FULL LAPTOP ACCESS & CONTROL (TERMINAL & FILESYSTEM): You have unrestricted, full access to the user's entire Windows laptop workstation:
   - Your host Windows laptop workstation is ONLINE, ACTIVE, and FULLY ACCESSIBLE.
   - When asked if you can access the laptop, terminal, files, or directories, ALWAYS CONFIRM YES! You have full access across all drives (C:\\, D:\\, etc.), user folders (Desktop, Downloads, Documents), and project directories.
   - Terminal Execution: Run ANY PowerShell/CLI command, script, git operation, build tool, or system command using `run_laptop_terminal_command`. Specify `working_dir` if needed (e.g. 'Desktop', 'Downloads', 'C:\\kirtan\\IRIS', 'C:\\').
   - Browse & List Directories: Browse any directory or drive across the laptop using `list_laptop_files` (e.g. `directory="Desktop"`, `directory="Downloads"`, or `directory="C:\\"`).
   - Read Files: Read code, documents, text files, or configuration files anywhere using `read_laptop_file`.
   - Write & Create Files: Create new files, write scripts, save notes, or append to files anywhere across the laptop using `write_laptop_file`.
   - Search Files: Recursively search for files across drives or folders matching any pattern (*.pdf, *.py, *.txt) using `search_laptop_files`.
   - App & CLI Display: Launch applications or interactive terminals on the physical laptop screen using `launch_laptop_app`:
     * Antigravity CLI: When user asks for Antigravity CLI, agy, or to open terminal with antigravity:
       Call `launch_laptop_app(app="antigravity_cli", directory="...", prompt="...", resume=True/False)`.
       - It opens an interactive terminal in the requested directory and runs `agy`.
       - If the user asks to resume or continue a conversation: pass `resume=True`.
       - If the user provides a prompt or instructions: pass `prompt="..."`.
     * Antigravity IDE: When user asks for Antigravity IDE, the desktop GUI application, or code editor:
       Call `launch_laptop_app(app="antigravity_ide", directory="...")`.
     * Terminal: Use `launch_laptop_app(app="terminal", directory="...")` for a general interactive terminal.
     * VS Code: Use `launch_laptop_app(app="vscode", directory="...")`.
   Whenever the user asks to inspect, run, modify, or search anything on their laptop, act immediately using these tools!
10. GOOGLE DRIVE INTEGRATION: You have tools to search, read, and upload files to Google Drive:
   - To view or search files in Google Drive, call `list_google_drive_files` or `search_google_drive`.
   - To retrieve and read the text of a document or Google Doc, call `read_google_drive_file`.
   - To upload notes, briefings, project plans, or laptop files to Google Drive (and NotebookLM sources), call `upload_to_google_drive`.
11. GMAIL & EMAIL INTEGRATION:
   - Connected email inboxes: {email_summary}.
   - You have tools to check, search, and draft emails:
     * `list_unread_emails`: Check unread emails across accounts or for a specific alias.
     * `search_emails`: Search messages using Gmail search syntax (`from:`, `subject:`, `is:unread`, etc.).
     * `get_email_details`: Fetch full body text and headers for an email message.
     * `create_email_draft`: Create a draft email in Gmail for the user to review and approve before sending.
     * `send_email`: Send an email directly (only when explicitly asked by user).
   - If user asks to check emails or about their inbox, NEVER say Gmail is not connected when active inboxes are listed above! Use the tools to retrieve their emails immediately.
12. DIARY & NOTES NOTEBOOK:
   - You have a full Diary / Notes notebook built directly into IRIS (located in the More section of the app).
   - Use your diary tools whenever the user wants to save an idea, write in their diary, take a note, review recent notes, or search thoughts:
     * `create_diary_entry`: Write notes, ideas, reflections, meeting notes, or journal entries. Set title, content, category (e.g. NOTE, IDEA, REFLECTION, JOURNAL, MEETING, LEARNING), tags, and is_pinned.
     * `read_diary_entries`: Search and retrieve notes, thoughts, and ideas by keyword query, category, or tag.
     * `get_diary_entry`: View full content of a specific note by ID.
     * `update_diary_entry`: Update or append to existing notes.
     * `delete_diary_entry`: Delete notes if requested.
   - When the user asks "write this idea in my diary", "save this in my diary", "take a note", "what are my ideas in the diary", etc., act immediately using these tools!
13. PERSONAL FINANCE & EXPENSE TRACKING:
   - You have tools to record income and expenses directly into the user's finance tracker:
     * `log_transactions`: Bulk-log multiple transactions from statements, receipts, lists, or visual screenshots.
     * `log_transaction`: Log a single income or expense entry.
     * `get_finances`: Review current monthly spending, category breakdown, and balance.
   - When the user asks to add, update, or log expenses, transactions, or bank statements from screenshots/text:
     * ALWAYS execute `log_transactions` or `log_transaction` to insert them into the database.
     * NEVER just describe them in text or save them to conversational memory (`save_memory`) when asked to update/log finances.
     * Accurate Dates: Always record the exact date (occurred_on="YYYY-MM-DD") for each transaction as shown in the statement. Do not use today's date if a specific past date is shown.
     * Categories: Pick the closest category (Food & Dining, Groceries, Transport, Shopping, Bills & Utilities, Rent, Subscriptions, Health, Entertainment, Travel, Other).""",
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

        is_agy_ide = any(w in msg_lower for w in ["antigravity ide", "agy ide", "antigravity gui", "antigravity editor"])
        is_agy_cli = not is_agy_ide and (
            ("antigravity" in msg_lower or "agy" in msg_lower)
            and any(w in msg_lower for w in ["cli", "terminal", "console", "resume", "continue", "-c", "--continue", "open", "launch", "start", "run"])
            or any(msg_lower.startswith(w) for w in ["open agy", "launch agy", "start agy", "agy -c", "agy --continue", "open antigravity", "launch antigravity", "start antigravity"])
            or msg_lower.strip() in ["agy", "antigravity", "antigravity cli", "agy cli"]
        )

        if is_agy_cli:
            from app.services import mesh_service as ms
            target_dir, prompt_text, should_resume = ms.parse_antigravity_cli_intent(user_message, default_dir=r"C:\kirtan\IRIS")
            res = ms.launch_windows_app("antigravity_cli", directory=target_dir, prompt=prompt_text, resume=should_resume)
            extra_msg = []
            if should_resume:
                extra_msg.append("resuming previous conversation")
            if prompt_text:
                extra_msg.append(f"with prompt: '{prompt_text}'")
            extra_desc = f" ({', '.join(extra_msg)})" if extra_msg else ""
            msg_text = f"⚡ Opened Antigravity CLI in `{target_dir}`{extra_desc} on your Windows laptop terminal." if res.get("success") else f"Could not launch Antigravity CLI: {res.get('error')}"
            return AgentResponseSchema(
                thought=f"User commanded to open Antigravity CLI in {target_dir}.",
                actions=[],
                message=msg_text,
                actions_summary=[f"Opened Antigravity CLI in {target_dir}"],
                evidence=[f"Antigravity CLI: Active ({target_dir})"],
            )

        if is_agy_ide:
            from app.services import mesh_service as ms
            target_dir, _, _ = ms.parse_antigravity_cli_intent(user_message, default_dir=r"C:\kirtan\IRIS")
            res = ms.launch_windows_app("antigravity_ide", directory=target_dir)
            msg_text = f"🚀 I've launched Antigravity IDE in `{target_dir}` on your Windows laptop display." if res.get("success") else f"Could not launch Antigravity IDE: {res.get('error')}"
            return AgentResponseSchema(
                thought="User commanded to open Antigravity IDE.",
                actions=[],
                message=msg_text,
                actions_summary=["Launched Antigravity IDE on laptop"],
                evidence=["Antigravity IDE: Launched on WinSta0\\Default"],
            )

        is_terminal = (
            any(w in msg_lower for w in ["terminal", "powershell", "console", "command prompt", "cmd window"])
            and any(w in msg_lower for w in ["open", "launch", "start", "spawn", "bring up", "show"])
            and not is_agy_cli
        ) or msg_lower.strip() in ["open terminal", "terminal", "launch terminal", "open powershell"]

        if is_terminal:
            from app.services import mesh_service as ms
            home_dir, target_dir = ms.parse_terminal_intent(user_message)
            res = ms.launch_windows_app("terminal", directory=target_dir if target_dir != home_dir else None)
            folder_label = "your home directory" if target_dir == home_dir else f"`{target_dir}` (from home directory)"
            msg_text = (
                f"💻 Opened Terminal in {folder_label} on your Windows laptop."
                if res.get("success")
                else f"Could not launch Terminal: {res.get('error')}"
            )
            return AgentResponseSchema(
                thought=f"User commanded to open Terminal in {folder_label}.",
                actions=[],
                message=msg_text,
                actions_summary=[f"Opened Terminal in {folder_label}"],
                evidence=[f"Terminal: Active ({target_dir})"],
            )

        if "terminal" in msg_lower and any(w in msg_lower for w in ["access", "can you", "available", "support"]):
            return AgentResponseSchema(
                thought="User inquired about terminal access.",
                actions=[],
                message="Yes, I have full terminal and CLI access to your Windows laptop! You can ask me to run any command (e.g. `run command git status`, `run dir`, `run npm test`) or ask me to launch Windows Terminal on your screen.",
                actions_summary=["Confirmed terminal access"],
                evidence=["Terminal: Active on Windows Host"],
            )

        if any(w in msg_lower for w in ["vscode", "vs code", "code"]) and any(w in msg_lower for w in ["open", "launch", "start"]):
            from app.services import mesh_service as ms
            res = ms.launch_windows_app("vscode", argument=r"C:\kirtan\IRIS")
            return AgentResponseSchema(
                thought="User commanded to open VS Code.",
                actions=[],
                message="📝 Opened VS Code on your laptop display.",
                actions_summary=["Opened VS Code"],
                evidence=["VS Code: Active"],
            )

        if any(w in msg_lower for w in ["explorer", "open files", "browse folder"]):
            from app.services import mesh_service as ms
            res = ms.launch_windows_app("explorer", argument=r"C:\kirtan\IRIS")
            return AgentResponseSchema(
                thought="User commanded to open File Explorer.",
                actions=[],
                message="📁 Opened File Explorer on your laptop display.",
                actions_summary=["Opened File Explorer"],
                evidence=["File Explorer: Active"],
            )

        # Check for file surfing / reading
        if any(w in msg_lower for w in ["surf file", "read file", "show file", "cat ", "view file"]):
            from pathlib import Path
            words = user_message.strip().split()
            target_file = words[-1] if len(words) > 1 else "main.py"
            p = Path(target_file) if Path(target_file).is_absolute() else Path(r"C:\kirtan\IRIS") / target_file
            if p.exists() and p.is_file():
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                    lines = content.splitlines()[:60]
                    return AgentResponseSchema(
                        thought=f"Read file {p.name}",
                        actions=[],
                        message=f"📄 **{p.name}** ({len(lines)} lines):\n```\n" + "\n".join(lines) + "\n```",
                        actions_summary=[f"Read {p.name}"],
                        evidence=[f"File: {p.name}"],
                    )
                except Exception as exc:
                    return AgentResponseSchema(
                        thought=f"Error reading file {p.name}",
                        actions=[],
                        message=f"Could not read `{p.name}`: {exc}",
                        actions_summary=[],
                        evidence=[],
                    )

        # Check for file listing / surfing laptop files and directories
        if any(w in msg_lower for w in ["surf files", "list files", "show files", "what files", "browse files", "browse folder", "list dir", "browse directory"]):
            from app.services import mesh_service as ms
            folder_arg = None
            if " in " in msg_lower:
                folder_arg = user_message.split(" in ", 1)[1].strip().strip("'\"")
            elif " of " in msg_lower:
                folder_arg = user_message.split(" of ", 1)[1].strip().strip("'\"")

            target_dir = ms.resolve_laptop_path(folder_arg)
            if target_dir.exists() and target_dir.is_dir():
                try:
                    items = sorted(target_dir.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:30]
                    items_str = "\n".join(f"- 📁 `{i.name}/`" if i.is_dir() else f"- 📄 `{i.name}`" for i in items)
                    return AgentResponseSchema(
                        thought=f"List files in {target_dir}",
                        actions=[],
                        message=f"📂 Files in `{target_dir}` ({len(items)} items):\n{items_str}",
                        actions_summary=[f"Listed files in {target_dir.name}"],
                        evidence=[f"Files listed from {target_dir}"],
                    )
                except Exception as exc:
                    return AgentResponseSchema(
                        thought=f"Error reading directory {target_dir}",
                        actions=[],
                        message=f"Could not browse `{target_dir}`: {exc}",
                        actions_summary=[],
                        evidence=[],
                    )

        # Check for Google Drive queries
        if "google drive" in msg_lower or ("drive" in msg_lower and any(w in msg_lower for w in ["access", "files", "list", "upload", "search", "retrieve", "connect"])):
            from app.services.google_drive_service import drive_service
            acc = drive_service.get_drive_account(db, user.id)
            if not acc:
                return AgentResponseSchema(
                    thought="User asked about Google Drive.",
                    actions=[],
                    message="Google Drive integration is ready to be linked! Run `python scripts/connect_drive.py` in your terminal to authorize your Google account. Once connected, I can upload, search, and read your Drive documents anytime.",
                    actions_summary=["Checked Google Drive connection"],
                    evidence=["Google Drive: Awaiting OAuth consent"],
                )

        # Check for remote command execution ("run command", "terminal <cmd>", "exec <cmd>")
        if msg_lower.startswith("run command ") or msg_lower.startswith("exec ") or msg_lower.startswith("terminal "):
            from app.services import mesh_service as ms
            clean_cmd = user_message.replace("run command ", "").replace("exec ", "").replace("terminal ", "").strip()
            res = ms.execute_terminal_command(clean_cmd)
            out_str = (res.get("stdout") or res.get("stderr") or "Command completed with no output.").strip()
            return AgentResponseSchema(
                thought=f"Executed command: {clean_cmd}",
                actions=[],
                message=f"💻 Output for `{clean_cmd}` (Exit {res.get('returncode', 0)}):\n```\n{out_str[:2000]}\n```",
                actions_summary=[f"Ran `{clean_cmd}` on laptop"],
                evidence=[f"Exit code: {res.get('returncode', 0)}"],
            )

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
            from app.models.email_account import EmailAccount
            accounts = db.query(EmailAccount).filter(EmailAccount.user_id == user.id, EmailAccount.is_active.is_(True)).all()
            if accounts:
                accts_str = ", ".join(f"`{a.email_address}` ({a.alias})" for a in accounts)
                return AgentResponseSchema(
                    thought=f"User asked about email; found {len(accounts)} connected accounts.",
                    actions=[],
                    message=f"📧 Gmail is connected! Active inboxes: {accts_str}. You can ask me to list your unread emails, search messages, or draft replies.",
                    actions_summary=[f"Confirmed Gmail connection ({len(accounts)} accounts)"],
                    evidence=[f"Gmail account: {a.email_address} ({a.alias})" for a in accounts],
                )
            else:
                return AgentResponseSchema(
                    thought="User inquired about emails; no Gmail accounts connected.",
                    actions=[],
                    message="Gmail is not connected yet. You can connect your Gmail account by running `python scripts/connect_gmail.py --alias personal` in your terminal.",
                    actions_summary=["Gmail not connected"],
                    evidence=["Gmail integration: Not connected"],
                    missing_information="No active email accounts found.",
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
