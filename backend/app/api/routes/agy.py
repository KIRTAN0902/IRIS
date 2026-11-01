"""Antigravity terminal bridge API.

Transport only: the persistent PTY sessions, completion detection and git
harvesting all live in ``app.services.agy_bridge``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.api.deps import current_user
from app.core.database import get_db
from app.models.coding_project import CodingProject
from app.models.user import User
from app.core.execution_provider import is_serverless_runtime, require_execution
from app.services.agy_bridge import AgyError, agy_manager

logger = get_logger("iris.api.agy")

router = APIRouter(prefix="/agy", tags=["agy"])


class AttachRequest(BaseModel):
    directory: str | None = None
    alias: str | None = None


class InputRequest(BaseModel):
    session_key: str | None = None
    input: str = Field(min_length=1)


class SlashRequest(BaseModel):
    session_key: str | None = None
    command: str = Field(min_length=1)


def _session_or_404(key: str | None):
    session = agy_manager.find_session(key)
    if session is None:
        raise HTTPException(status_code=404, detail=f"No active Antigravity session: {key}")
    return session

def _workspace_permission(db: Session, user: User, directory: str, *, write: bool = False, command: bool = False) -> CodingProject:
    projects=db.query(CodingProject).filter_by(user_id=user.id,active=True).all()
    norm=directory.strip().casefold()
    for project in projects:
        path_match=str(Path(project.directory).resolve()).casefold()==str(Path(directory).resolve()).casefold() if Path(directory).is_absolute() else False
        alias_match=norm==project.name.casefold() or norm in [a.casefold() for a in (project.aliases or [])]
        if path_match or alias_match:
            if not project.read_access or (write and not project.write_access) or (command and not project.command_access):
                raise HTTPException(403,"Workspace permission is not granted for this action")
            return project
    raise HTTPException(403,"Antigravity sessions require a registered project workspace")

def _authorized_session(db: Session, user: User, key: str | None, *, write: bool = False, command: bool = False):
    session=_session_or_404(key)
    _workspace_permission(db,user,session.directory,write=write,command=command)
    return session


@router.get("/sessions")
def list_sessions(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    require_execution("coding_agent")
    owned={str(Path(p.directory).resolve()).casefold() for p in db.query(CodingProject).filter_by(user_id=user.id,active=True).all()}
    sessions=[s for s in agy_manager.list_sessions() if str(Path(s["directory"]).resolve()).casefold() in owned]
    return {
        "current_session_key": agy_manager.current_session_key if any(s["key"]==agy_manager.current_session_key for s in sessions) else None,
        "sessions": sessions,
        "workspaces": [{"alias":(p.aliases or [p.name.lower()])[0],"path":p.directory,"exists":Path(p.directory).is_dir(),"is_git":(Path(p.directory)/".git").exists(),"source":"registry"} for p in db.query(CodingProject).filter_by(user_id=user.id,active=True).all()],
    }


@router.get("/workspaces")
def list_workspaces(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    require_execution("coding_agent")
    return {"workspaces":[{"alias":(p.aliases or [p.name.lower()])[0],"path":p.directory,"exists":Path(p.directory).is_dir(),"is_git":(Path(p.directory)/".git").exists(),"source":"registry"} for p in db.query(CodingProject).filter_by(user_id=user.id,active=True).all()]}


@router.post("/attach")
def attach(payload: AttachRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    require_execution("coding_agent")
    try:
        _workspace_permission(db,user,payload.directory or payload.alias or "",write=True,command=True)
        session = agy_manager.spawn_or_attach(payload.directory, payload.alias, governed=True)
    except AgyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "session": session.to_dict(),
        "recent_output": session.recent(120),
    }


@router.post("/input")
def send_input(payload: InputRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    require_execution("coding_agent")
    try:
        session=_authorized_session(db,user,payload.session_key,write=True,command=True)
        if payload.input.strip().startswith("/"):
            result = agy_manager.send_raw_input(session.key, payload.input)
        else:
            result = agy_manager.send_prompt(session.key, payload.input)
    except AgyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/slash")
def send_slash(payload: SlashRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    require_execution("coding_agent")
    command = payload.command.strip()
    if not command.startswith("/"):
        command = f"/{command}"
    try:
        session=_authorized_session(db,user,payload.session_key,write=True,command=True)
        return agy_manager.send_raw_input(session.key, command)
    except AgyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/session/{session_key}")
def session_status(session_key: str, lines: int = 120, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    require_execution("coding_agent")
    session = _authorized_session(db,user,session_key)
    return {
        "session": session.to_dict(),
        "recent_output": session.recent(lines),
        "last_diff": session.last_diff[:12000],
        "last_diff_stat": session.last_diff_stat,
    }


@router.delete("/session/{session_key}")
def close_session(session_key: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    require_execution("coding_agent")
    session = _authorized_session(db,user,session_key,write=True,command=True)
    agy_manager.close_session(session.key)
    return {"closed": session.key}


@router.websocket("/stream/{session_key}")
async def stream_session(websocket: WebSocket, session_key: str) -> None:
    if is_serverless_runtime():
        await websocket.close(code=1013, reason="Open a persistent IRIS execution host for Agy sessions.")
        return
    session = agy_manager.find_session(session_key)
    if session is None:
        await websocket.close(code=4404)
        return
    from app.core.database import SessionLocal
    from app.core.security import get_current_user
    db=SessionLocal()
    try:
        user=get_current_user(db)
        _workspace_permission(db,user,session.directory)
    except HTTPException:
        await websocket.close(code=4403)
        return
    finally:
        db.close()
    await websocket.accept()
    await websocket.send_json(
        {
            "type": "session",
            "session": session.to_dict(),
            "backlog": session.recent(120),
        }
    )
    stop = asyncio.Event()

    async def sender() -> None:
        try:
            async for chunk in agy_manager.stream_output(session.key, backlog_lines=0):
                if stop.is_set():
                    return
                if chunk:
                    await websocket.send_json({"type": "output", "data": chunk})
                else:
                    await websocket.send_json({"type": "ping"})
        except Exception:
            logger.debug("agy websocket sender closed", exc_info=True)

    async def receiver() -> None:
        try:
            while True:
                data = await websocket.receive_json()
                kind = str(data.get("type", "input"))
                text = str(data.get("data", data.get("input", ""))).strip()
                if not text:
                    continue
                if kind == "slash" or text.startswith("/"):
                    agy_manager.send_raw_input(session.key, text)
                else:
                    agy_manager.send_prompt(session.key, text)
                await websocket.send_json({"type": "ack", "state": session.state})
        except (WebSocketDisconnect, RuntimeError):
            pass
        except Exception:
            logger.debug("agy websocket receiver closed", exc_info=True)
        finally:
            stop.set()

    sender_task = asyncio.create_task(sender())
    receiver_task = asyncio.create_task(receiver())
    try:
        done, pending = await asyncio.wait(
            {sender_task, receiver_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            if not task.cancelled():
                task.exception()
    finally:
        stop.set()
        sender_task.cancel()
        receiver_task.cancel()
        await asyncio.gather(sender_task, receiver_task, return_exceptions=True)
