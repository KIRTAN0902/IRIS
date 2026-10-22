"""Antigravity terminal bridge API.

Transport only: the persistent PTY sessions, completion detection and git
harvesting all live in ``app.services.agy_bridge``.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.core.logging import get_logger
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


@router.get("/sessions")
def list_sessions() -> dict[str, Any]:
    return {
        "current_session_key": agy_manager.current_session_key,
        "sessions": agy_manager.list_sessions(),
        "workspaces": agy_manager.list_workspaces(),
    }


@router.get("/workspaces")
def list_workspaces() -> dict[str, Any]:
    return {"workspaces": agy_manager.list_workspaces()}


@router.post("/attach")
def attach(payload: AttachRequest) -> dict[str, Any]:
    try:
        session = agy_manager.spawn_or_attach(payload.directory, payload.alias)
    except AgyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "session": session.to_dict(),
        "recent_output": session.recent(120),
    }


@router.post("/input")
def send_input(payload: InputRequest) -> dict[str, Any]:
    try:
        if payload.input.strip().startswith("/"):
            result = agy_manager.send_raw_input(payload.session_key, payload.input)
        else:
            result = agy_manager.send_prompt(payload.session_key, payload.input)
    except AgyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/slash")
def send_slash(payload: SlashRequest) -> dict[str, Any]:
    command = payload.command.strip()
    if not command.startswith("/"):
        command = f"/{command}"
    try:
        return agy_manager.send_raw_input(payload.session_key, command)
    except AgyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/session/{session_key}")
def session_status(session_key: str, lines: int = 120) -> dict[str, Any]:
    session = _session_or_404(session_key)
    return {
        "session": session.to_dict(),
        "recent_output": session.recent(lines),
        "last_diff": session.last_diff[:12000],
        "last_diff_stat": session.last_diff_stat,
    }


@router.delete("/session/{session_key}")
def close_session(session_key: str) -> dict[str, Any]:
    session = _session_or_404(session_key)
    agy_manager.close_session(session.key)
    return {"closed": session.key}


@router.websocket("/stream/{session_key}")
async def stream_session(websocket: WebSocket, session_key: str) -> None:
    session = agy_manager.find_session(session_key)
    if session is None:
        await websocket.close(code=4404)
        return
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
