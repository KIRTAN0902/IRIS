"""Persist managed Antigravity output independently of UI polling."""
from __future__ import annotations

from datetime import UTC, datetime
import asyncio
import logging

logger=logging.getLogger("iris.coding.persistence")


def persist_headless_sessions() -> None:
    from app.core.database import SessionLocal
    from app.coding.headless import headless_manager
    from app.coding.adapters.codex_adapter import codex_headless_manager
    from app.coding.contracts import TaskStatus, validate_transition
    from app.models.coding_task import CodingSessionRecord, CodingTaskRecord
    from app.coding.git_workspace import collect_worktree_diff, commit_worktree_changes

    sessions = list(headless_manager.list_sessions()) + list(codex_headless_manager.list_sessions())
    if not sessions:
        return
    db = SessionLocal()
    try:
        changed=False
        for live in sessions:
            snapshot=live.snapshot()
            row=db.query(CodingSessionRecord).filter_by(manager_key=live.key).first()
            if row is None:
                continue
            row.output=snapshot.get("recent_output","")
            row.external_session_id=snapshot.get("conversation_id") or row.external_session_id
            row.status={"WAITING_FOR_USER":"waiting_for_user","FAILED":"failed","INTERRUPTED":"interrupted","IDLE":"agent_reported_completion"}.get(snapshot.get("state"),"running")
            result=snapshot.get("last_result") or {}
            if result.get("status") in {"ERROR","FAILED"}:
                row.error=str(result.get("error") or "Antigravity CLI reported an error")[:2000]
            task=db.query(CodingTaskRecord).filter_by(id=row.task_id).first()
            events=snapshot.get("events") or []
            total=int(snapshot.get("event_total",len(events)))
            start=max(0,total-len(events))
            if task is not None:
                if row.event_cursor<start:
                    task.events=list(task.events or [])+[{"type":"event_buffer_overrun","lost_events":start-row.event_cursor,"at":datetime.now(UTC).isoformat()}]
                new_events=events[max(0,row.event_cursor-start):]
                for event in new_events:
                    task.events=list(task.events or [])+[{"type":"agent_event","event":event,"at":datetime.now(UTC).isoformat()}]
                task.events=(task.events or [])[-500:]
                state=snapshot.get("state")
                if state=="WAITING_FOR_USER" and task.status==TaskStatus.RUNNING.value:
                    validate_transition(TaskStatus.RUNNING,TaskStatus.WAITING_FOR_USER)
                    task.status=TaskStatus.WAITING_FOR_USER.value
                    task.events=list(task.events or [])+[{"type":"follow_up_requested","source":"agent_waiting","at":datetime.now(UTC).isoformat()}]
                elif state=="IDLE" and result.get("status")=="SUCCESS" and task.status==TaskStatus.RUNNING.value:
                    validate_transition(TaskStatus.RUNNING,TaskStatus.COMPLETED)
                    task.status=TaskStatus.COMPLETED.value; task.ended_at=datetime.now(UTC)
                    commands=[]; changed_files=[]
                    for event in events:
                        step=event.get("step_update",{})
                        if step.get("step_type")=="tool" and step.get("tool_name")=="run_command":
                            info=step.get("tool_info") or {}; commands.append({"command":(info.get("parameters") or {}).get("CommandLine"),"output":info.get("output"),"error":info.get("error")})
                        elif step.get("step_type")=="tool" and step.get("state")=="DONE" and step.get("tool_name") in {"write_file","write_to_file","replace_file_content","multi_replace_file_content","notebook_edit"}:
                            params=(step.get("tool_info") or {}).get("parameters") or {}
                            path=next((params.get(k) for k in ("Path","path","FilePath","file_path","notebook_path") if params.get(k)),None)
                            if path and path not in changed_files: changed_files.append(path)

                    worktree_dir = (task.brief or {}).get("worktree_path")
                    base_commit = (task.brief or {}).get("base_commit")
                    diff_info = {}
                    new_commit = None
                    if worktree_dir and base_commit:
                        try:
                            new_commit = commit_worktree_changes(worktree_dir, f"IRIS Task: {task.instruction[:80]}")
                            diff_info = collect_worktree_diff(worktree_dir, base_commit)
                            for f in diff_info.get("changed_files", []):
                                if f.get("path") and f["path"] not in changed_files:
                                    changed_files.append(f["path"])
                        except Exception as exc:
                            diff_info = {"error": str(exc)}

                    task.result={"agent_reported":True,"status":result.get("status"),"summary":result.get("response",""),"changed_files_reported_by_tools":changed_files,"commands_executed":commands,
                                 "worktree_path":worktree_dir,"branch_name":(task.brief or {}).get("task_branch"),"base_commit":base_commit,"task_commit":new_commit,
                                 "diff_stat":diff_info.get("stat",""),"diff_summary":diff_info.get("diff","")[:20000],"changed_files":diff_info.get("changed_files",[])}
                    task.verification={"independently_verified":False,"tests_observed":[c["command"] for c in commands if c.get("command") and any(x in c["command"].lower() for x in ("pytest","npm test","vitest","jest","cargo test"))],"test_results":"Not independently verified; inspect captured command output.","note":"A successful agent turn does not itself establish tests passed.","git_verified":bool(new_commit)}
                    task.events=list(task.events or [])+[{"type":"completion_reported","at":datetime.now(UTC).isoformat()}]
                elif state=="FAILED" and task.status in {TaskStatus.RUNNING.value,TaskStatus.WAITING_FOR_USER.value}:
                    validate_transition(TaskStatus(task.status),TaskStatus.FAILED)
                    task.status=TaskStatus.FAILED.value; task.ended_at=datetime.now(UTC)
                    task.result={"agent_reported":False,"error":result.get("error","Antigravity CLI failed")}
                    task.events=list(task.events or [])+[{"type":"execution_failed","at":datetime.now(UTC).isoformat()}]
            row.event_cursor=total
            changed=True
        if changed:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def persist_headless_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(persist_headless_sessions)
        except Exception:
            logger.exception("Could not persist Antigravity session snapshots")
        await asyncio.sleep(1.0)
