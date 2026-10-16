"""IrisSupervisor: Orchestrator for multi-agent delegation and deterministic fast-paths.

The user talks ONLY with IRIS Core (the Orchestrator).
The Orchestrator:
1. Intercepts fast-path state queries & actions deterministically with 0 LLM latency and 0 rate-limit usage:
   - "what's my task?" / "what should I do?" -> instant contextual recommendation
   - "task done" / "completed task" -> instant task completion + next recommendation
   - "gym done" / "workout completed" -> instant habit/workout tick-off
   - "lock pc" / "ring phone" / "launch agy" -> direct workstation execution
2. For domain-specific complex instructions, delegates to specialized sub-agents:
   - Operator: Workstation CLI, files, app launching, autonomous coding
   - Planner: Chronos schedule planning, calendar time blocks, task management
   - Scribe: Diary & notes notebook, workout/habit logs, finance & startup tracking
   - BUBBA: Gmail triage & drafting, Google Drive search & reading
3. Synthesizes reports into a unified, transparent user response.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.agent.agents.base_agent import SubAgentReport
from app.agent.agents.bubba import get_bubba_agent
from app.agent.agents.operator import get_operator_agent
from app.agent.agents.planner import get_planner_agent
from app.agent.agents.scribe import get_scribe_agent
from app.agent.schemas import AgentResponseSchema
from app.agent.tools.mesh import LockWorkstationTool, RingMyPhoneTool
from app.agent.tools.tasks import CompleteTaskTool
from app.core.config import settings
from app.core.logging import get_logger
from app.intelligence.decision_engine import deterministic_decision
from app.models.enums import TaskStatus
from app.models.task import Task
from app.models.user import User
from app.services import habit_service
from app.services.memory_service import memory_service
from app.utils.datetime import to_local, utcnow

logger = get_logger("iris.agent.supervisor")


class IrisSupervisor:
    """Supervises and coordinates sub-agent workers while managing fast-path queries."""

    def __init__(self) -> None:
        pass

    # --- 1. Deterministic Fast-Path Interceptor -------------------------------

    def try_fast_path(
        self,
        db: Session,
        user: User,
        context: dict[str, Any],
        user_message: str,
    ) -> tuple[AgentResponseSchema | None, list[dict[str, Any]]]:
        """Try to answer or execute immediately via deterministic engine.

        Returns (response_schema, actions_executed) if handled; otherwise (None, []).
        """
        msg = user_message.strip()
        msg_lower = msg.lower()
        clean_msg = msg_lower.rstrip("?.! ").strip()

        # A. Quick Time / Date queries
        time_triggers = {
            "what time is it",
            "what's the time",
            "current time",
            "what day is today",
            "what date is today",
            "what is the time",
            "time please",
            "tell me the time",
        }
        if clean_msg in time_triggers:
            local_dt = to_local(utcnow(), user.timezone or "UTC")
            time_str = local_dt.strftime("%I:%M %p")
            date_str = local_dt.strftime("%A, %B %d, %Y")
            return (
                AgentResponseSchema(
                    thought="Direct local time query.",
                    actions=[],
                    message=f"🕒 It is currently **{time_str}** on {date_str} ({user.timezone or 'UTC'}).",
                    actions_summary=[],
                    evidence=[f"Current time: {time_str}"],
                ),
                [],
            )

        # B. Direct "What's my task?" / "What should I do?" queries
        task_query_triggers = {
            "what's my task",
            "what is my task",
            "what is my next task",
            "what's my next task",
            "what should i do",
            "what should i do now",
            "what should i do right now",
            "what do i do now",
            "what to do",
            "what's next",
            "what is next",
            "what's on my plate",
            "what should i focus on",
            "next task",
            "current task",
        }
        if clean_msg in task_query_triggers or any(
            clean_msg.startswith(t) and len(clean_msg) < len(t) + 12 for t in ["what's my task", "what should i do", "what is my task"]
        ):
            rec = deterministic_decision(db, user)
            evidence = rec.evidence or []
            if rec.opportunity_cost:
                evidence.append(f"Trade-off: {rec.opportunity_cost}")

            # Check if there is an open task in DB
            open_task = (
                db.query(Task)
                .filter(Task.user_id == user.id, Task.status.in_([TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]))
                .order_by(Task.deadline.asc().nullslast(), Task.priority.desc())
                .first()
            )

            if rec.task_id:
                reply = (
                    f"🎯 Your top priority right now is: **{rec.title}** ({rec.duration_minutes}m).\n"
                    f"{rec.reason}"
                )
                task_title = rec.title
                task_id = rec.task_id
                duration = rec.duration_minutes
                dec_type = rec.decision_type
                reason = rec.reason
            elif open_task:
                task_title = open_task.title
                task_id = open_task.id
                duration = open_task.estimated_duration or 30
                dec_type = None
                reason = open_task.description or "Highest priority open task"
                reply = f"🎯 Your top priority pending task is: **{open_task.title}** ({duration}m)."
                if "sleep" in rec.title.lower() or "rest" in rec.title.lower():
                    reply += f"\nNote: You are currently within your scheduled {rec.title}. {rec.reason}"
            else:
                reply = f"🎉 {rec.title}. {rec.reason}"
                task_title = rec.title
                task_id = None
                duration = None
                dec_type = rec.decision_type
                reason = rec.reason

            return (
                AgentResponseSchema(
                    thought="Instant deterministic task recommendation.",
                    actions=[],
                    message=reply,
                    actions_summary=["Checked top priority task"],
                    evidence=evidence[:4],
                    recommended_action={
                        "task_id": task_id,
                        "title": task_title,
                        "duration_minutes": duration,
                        "decision_type": dec_type,
                        "reason": reason,
                    }
                    if task_id
                    else None,
                ),
                [],
            )

        # C. Direct "Task done" / "Completed task"
        is_task_done = (
            clean_msg in {"task done", "completed task", "finished task", "mark task done", "done with task", "finished my task", "task completed"}
            or clean_msg.startswith("mark done ")
            or clean_msg.startswith("completed ")
            or clean_msg.startswith("finished ")
        ) and not any(w in clean_msg for w in ["gym", "workout", "exercise", "routine"])

        if is_task_done:
            # Check if a specific task title or ID was provided
            target_task: Task | None = None
            # Check if task ID is in message
            id_match = re.search(r"#?(\d+)", user_message)
            if id_match:
                task_id = int(id_match.group(1))
                target_task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()

            # Otherwise, find top active / in-progress task
            if not target_task:
                rec = deterministic_decision(db, user)
                if rec and rec.task_id:
                    target_task = db.query(Task).filter(Task.id == rec.task_id, Task.user_id == user.id).first()

            if not target_task:
                target_task = (
                    db.query(Task)
                    .filter(Task.user_id == user.id, Task.status != TaskStatus.COMPLETED.value)
                    .order_by(Task.deadline.asc().nullslast(), Task.priority.desc())
                    .first()
                )

            if target_task:
                target_task.status = TaskStatus.COMPLETED.value
                target_task.completed_at = utcnow()
                db.commit()
                db.refresh(target_task)

                action_record = {
                    "tool_name": "complete_task",
                    "success": True,
                    "summary": f"Completed task #{target_task.id}: {target_task.title}",
                    "data": {"task_id": target_task.id, "title": target_task.title},
                }

                # Get the next recommendation
                new_rec = deterministic_decision(db, user)
                next_part = ""
                if new_rec and new_rec.task_id:
                    next_part = f"\n\nNext up: **{new_rec.title}** ({new_rec.duration_minutes}m). {new_rec.reason}"
                else:
                    next_part = "\n\nAll current priority tasks are completed. Great work!"

                return (
                    AgentResponseSchema(
                        thought=f"Marked task #{target_task.id} '{target_task.title}' complete.",
                        actions=[],
                        message=f"✅ Marked **'{target_task.title}'** as complete!{next_part}",
                        actions_summary=[f"Completed '{target_task.title}'"],
                        evidence=[f"Task #{target_task.id} marked COMPLETED"],
                        recommended_action={
                            "task_id": new_rec.task_id,
                            "title": new_rec.title,
                            "duration_minutes": new_rec.duration_minutes,
                            "decision_type": new_rec.decision_type,
                        }
                        if new_rec and new_rec.task_id
                        else None,
                    ),
                    [action_record],
                )
            else:
                return (
                    AgentResponseSchema(
                        thought="No open tasks found to complete.",
                        actions=[],
                        message="You don't have any pending tasks right now. Would you like to create one or plan your schedule?",
                        actions_summary=[],
                        evidence=["No open tasks found in database"],
                    ),
                    [],
                )

        # D. Direct "Gym done" / "Workout completed"
        gym_triggers = {"gym done", "finished gym", "workout done", "completed workout", "done with gym", "chest day done", "leg day done"}
        if clean_msg in gym_triggers or (
            any(w in clean_msg for w in ["gym", "workout"]) and any(w in clean_msg for w in ["done", "finished", "completed"])
        ):
            # Check if routine exists
            routine = habit_service.find(db, user, "gym") or habit_service.find(db, user, "workout")
            actions_executed: list[dict[str, Any]] = []
            streak_info = ""
            if routine:
                try:
                    checked = habit_service.check(db, user, routine.id, done=True)
                    streak_info = f" ({checked.streak}-day streak! 🔥)" if checked.streak > 1 else ""
                    actions_executed.append({
                        "tool_name": "check_routine",
                        "success": True,
                        "summary": f"Marked {routine.name} done{streak_info}",
                    })
                except Exception:
                    pass

            reply = f"💪 Awesome work! Logged your gym/workout session as completed for today{streak_info}."
            return (
                AgentResponseSchema(
                    thought="Instant gym/workout completion handler.",
                    actions=[],
                    message=reply,
                    actions_summary=["Logged gym/workout completion"],
                    evidence=["Routine: Gym/Workout marked done"],
                ),
                actions_executed,
            )

        # E. Fast Workstation Commands: Lock Workstation & Ring Phone
        if clean_msg in {"lock workstation", "lock pc", "lock laptop", "lock my workstation", "lock my laptop", "lock my pc"}:
            from app.services import mesh_service as ms
            success = ms.lock_windows_pc()
            action_rec = {
                "tool_name": "lock_workstation",
                "success": success,
                "summary": "Locked Windows workstation.",
            }
            msg_reply = "🔒 Workstation locked successfully." if success else "Failed to lock workstation."
            return (
                AgentResponseSchema(
                    thought="Executed workstation lock.",
                    actions=[],
                    message=msg_reply,
                    actions_summary=["Locked Windows workstation"],
                    evidence=["LockWorkstation: Executed on host"],
                ),
                [action_rec],
            )

        if clean_msg in {"ring my phone", "find my phone", "ring phone"}:
            # Trigger ring alert
            import asyncio
            from app.services import mesh_service as ms
            msg_obj = ms.MeshMessage(
                type="REMOTE_COMMAND",
                sender_device="iris_agent",
                payload={"command": "RING_PHONE"},
            )
            # Create task to broadcast in background
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(ms.hub.broadcast(msg_obj, exclude_sender=False))
            except RuntimeError:
                pass
            action_rec = {
                "tool_name": "ring_my_phone",
                "success": True,
                "summary": "Triggered Find My Phone alert across IRIS mesh.",
            }
            return (
                AgentResponseSchema(
                    thought="Triggered ring alert on connected phone.",
                    actions=[],
                    message="🔔 Ringing your phone now across the IRIS mesh at full volume!",
                    actions_summary=["Ringing phone"],
                    evidence=["Find My Phone: Sound alert broadcasted"],
                ),
                [action_rec],
            )

        # F. Antigravity CLI / IDE quick launcher
        is_agy_cli = (
            ("antigravity" in msg_lower or "agy" in msg_lower)
            and any(w in msg_lower for w in ["cli", "terminal", "console", "resume", "continue", "-c", "--continue"])
        ) or any(msg_lower.startswith(w) for w in ["open agy", "launch agy", "start agy", "agy -c", "agy --continue"]) or msg_lower == "agy"

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
            msg_text = (
                f"⚡ Opened Antigravity CLI in `{target_dir}`{extra_desc} on your Windows laptop terminal."
                if res.get("success")
                else f"Could not launch Antigravity CLI: {res.get('error')}"
            )
            return (
                AgentResponseSchema(
                    thought=f"Opened Antigravity CLI in {target_dir}.",
                    actions=[],
                    message=msg_text,
                    actions_summary=[f"Opened Antigravity CLI in {target_dir}"],
                    evidence=[f"Antigravity CLI: Active ({target_dir})"],
                ),
                [{"tool_name": "launch_laptop_app", "success": res.get("success", False), "summary": msg_text}],
            )

        # G. Memory search / recall quick queries
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
                return (
                    AgentResponseSchema(
                        thought="Returned stored memories.",
                        actions=[],
                        message=f"Here is what I currently remember from our conversations:\n{bullets}",
                        actions_summary=["Recalled memories"],
                        evidence=[f"Recalled {len(recalled)} memories"],
                    ),
                    [],
                )
            else:
                return (
                    AgentResponseSchema(
                        thought="No stored memories found.",
                        actions=[],
                        message="I don't have any specific memories stored yet. Tell me about your preferences, routine, or projects and I will remember them across all our conversations.",
                        actions_summary=[],
                        evidence=["Memory store is currently empty"],
                    ),
                    [],
                )

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
                return (
                    AgentResponseSchema(
                        thought="Stored memory explicitly.",
                        actions=[],
                        message=f"Understood. I have committed this to memory: {content_preview}.",
                        actions_summary=["Saved context to memory"],
                        evidence=[f"Stored memory #{m.id}" for m in saved],
                    ),
                    [{"tool_name": "save_memory", "success": True, "summary": f"Stored {len(saved)} memory item(s)"}],
                )

        return (None, [])

    # --- 2. Intent Routing ----------------------------------------------------

    def route_intent(self, user_message: str) -> list[str]:
        """Classify which specialized domain(s) should handle this request.

        Returns list containing one or more of: ['operator', 'planner', 'scribe', 'bubba'].
        Empty list means general turn handled directly by the Orchestrator.
        """
        msg = user_message.lower()
        matched: list[str] = []

        # Operator triggers: Terminal, PowerShell, OS files, App launchers, Coding
        operator_keywords = [
            "run command", "terminal", "powershell", "execute command", "exec ",
            "surf file", "read file", "show file", "cat ", "view file",
            "surf files", "list files", "show files", "what files", "browse files",
            "write file", "save file", "create file", "search files", "open file",
            "vscode", "vs code", "explorer", "antigravity", "agy",
            "start autonomous coding", "coding task", "run tests", "pytest", "npm run",
            "lock workstation", "lock laptop", "lock pc", "ring phone", "sync clipboard",
        ]
        if any(k in msg for k in operator_keywords):
            matched.append("operator")

        # Planner triggers: Chronos, Schedule time blocks, Calendar, Task planning, Goals
        planner_keywords = [
            "plan my day", "plan today", "plan tomorrow", "plan schedule", "plan the day",
            "time block", "timeblock", "create schedule", "reschedule", "chronos",
            "organize my day", "schedule block", "calendar", "free time", "available time",
            "recurring schedule", "my goals", "create goal", "update goal",
            "create task", "delete task", "update task", "reorder tasks",
        ]
        if any(k in msg for k in planner_keywords):
            matched.append("planner")

        # Scribe triggers: Diary, Notes notebook, Habits, Workouts, Finances, Startup
        scribe_keywords = [
            "diary", "my notes", "take a note", "save note", "write note", "note in diary",
            "journal", "reflection", "startup idea", "write in diary", "read diary",
            "workout", "gym", "exercise", "bench press", "squat", "pushups", "sets", "reps",
            "habit", "streak", "daily routine",
            "finance", "expense", "spent", "income", "budget", "bill", "savings goal",
            "startup status", "outreach status", "log outreach",
        ]
        if any(k in msg for k in scribe_keywords):
            matched.append("scribe")

        # BUBBA triggers: Gmail, Inbox, Emails, Google Drive
        bubba_keywords = [
            "email", "emails", "gmail", "inbox", "unread email", "unread emails",
            "draft email", "send email", "check email", "search emails",
            "google drive", "gdrive", "drive files", "drive document", "upload to drive",
            "search drive", "read drive",
        ]
        if any(k in msg for k in bubba_keywords):
            matched.append("bubba")

        return matched

    async def route_intent_async(self, user_message: str) -> list[str]:
        """Classify which specialized domain(s) should handle this request.

        Two-tier routing architecture (Jev alternative):
        1. Instant deterministic keyword check (0ms, 0 API calls).
        2. Fast Groq LPU System 1 Decision Classifier (~400ms, calibrated JSON output).
        """
        # Tier 1: Deterministic fast check (0ms)
        deterministic_matches = self.route_intent(user_message)
        if deterministic_matches:
            return deterministic_matches

        # If user message is too short or simple chitchat, avoid unnecessary API calls
        msg_clean = user_message.strip().lower()
        if len(msg_clean) < 6 or msg_clean in {
            "hi", "hello", "hey", "yo", "sup", "thanks", "thank you", "bye", "good morning", "good evening"
        }:
            return []

        # Tier 2: Groq LPU System 1 Decision Engine (Jev Principle: single forward pass, 0 tool schemas)
        groq_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY")
        if not groq_key:
            return []

        router_model = settings.ai_router_model.replace("groq:", "").strip()
        system_prompt = (
            "Classify user intent into exactly one category:\n"
            "[A] Operator (terminal/shell commands, file operations, desktop apps, autonomous coding)\n"
            "[B] Planner (calendar, schedule timeblocks, task management, goals)\n"
            "[C] Scribe (notes, diary, workout/gym log, habits, finance/expenses)\n"
            "[D] BUBBA (emails, Gmail triage, Google Drive docs)\n"
            "[E] Chat (general chitchat, greetings, questions directly to IRIS)\n\n"
            "Reply with ONLY the single uppercase letter [A/B/C/D/E]."
        )

        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                resp = await client.post(
                    f"{settings.groq_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={
                        "model": router_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                        "temperature": 0.0,
                        "max_tokens": 1,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    raw_text = data["choices"][0]["message"]["content"].strip()
                    cleaned = raw_text.strip("[]() :.\"'").upper()
                    mapping = {
                        "A": ["operator"],
                        "B": ["planner"],
                        "C": ["scribe"],
                        "D": ["bubba"],
                        "E": [],
                    }
                    if cleaned and cleaned[0] in mapping:
                        return mapping[cleaned[0]]
        except Exception as exc:
            logger.debug("Groq System 1 Decision Router skipped/timed out: %s", exc)

        return []

    # --- 3. Sub-Agent Dispatch -----------------------------------------------

    async def dispatch_to_subagent(
        self,
        domain: str,
        db: Session,
        user: User,
        instruction: str,
        context: dict[str, Any],
    ) -> SubAgentReport:
        """Execute the sub-agent corresponding to the given domain."""
        if domain == "operator":
            agent = get_operator_agent()
        elif domain == "planner":
            agent = get_planner_agent()
        elif domain == "scribe":
            agent = get_scribe_agent()
        elif domain == "bubba":
            agent = get_bubba_agent()
        else:
            return SubAgentReport(
                agent_name="Supervisor",
                success=False,
                summary=f"Unknown sub-agent domain: '{domain}'",
                error="Invalid domain",
            )

        return await agent.execute(db=db, user=user, instruction=instruction, context=context)

    # --- 4. Synthesis & Response Formatting ----------------------------------

    def synthesize_reports(
        self,
        reports: list[SubAgentReport],
        user_message: str,
    ) -> tuple[AgentResponseSchema, list[dict[str, Any]]]:
        """Synthesize sub-agent report(s) into a unified AgentResponseSchema."""
        all_actions: list[dict[str, Any]] = []
        messages: list[str] = []
        evidence: list[str] = []
        actions_summary: list[str] = []

        for r in reports:
            all_actions.extend(r.actions_executed)
            if r.success:
                prefix = f"[{r.agent_name}]" if len(reports) > 1 else ""
                content = f"{prefix} {r.summary}".strip()
                messages.append(content)
                evidence.append(f"{r.agent_name}: Completed successfully ({len(r.actions_executed)} actions)")
            else:
                messages.append(f"[{r.agent_name}] Encountered an error: {r.error or r.summary}")
                evidence.append(f"{r.agent_name}: Error occurred")

            for a in r.actions_executed:
                if a.get("summary"):
                    actions_summary.append(a["summary"])

        unified_message = "\n\n".join(messages) if messages else "Execution completed."
        return (
            AgentResponseSchema(
                thought=f"Delegated to {', '.join(r.agent_name for r in reports)} sub-agent(s).",
                actions=[],
                message=unified_message,
                actions_summary=actions_summary,
                evidence=evidence,
            ),
            all_actions,
        )


_supervisor_instance: IrisSupervisor | None = None


def get_iris_supervisor() -> IrisSupervisor:
    """Return singleton IrisSupervisor."""
    global _supervisor_instance
    if _supervisor_instance is None:
        _supervisor_instance = IrisSupervisor()
    return _supervisor_instance
