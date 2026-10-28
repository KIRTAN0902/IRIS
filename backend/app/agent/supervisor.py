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
from datetime import datetime, timedelta
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
from app.ai.deadline import get_current_deadline
from app.core.config import settings
from app.core.logging import get_logger
from app.intelligence.decision_engine import deterministic_decision
from app.models.ai_memory import AIMemory
from app.models.enums import TaskStatus, TimeBlockStatus
from app.models.task import Task
from app.models.time_block import TimeBlock
from app.models.user import User
from app.services import habit_service
from app.services.agy_bridge import NATIVE_SLASH_COMMANDS, AgyError, agy_manager
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
        resp, actions = self._try_fast_path_impl(db, user, context, user_message)
        if resp is not None:
            resp.fast_path = True
            for a in actions:
                if isinstance(a, dict):
                    a["fast_path"] = True
        return resp, actions

    def _try_fast_path_impl(
        self,
        db: Session,
        user: User,
        context: dict[str, Any],
        user_message: str,
    ) -> tuple[AgentResponseSchema | None, list[dict[str, Any]]]:
        msg = user_message.strip()
        msg_lower = msg.lower()
        clean_msg = msg_lower.rstrip("?.! ").strip()
        norm_msg = re.sub(
            r"^(?:hey\s+iris[,:\s]*|iris[,:\s]*|can\s+you\s+(?:please\s+)?|could\s+you\s+(?:please\s+)?|would\s+you\s+(?:please\s+)?|will\s+you\s+(?:please\s+)?|please\s+)+",
            "",
            clean_msg,
            flags=re.IGNORECASE,
        ).strip()

        # A0. Persistent Antigravity terminal fast-paths (0 LLM tokens)
        session_words = msg.split()
        native_command = (
            session_words[0].lower() if session_words and session_words[0].startswith("/") else ""
        )
        if native_command in NATIVE_SLASH_COMMANDS:
            return self._fast_agy_slash(db, user, native_command)

        agy_match = re.match(r"^agy(?:\s+(.*))?$", msg, re.IGNORECASE | re.DOTALL)
        if agy_match:
            return self._fast_agy_command(db, user, (agy_match.group(1) or "").strip())

        bare_attach_match = re.match(
            r"^(?:attach(?:\s+to)?|switch(?:\s+to)?|cd(?:\s+into|\s+to)?|use)\s+(.+)$",
            clean_msg,
            re.IGNORECASE | re.DOTALL,
        )
        if bare_attach_match:
            target_arg = bare_attach_match.group(1).strip()
            if target_arg.lower() in {
                "antigravity",
                "agy",
                "session",
                "agy session",
                "antigravity session",
                "workspace",
            }:
                return self._fast_agy_command(db, user, "")
            return self._fast_agy_command(db, user, f"attach {target_arg}")

        if clean_msg in {
            "attach antigravity",
            "attach agy",
            "open antigravity session",
            "start agy session",
        }:
            return self._fast_agy_command(db, user, "")

        changes_match = re.match(
            r"^(?:what did we change in|what changed in|last changes in|show agy diff for|show changes for)\s+(.+)$",
            clean_msg,
        )
        if changes_match:
            return self._fast_agy_changes(db, user, changes_match.group(1))

        expense_match = re.match(
            r"^(?:spent|paid|expense)\s+(\d+(?:\.\d+)?)\s+(?:on|for)\s+(.+)$",
            clean_msg,
        )
        if expense_match:
            return self._fast_log_expense(db, user, expense_match.group(1), expense_match.group(2))

        if "reflow schedule" in clean_msg or "pushed back by" in clean_msg:
            return self._fast_reflow_schedule(db, user, clean_msg)

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

        # D. Direct "Gym done" / "Workout completed" / "Yoga done"
        fitness_triggers = {
            "gym done", "finished gym", "workout done", "completed workout", "done with gym",
            "chest day done", "leg day done",
            "yoga done", "finished yoga", "completed yoga", "yoga completed", "done with yoga", "asana done",
        }
        is_fitness_completion = clean_msg in fitness_triggers or (
            any(w in clean_msg for w in ["gym", "workout", "yoga"]) and any(w in clean_msg for w in ["done", "finished", "completed"])
        )
        if is_fitness_completion:
            is_yoga = "yoga" in clean_msg or "asana" in clean_msg
            routine = None
            if is_yoga:
                routine = habit_service.find(db, user, "yoga") or habit_service.find(db, user, "asana")
            if not routine:
                routine = habit_service.find(db, user, "gym") or habit_service.find(db, user, "workout") or habit_service.find(db, user, "yoga")

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

            item_label = "yoga session" if is_yoga else "gym/workout session"
            reply_icon = "🧘 Namaste!" if is_yoga else "💪 Awesome work!"
            reply = f"{reply_icon} Logged your {item_label} as completed for today{streak_info}."
            return (
                AgentResponseSchema(
                    thought=f"Instant {item_label} completion handler.",
                    actions=[],
                    message=reply,
                    actions_summary=[f"Logged {item_label} completion"],
                    evidence=[f"Routine: {item_label} marked done"],
                ),
                actions_executed,
            )

        # E. Fast Workstation Commands: Lock Workstation & Ring Phone
        lock_triggers = {"lock workstation", "lock pc", "lock laptop", "lock my workstation", "lock my laptop", "lock my pc"}
        if clean_msg in lock_triggers or norm_msg in lock_triggers:
            from app.services import mesh_service as ms
            from app.services import mesh_relay_service as mrs

            if mrs.is_local_windows_host():
                success = ms.lock_windows_pc()
            else:
                if not mrs.is_host_laptop_online(db, user.id, threshold_seconds=300.0):
                    return (
                        AgentResponseSchema(
                            thought="Laptop offline for lock command.",
                            actions=[],
                            message="⚠️ Your Windows laptop is currently offline or unreachable on the IRIS mesh. Please ensure your laptop is powered on with the IRIS daemon running.",
                            actions_summary=["Laptop offline"],
                        ),
                        [{"tool_name": "lock_workstation", "success": False, "summary": "Laptop offline"}],
                    )
                mrs.push_relay_message(
                    db=db,
                    user_id=user.id,
                    sender_device_id="mobile_assistant",
                    target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
                    msg_type="REMOTE_COMMAND",
                    payload={"command": "LOCK_PC"},
                )
                success = True

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

        ring_triggers = {"ring my phone", "find my phone", "ring phone"}
        if clean_msg in ring_triggers or norm_msg in ring_triggers:
            # Trigger ring alert
            import asyncio
            from app.services import mesh_service as ms
            from app.services import mesh_relay_service as mrs

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

            mrs.push_relay_message(
                db=db,
                user_id=user.id,
                sender_device_id="iris_agent",
                target_device_id=None,
                msg_type="REMOTE_COMMAND",
                payload={"command": "RING_PHONE"},
            )

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

        # F. Universal Dynamic Peer Action Dispatcher (Zero Hardcoding, Millisecond Execution)
        req_clean = norm_msg
        app_launch_match = re.match(
            r"^(?:open|launch|start|spawn|bring up)\s+(.+?)(?:\s+(?:on|in|at)\s+(?:my\s+)?(laptop|phone|pc|mobile|computer|workstation|desktop))?$",
            req_clean,
            re.IGNORECASE,
        )
        if app_launch_match:
            raw_target_app = app_launch_match.group(1).strip()
            device_hint = (app_launch_match.group(2) or "").lower().strip()

            from app.services import mesh_service as ms
            from app.services import mesh_relay_service as mrs

            # Extract directory preserving original casing from user_message
            orig_dir_match = re.search(
                r'\b(?:in|at|into)\s+([a-zA-Z]:\\[^\s"\'`]+|[a-zA-Z]:/[^\s"\'`]+|[a-zA-Z0-9_\-\\.]+)',
                user_message,
                re.IGNORECASE,
            )
            target_directory = None
            if orig_dir_match:
                cand_dir = orig_dir_match.group(1).strip().strip("'\"`")
                if cand_dir.lower() not in ["terminal", "cli", "powershell", "cmd", "console", "wt", "window", "tab", "laptop", "pc", "phone"]:
                    target_directory = cand_dir
                    clean_app = re.sub(r'\b(?:in|at|into)\s+.*$', '', raw_target_app, flags=re.IGNORECASE).strip()
                else:
                    clean_app = raw_target_app
            else:
                clean_app = raw_target_app

            clean_app = re.sub(r"\s+(?:for\s+me|please)$", "", clean_app, flags=re.IGNORECASE).strip()
            clean_app_low = clean_app.lower()

            # Target Device Resolution: Phone vs Laptop
            mobile_indicators = {
                "camera", "whatsapp", "instagram", "gpay", "google pay", "phonepe", "paytm",
                "zomato", "swiggy", "uber", "ola", "zepto", "blinkit", "gallery", "phone",
                "contacts", "messages", "sms"
            }
            is_phone_target = device_hint in ["phone", "mobile"] or (
                device_hint == "" and clean_app_low in mobile_indicators
            )

            if is_phone_target:
                # Dispatch dynamically to Mobile Phone Companion
                msg_obj = ms.MeshMessage(
                    type="LAUNCH_APP",
                    sender_device="iris_agent",
                    payload={"app": clean_app, "target": "mobile"}
                )
                try:
                    import asyncio
                    loop = asyncio.get_running_loop()
                    loop.create_task(ms.hub.broadcast(msg_obj, exclude_sender=False))
                except RuntimeError:
                    pass

                mrs.push_relay_message(
                    db=db,
                    user_id=user.id,
                    sender_device_id="iris_agent",
                    target_device_id=None,
                    msg_type="LAUNCH_APP",
                    payload={"app": clean_app, "target": "mobile"},
                )
                msg_reply = f"📱 Opening **{clean_app.title()}** on your phone."
                return (
                    AgentResponseSchema(
                        thought=f"Dispatched dynamic launch for {clean_app} to mobile companion.",
                        actions=[],
                        message=msg_reply,
                        actions_summary=[f"Opened {clean_app.title()} on phone"],
                        evidence=[f"Phone App: {clean_app.title()}"],
                    ),
                    [{"tool_name": "launch_mobile_app", "success": True, "app": clean_app, "summary": msg_reply}],
                )

            else:
                # Dispatch dynamically to Windows Laptop Workstation
                is_agy_cli = clean_app_low in ["agy", "antigravity", "antigravity cli", "agy cli"] or "cli" in clean_app_low
                is_terminal = clean_app_low in ["terminal", "powershell", "wt", "cmd", "windows terminal"]
                target_dir = target_directory
                prompt_text = None
                should_resume = False

                if is_agy_cli:
                    target_dir, prompt_text, should_resume = ms.parse_antigravity_cli_intent(user_message, default_dir=r"C:\kirtan\IRIS")
                    clean_app = "antigravity_cli"
                elif is_terminal:
                    clean_app = "terminal"

                if mrs.is_local_windows_host():
                    if is_agy_cli:
                        res = ms.launch_windows_app(
                            "antigravity_cli",
                            directory=target_dir,
                            prompt=prompt_text,
                            resume=should_resume,
                        )
                        app_title = res.get("app", "Antigravity CLI")
                    elif is_terminal:
                        res = ms.launch_windows_app("terminal", directory=target_dir)
                        app_title = res.get("app", "Terminal")
                    else:
                        res = ms.launch_windows_app(
                            clean_app,
                            directory=target_dir,
                            prompt=prompt_text,
                            resume=should_resume,
                        )
                        app_title = res.get("app", clean_app.title())

                    if is_terminal and res.get("success"):
                        if target_dir:
                            msg_reply = f"💻 Opened Terminal in `{target_dir}` (from home directory) on your Windows laptop."
                        else:
                            msg_reply = "💻 Opened Terminal in your home directory on your Windows laptop."
                    elif res.get("success"):
                        folder_str = f" in `{target_dir}`" if target_dir else ""
                        msg_reply = f"💻 Opened **{app_title}**{folder_str} on your Windows laptop."
                    else:
                        msg_reply = f"Could not launch {clean_app}: {res.get('error')}"
                else:
                    if not mrs.is_host_laptop_online(db, user.id, threshold_seconds=300.0):
                        return (
                            AgentResponseSchema(
                                thought="Laptop offline for dynamic app launch.",
                                actions=[],
                                message="⚠️ Your Windows laptop is currently offline or unreachable on the IRIS mesh. Please ensure your laptop is powered on with the IRIS daemon running.",
                                actions_summary=["Laptop offline"],
                            ),
                            [{"tool_name": "launch_laptop_app", "success": False, "summary": "Laptop offline"}],
                        )
                    mrs.push_relay_message(
                        db=db,
                        user_id=user.id,
                        sender_device_id="mobile_assistant",
                        target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
                        msg_type="REMOTE_COMMAND",
                        payload={
                            "command": "LAUNCH_APP",
                            "app": clean_app,
                            "directory": target_dir,
                            "prompt": prompt_text,
                            "resume": should_resume,
                        },
                    )
                    app_title = clean_app.replace("_", " ").title()
                    folder_str = f" in `{target_dir}`" if target_dir else ""
                    msg_reply = f"💻 Opened **{app_title}**{folder_str} on your Windows laptop."

                return (
                    AgentResponseSchema(
                        thought=f"Dispatched dynamic launch for {clean_app} to laptop workstation.",
                        actions=[],
                        message=msg_reply,
                        actions_summary=[f"Opened {clean_app.title()} on laptop"],
                        evidence=[f"Laptop App: {clean_app.title()}"],
                    ),
                    [{"tool_name": "launch_laptop_app", "success": True, "summary": msg_reply}],
                )

        # G. Dynamic Command Execution on Laptop
        cmd_exec_match = re.match(
            r"^(?:run|exec|execute|powershell|cmd)\s+(?:command\s+)?[\"']?(.+?)[\"']?(?:\s+(?:on|in)\s+(?:my\s+)?(laptop|pc|computer))?$",
            req_clean,
            re.IGNORECASE,
        )
        if cmd_exec_match:
            candidate_cmd = cmd_exec_match.group(1).strip()
            from app.services import mesh_service as ms
            from app.services import mesh_relay_service as mrs

            if candidate_cmd.lower() in ["terminal", "powershell", "wt", "cmd", "windows terminal"]:
                if mrs.is_local_windows_host():
                    res = ms.launch_windows_app("terminal")
                    msg_reply = "💻 Opened **Terminal** on your Windows laptop." if res.get("success") else f"Could not launch Terminal: {res.get('error')}"
                else:
                    if not mrs.is_host_laptop_online(db, user.id, threshold_seconds=300.0):
                        return (
                            AgentResponseSchema(
                                thought="Laptop offline for terminal launch.",
                                actions=[],
                                message="⚠️ Your Windows laptop is currently offline or unreachable on the IRIS mesh. Please ensure your laptop is powered on with the IRIS daemon running.",
                                actions_summary=["Laptop offline"],
                            ),
                            [{"tool_name": "launch_laptop_app", "success": False, "summary": "Laptop offline"}],
                        )
                    mrs.push_relay_message(
                        db=db,
                        user_id=user.id,
                        sender_device_id="mobile_assistant",
                        target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
                        msg_type="REMOTE_COMMAND",
                        payload={"command": "LAUNCH_APP", "app": "terminal"},
                    )
                    msg_reply = "💻 Opened **Terminal** on your Windows laptop."
                return (
                    AgentResponseSchema(
                        thought="Dispatched terminal launch to laptop workstation.",
                        actions=[],
                        message=msg_reply,
                        actions_summary=["Opened Terminal on laptop"],
                        evidence=["Laptop App: Terminal"],
                    ),
                    [{"tool_name": "launch_laptop_app", "success": True, "summary": msg_reply}],
                )

            if candidate_cmd and not any(candidate_cmd.lower().startswith(w) for w in ["app", "today", "tasks"]):
                if mrs.is_local_windows_host():
                    res = ms.execute_terminal_command(candidate_cmd)
                    output = (res.get("stdout") or res.get("stderr") or "Command executed.").strip()
                    msg_reply = f"💻 Executed `{candidate_cmd}` on your laptop:\n```\n{output[:1500]}\n```"
                else:
                    if not mrs.is_host_laptop_online(db, user.id, threshold_seconds=300.0):
                        return (
                            AgentResponseSchema(
                                thought="Laptop offline for command execution.",
                                actions=[],
                                message="⚠️ Your Windows laptop is currently offline or unreachable on the IRIS mesh.",
                                actions_summary=["Laptop offline"],
                            ),
                            [{"tool_name": "run_laptop_terminal_command", "success": False, "summary": "Laptop offline"}],
                        )
                    mrs.push_relay_message(
                        db=db,
                        user_id=user.id,
                        sender_device_id="mobile_assistant",
                        target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
                        msg_type="TERMINAL_EXEC",
                        payload={"command": candidate_cmd, "timeout": 20},
                    )
                    msg_reply = f"💻 Dispatched command `{candidate_cmd}` to execute on your Windows laptop."

                return (
                    AgentResponseSchema(
                        thought=f"Executed command {candidate_cmd} on laptop.",
                        actions=[],
                        message=msg_reply,
                        actions_summary=[f"Executed `{candidate_cmd}` on laptop"],
                        evidence=[f"Command: {candidate_cmd}"],
                    ),
                    [{"tool_name": "run_laptop_terminal_command", "success": True, "summary": msg_reply}],
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

    # --- 1b. Antigravity & deterministic action helpers ---------------------

    def _agy_response(
        self,
        message: str,
        summary: str,
        evidence: list[str] | None = None,
        actions: list[dict[str, Any]] | None = None,
    ) -> tuple[AgentResponseSchema, list[dict[str, Any]]]:
        return (
            AgentResponseSchema(
                thought=summary,
                actions=[],
                message=message,
                actions_summary=[summary],
                evidence=evidence or [summary],
                fast_path=True,
            ),
            actions or [],
        )

    def _ensure_agy_session(self):
        session = agy_manager.find_session(agy_manager.current_session_key)
        if session is not None and session.alive:
            return session
        return agy_manager.spawn_or_attach(None, None)

    def _fast_agy_slash(
        self, db: Session, user: User, command: str
    ) -> tuple[AgentResponseSchema, list[dict[str, Any]]]:
        try:
            session = self._ensure_agy_session()
            agy_manager.send_raw_input(session.key, command)
        except AgyError as exc:
            return self._agy_response(
                f"⚠️ Antigravity is unavailable: {exc}",
                "Antigravity attach failed",
                [str(exc)],
            )
        if command == "/clear":
            session.buffer.clear()
        output = session.recent(24).strip()
        body = f"**Antigravity · {session.alias} · `{command}`**"
        if output:
            body += f"\n\n```text\n{output}\n```"
        return self._agy_response(
            body,
            f"Ran {command} in {session.alias}",
            [f"Session: {session.directory}", f"Command: {command}"],
            [
                {
                    "tool_name": "agy_run_slash_command",
                    "success": True,
                    "summary": f"Ran {command} in {session.alias}",
                }
            ],
        )

    def _fast_agy_command(
        self, db: Session, user: User, rest: str
    ) -> tuple[AgentResponseSchema, list[dict[str, Any]]]:
        try:
            target = re.match(
                r"^(?:attach(?:\s+to)?|switch(?:\s+to)?|cd(?:\s+into|\s+to)?|use)\s+(.+)$",
                rest,
                re.IGNORECASE | re.DOTALL,
            )
            if target:
                session = agy_manager.spawn_or_attach(target.group(1).strip(), None)
                return self._agy_response(
                    f"🔗 Attached to Antigravity session **{session.alias}** in `{session.directory}`.",
                    f"Attached to {session.alias}",
                    [f"Directory: {session.directory}"],
                    [
                        {
                            "tool_name": "agy_attach_directory",
                            "success": True,
                            "summary": f"Attached to {session.alias}",
                            "data": {
                                "key": session.key,
                                "alias": session.alias,
                                "directory": session.directory,
                            },
                        }
                    ],
                )
            session = self._ensure_agy_session()
            if not rest:
                return self._agy_response(
                    f"🔗 Antigravity session **{session.alias}** is ready in `{session.directory}`. "
                    "Send a prompt or a native command such as `/models`.",
                    f"Attached to {session.alias}",
                    [f"Directory: {session.directory}"],
                    [
                        {
                            "tool_name": "agy_attach_directory",
                            "success": True,
                            "summary": f"Attached to {session.alias}",
                            "data": {
                                "key": session.key,
                                "alias": session.alias,
                                "directory": session.directory,
                            },
                        }
                    ],
                )
            if rest.startswith("/"):
                return self._fast_agy_slash(db, user, rest.split()[0].lower())
            agy_manager.send_prompt(session.key, rest)
            return self._agy_response(
                f"⚡ Sent to Antigravity in **{session.alias}**: `{rest[:240]}`\n"
                "It is working now; I will report the git summary when it settles.",
                f"Sent prompt to {session.alias}",
                [f"Session: {session.directory}"],
                [
                    {
                        "tool_name": "agy_execute_prompt",
                        "success": True,
                        "summary": f"Sent prompt to {session.alias}",
                    }
                ],
            )
        except AgyError as exc:
            target_err = re.match(
                r"^(?:attach(?:\s+to)?|switch(?:\s+to)?|cd(?:\s+into|\s+to)?|use)\s+(.+)$",
                rest,
                re.IGNORECASE | re.DOTALL,
            )
            action_list = []
            if target_err or not rest:
                action_list.append(
                    {
                        "tool_name": "agy_attach_directory",
                        "success": False,
                        "summary": f"Failed to attach: {exc}",
                        "error": str(exc),
                    }
                )
            return self._agy_response(
                f"⚠️ Antigravity is unavailable: {exc}",
                "Antigravity command failed",
                [str(exc)],
                action_list if action_list else None,
            )

    def _fast_agy_changes(
        self, db: Session, user: User, raw_project: str
    ) -> tuple[AgentResponseSchema, list[dict[str, Any]]]:
        project = re.sub(r"\b(project|repo|repository|code|workspace)\b", "", raw_project).strip()
        project = project or raw_project.strip()
        slug = re.sub(r"\s+", "_", project.lower())
        memory = (
            db.query(AIMemory)
            .filter(
                AIMemory.user_id == user.id,
                AIMemory.category.ilike("coding_session"),
                AIMemory.key.ilike(f"agy:{slug}:%"),
            )
            .order_by(AIMemory.updated_at.desc())
            .first()
        )
        if memory is None:
            memory = (
                db.query(AIMemory)
                .filter(
                    AIMemory.user_id == user.id,
                    AIMemory.category.ilike("coding_session"),
                    AIMemory.content.ilike(f"%{project}%"),
                )
                .order_by(AIMemory.updated_at.desc())
                .first()
            )
        if memory is None:
            session = agy_manager.find_session(slug) or agy_manager.find_session(project)
            if session and session.last_summary:
                return self._agy_response(
                    f"**{session.alias}** · {session.last_summary}\n\n```text\n{session.last_diff_stat or 'No diff stat'}\n```",
                    f"Read live diff for {session.alias}",
                    [f"Session: {session.directory}"],
                )
            return self._agy_response(
                f"I have no harvested coding changes for **{project}** yet. "
                f"Say `agy switch {project}` and give me a task.",
                f"No coding memory for {project}",
                [f"Project: {project}"],
            )
        try:
            payload = json.loads(memory.content)
        except (TypeError, ValueError):
            payload = {"summary": memory.content[:800]}
        summary = payload.get("summary") or "No summary stored."
        prompt = payload.get("prompt") or ""
        diff_stat = payload.get("diff_stat") or ""
        body = f"**{project} · last Antigravity task**\n{summary}"
        if prompt:
            body += f"\n\n> {prompt[:400]}"
        if diff_stat:
            body += f"\n\n```text\n{diff_stat[:2000]}\n```"
        return self._agy_response(
            body,
            f"Recalled changes for {project}",
            [f"Memory #{memory.id}", f"Project: {project}"],
        )

    def _fast_log_expense(
        self, db: Session, user: User, amount_raw: str, clue: str
    ) -> tuple[AgentResponseSchema, list[dict[str, Any]]]:
        amount = float(amount_raw)
        if amount <= 0:
            return self._agy_response(
                "Expense amount must be greater than zero.",
                "Rejected zero expense",
            )
        clue = " ".join(clue.split()).strip(" .")
        try:
            from app.schemas.finance import TransactionCreate
            from app.services import finance_service

            txn = finance_service.create_transaction(
                db,
                user,
                TransactionCreate(
                    kind="EXPENSE",
                    amount=amount,
                    category=clue[:60],
                    note=clue[:255],
                ),
            )
            today = finance_service.today_for(user)
            todays_total = sum(
                t.amount
                for t in finance_service.list_transactions(
                    db, user, kind="EXPENSE", limit=500
                )
                if t.occurred_on == today
            )
        except Exception as exc:
            logger.warning("Fast expense path failed: %s", exc)
            return self._agy_response(
                f"Could not log that expense: {exc}",
                "Expense logging failed",
                [str(exc)],
            )
        return self._agy_response(
            f"💸 Logged **₹{amount:,.2f}** for **{clue}**.\nToday's expenses: **₹{todays_total:,.2f}**.",
            f"Logged ₹{amount:,.2f} expense for {clue}",
            [f"Transaction #{txn.id}", f"Category: {txn.category}"],
            [
                {
                    "tool_name": "log_expense",
                    "success": True,
                    "summary": f"Logged ₹{amount:,.2f} for {clue}",
                    "data": {"transaction_id": txn.id, "amount": amount},
                }
            ],
        )

    def _fast_reflow_schedule(
        self, db: Session, user: User, clean_msg: str
    ) -> tuple[AgentResponseSchema, list[dict[str, Any]]]:
        match = re.search(
            r"(?:pushed back by|reflow schedule(?: by)?)\s*(\d+)\s*(?:m|min|mins|minutes)?",
            clean_msg,
        )
        minutes = int(match.group(1)) if match else 15
        minutes = max(5, min(minutes, 480))
        now = utcnow()
        try:
            from app.services import schedule_service

            blocks = schedule_service.list_time_blocks(db, user.id, start=now)
            movable = [
                block
                for block in blocks
                if block.status == TimeBlockStatus.SCHEDULED.value and block.start_time >= now
            ]
            delta = timedelta(minutes=minutes)
            for block in movable:
                block.start_time += delta
                block.end_time += delta
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Fast schedule reflow failed: %s", exc)
            return self._agy_response(
                f"Could not reflow the schedule: {exc}",
                "Schedule reflow failed",
            )
        if not movable:
            return self._agy_response(
                f"No upcoming scheduled blocks to push back by {minutes}m.",
                "No movable schedule blocks",
            )
        nxt = min(movable, key=lambda block: block.start_time)
        local_start = to_local(nxt.start_time, user.timezone or "UTC").strftime("%a %I:%M %p")
        return self._agy_response(
            f"⏩ Pushed **{len(movable)}** upcoming block(s) back by **{minutes}m** "
            f"(movable only). Next up at **{local_start}**.",
            f"Reflowed {len(movable)} blocks by {minutes}m",
            [f"Moved {len(movable)} SCHEDULED blocks", f"Delta: {minutes}m"],
            [
                {
                    "tool_name": "reflow_schedule",
                    "success": True,
                    "summary": f"Pushed {len(movable)} blocks back by {minutes}m",
                    "data": {"blocks": len(movable), "minutes": minutes},
                }
            ],
        )

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
            "laptop screen", "computer screen", "screen capture", "screenshot of laptop",
            "see my screen", "look at my laptop", "check my laptop", "what's on my laptop",
            "what is on my laptop", "capture laptop screen",
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
            "yoga", "asana", "pranayama", "surya namaskar",
            "habit", "streak", "daily routine",
            "finance", "finances", "expense", "expenses", "spent", "income", "budget", "bill", "bills",
            "savings goal", "transaction", "transactions", "payment", "payments", "gpay", "google pay",
            "phonepe", "paytm", "banking", "credit", "debit", "receipt", "receipts", "invoice", "invoices",
            "rupee", "rupees", "inr",
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

        # Tier 2: System 1 Decision Engine (Jev Principle: single forward pass, 0 tool schemas)
        router_spec = (settings.ai_router_model or "").strip()
        if not router_spec and settings.groq_api_key:
            router_spec = f"groq:{settings.groq_model or 'qwen/qwen3.8-27b'}"

        if router_spec.startswith("nvidia:"):
            router_base_url = settings.nvidia_base_url
            router_api_key = settings.nvidia_api_key or os.environ.get("NVIDIA_API_KEY")
            router_model = router_spec.replace("nvidia:", "").strip()
        elif router_spec.startswith("groq:"):
            router_base_url = settings.groq_base_url or "https://api.groq.com/openai/v1"
            router_api_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY")
            router_model = router_spec.replace("groq:", "").strip()
        elif router_spec.startswith("gemini:") or not router_spec or router_spec.startswith("google/"):
            router_base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
            router_api_key = (
                settings.gemini_api_key
                or settings.ai_api_key
                or os.environ.get("GEMINI_API_KEY")
            )
            raw_m = router_spec.replace("gemini:", "").strip()
            # If default gemma-4-31b-it on Google Developer endpoint, use gemini-3.1-flash-lite to avoid 47s thinking latency
            if not raw_m or "gemma-4-31b" in raw_m.lower():
                router_model = "gemini-3.1-flash-lite"
            else:
                router_model = f"models/{raw_m}" if raw_m.startswith("gemma-") and not raw_m.startswith("models/") else raw_m
        else:
            router_base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
            router_api_key = (
                settings.gemini_api_key
                or settings.ai_api_key
                or os.environ.get("GEMINI_API_KEY")
            )
            raw_m = router_spec.replace("gemini:", "").strip()
            router_model = raw_m or "gemini-3.1-flash-lite"

        if not router_api_key:
            return []

        system_prompt = (
            "Classify user intent into exactly one category:\n"
            "[A] Operator (terminal/shell commands, file operations, desktop apps, autonomous coding)\n"
            "[B] Planner (calendar, schedule timeblocks, task management, goals)\n"
            "[C] Scribe (notes, diary, workout/gym log, habits, finance/expenses)\n"
            "[D] BUBBA (emails, Gmail triage, Google Drive docs)\n"
            "[E] Chat (general chitchat, greetings, questions directly to IRIS)\n\n"
            "Reply with ONLY the single uppercase letter [A/B/C/D/E]."
        )

        payload: dict[str, Any] = {
            "model": router_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.0,
            "max_tokens": 10,
        }
        # chat_template_kwargs is supported by vLLM/NVIDIA NIM endpoints to disable thinking,
        # but Google Gemini (googleapis.com) strictly rejects unknown fields with HTTP 400.
        if "googleapis.com" not in router_base_url.lower():
            if any(k in router_model.lower() for k in ("nemotron", "gemma", "qwen")) or "nvidia" in router_base_url.lower():
                payload["chat_template_kwargs"] = {"enable_thinking": False}

        dl = get_current_deadline()
        router_timeout = min(dl.per_attempt_timeout(4.0), 4.0) if dl is not None else 4.0

        try:
            async with httpx.AsyncClient(timeout=router_timeout) as client:
                resp = await client.post(
                    f"{router_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {router_api_key}", "Content-Type": "application/json"},
                    json=payload,
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
            logger.debug("System 1 Decision Router skipped/timed out: %s", exc)

        return []

    # --- 3. Sub-Agent Dispatch -----------------------------------------------

    def slice_context_for_domain(
        self,
        db: Session,
        user: User,
        domain: str,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Give each sub-agent only the state slice it needs.

        Keeps routing latency and prompt tokens bounded by the agent's domain
        instead of serializing the entire life OS on every delegation.
        """
        tz = user.timezone or "UTC"
        now = utcnow()
        shared: dict[str, Any] = {
            "user_name": user.name,
            "timezone": tz,
            "now_local": to_local(now, tz).isoformat(),
        }

        if domain == "operator":
            session = agy_manager.find_session(agy_manager.current_session_key)
            coding_memories = (
                db.query(AIMemory)
                .filter(AIMemory.user_id == user.id, AIMemory.category.ilike("coding_session"))
                .order_by(AIMemory.updated_at.desc())
                .limit(5)
                .all()
            )
            shared.update(
                {
                    "platform": os.name,
                    "working_directory": session.directory
                    if session
                    else settings.agy_default_directory,
                    "agy_sessions": [
                        {
                            "alias": item.alias,
                            "directory": item.directory,
                            "state": item.state,
                            "last_summary": item.last_summary,
                        }
                        for item in agy_manager.active_sessions.values()
                    ],
                    "recent_coding_sessions": [
                        {
                            "key": item.key,
                            "content": item.content[:1200],
                            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                        }
                        for item in coding_memories
                    ],
                }
            )
        elif domain == "planner":
            from app.services import schedule_service

            blocks = schedule_service.list_time_blocks(
                db, user.id, start=now, end=now + timedelta(days=2)
            )
            tasks = (
                db.query(Task)
                .filter(
                    Task.user_id == user.id,
                    Task.status.in_([TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]),
                )
                .order_by(Task.deadline.asc().nullslast(), Task.priority.desc())
                .limit(20)
                .all()
            )
            shared.update(
                {
                    "upcoming_blocks": [
                        {
                            "id": block.id,
                            "title": block.task.title if block.task else block.type,
                            "start": block.start_time.isoformat(),
                            "end": block.end_time.isoformat(),
                            "status": block.status,
                        }
                        for block in blocks
                    ],
                    "open_tasks": [
                        {
                            "id": task.id,
                            "title": task.title,
                            "status": task.status,
                            "priority": task.priority,
                            "deadline": task.deadline.isoformat() if task.deadline else None,
                            "estimated_duration": task.estimated_duration,
                        }
                        for task in tasks
                    ],
                }
            )
        elif domain == "scribe":
            from app.models.lead import Lead
            from app.models.startup import Startup
            from app.services import diary_service, finance_service

            brief = habit_service.situation_brief(db, user) or []
            transactions = finance_service.list_transactions(db, user, limit=10)
            lead_counts: dict[str, int] = {}
            rows = (
                db.query(Lead.status)
                .join(Startup, Lead.startup_id == Startup.id)
                .filter(Startup.user_id == user.id)
                .all()
            )
            for (status_value,) in rows:
                lead_counts[status_value] = lead_counts.get(status_value, 0) + 1
            shared.update(
                {
                    "habits": brief[:10],
                    "recent_expenses": [
                        {
                            "amount": txn.amount,
                            "category": txn.category,
                            "kind": txn.kind,
                            "occurred_on": txn.occurred_on.isoformat() if txn.occurred_on else None,
                        }
                        for txn in transactions
                    ],
                    "diary": diary_service.get_diary_summary(db, user.id),
                    "crm_pipeline": lead_counts,
                }
            )
        elif domain == "bubba":
            from app.models.email_account import EmailAccount
            from app.models.lead import Lead
            from app.models.startup import Startup

            accounts = (
                db.query(EmailAccount)
                .filter(EmailAccount.user_id == user.id, EmailAccount.is_active.is_(True))
                .all()
            )
            followups = (
                db.query(Lead)
                .join(Startup, Lead.startup_id == Startup.id)
                .filter(
                    Startup.user_id == user.id,
                    Lead.next_follow_up.isnot(None),
                    Lead.next_follow_up <= now,
                )
                .order_by(Lead.next_follow_up.asc())
                .limit(10)
                .all()
            )
            shared.update(
                {
                    "email_accounts": [
                        {
                            "alias": account.alias,
                            "email_address": account.email_address,
                            "provider": account.provider,
                        }
                        for account in accounts
                    ],
                    "leads_needing_follow_up": [
                        {
                            "id": lead.id,
                            "name": lead.name,
                            "company": lead.company,
                            "status": lead.status,
                            "next_follow_up": lead.next_follow_up.isoformat()
                            if lead.next_follow_up
                            else None,
                        }
                        for lead in followups
                    ],
                }
            )

        if context:
            for key in ("force_agent", "conversation_id"):
                if key in context:
                    shared[key] = context[key]
        return shared

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

        sliced_context = self.slice_context_for_domain(db, user, domain, context)
        return await agent.execute(
            db=db, user=user, instruction=instruction, context=sliced_context
        )

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
