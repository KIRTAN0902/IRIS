"""Voice endpoints: transcribe the user's speech and speak IRIS's replies.

The phone records audio and posts it raw; replies come back as audio bytes.
A 429/503 here tells the client to fall back to the phone's own speech engines.
"""

from __future__ import annotations

import asyncio
import base64

from fastapi import APIRouter, Depends, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.ai import voice
from app.api.deps import current_user
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.user import User

logger = get_logger("iris.api.voice")

router = APIRouter(prefix="/voice", tags=["Voice"])

# Stays under Vercel's 4.5 MB request limit; about 4 minutes of Opus audio.
MAX_AUDIO_BYTES = 4 * 1024 * 1024


class VoiceUnavailableError(AppError):
    status_code = 503
    code = "VOICE_UNAVAILABLE"


class VoiceRateLimitedError(AppError):
    status_code = 429
    code = "VOICE_RATE_LIMITED"


def _fail(exc: voice.VoiceError) -> AppError:
    return VoiceRateLimitedError(str(exc)) if exc.rate_limited else VoiceUnavailableError(str(exc))


class SpeakIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


@router.get("/status")
def voice_status(_: User = Depends(current_user)) -> dict:
    """Which voice providers are configured (the client falls back when one is off)."""
    stt, tts = voice.get_speech_to_text(), voice.get_text_to_speech()
    return {
        "stt": {"enabled": stt is not None, "provider": stt.provider if stt else None, "model": stt.model if stt else None},
        "tts": {"enabled": tts is not None, "provider": tts.provider if tts else None, "model": tts.model if tts else None},
        "live": {
            "enabled": voice.is_live_enabled(),
            "model": settings.ai_live_model,
            "voice": settings.ai_tts_voice,
        },
    }


@router.post("/transcribe")
async def transcribe(request: Request, _: User = Depends(current_user)) -> dict:
    """Transcribe a recorded clip posted as the raw request body (Content-Type: audio/*)."""
    mime_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not mime_type.startswith("audio/"):
        raise AppError("Send the recording as the request body with an audio/* Content-Type.")
    audio = await request.body()
    if not audio:
        raise AppError("The recording is empty.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise AppError("The recording is too long. Keep it under about 4 minutes.")

    stt = voice.get_speech_to_text()
    if stt is None:
        raise VoiceUnavailableError("Speech recognition is not configured.")
    try:
        text = await stt.transcribe(audio, mime_type)
    except voice.VoiceError as exc:
        raise _fail(exc) from exc
    return {"text": text}


@router.post("/speak")
async def speak(payload: SpeakIn, _: User = Depends(current_user)) -> Response:
    """Turn text into speech; returns the audio bytes."""
    tts = voice.get_text_to_speech()
    if tts is None:
        raise VoiceUnavailableError("Text-to-speech is not configured.")
    try:
        audio = await tts.synthesize(payload.text.strip())
    except voice.VoiceError as exc:
        raise _fail(exc) from exc
    return Response(content=audio.data, media_type=audio.mime_type, headers={"Cache-Control": "no-store"})


@router.post("/speak/stream")
async def speak_stream(payload: SpeakIn, _: User = Depends(current_user)) -> Response:
    """Stream speech as raw 16-bit mono PCM (rate in ``X-Sample-Rate``) while it is generated.

    The first chunk is fetched before responding, so rate limits and outages
    still come back as 429/503 and the client can fall back.
    """
    tts = voice.get_text_to_speech()
    if tts is None:
        raise VoiceUnavailableError("Text-to-speech is not configured.")
    if not tts.stream_rate:
        raise VoiceUnavailableError("This text-to-speech provider does not stream.")
    chunks = tts.stream(payload.text.strip())
    try:
        first = await anext(chunks)
    except StopAsyncIteration as exc:
        raise VoiceUnavailableError("Speech synthesis returned no audio.") from exc
    except voice.VoiceError as exc:
        raise _fail(exc) from exc

    async def body():
        yield first
        try:
            async for chunk in chunks:
                yield chunk
        except voice.VoiceError:
            return  # the client plays what arrived

    return StreamingResponse(
        body(),
        media_type="application/octet-stream",
        headers={"X-Sample-Rate": str(tts.stream_rate), "Cache-Control": "no-store"},
    )


@router.websocket("/live")
async def voice_live_websocket(
    websocket: WebSocket,
):
    """Bidirectional full-duplex conversational audio streaming with Gemini 3.8 Live."""
    await websocket.accept()
    if not voice.is_live_enabled():
        await websocket.send_json({"type": "error", "message": "Gemini Live is not configured or disabled."})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        from google.genai import types

        user_name = "Kirtan"
        situation_text = ""
        pm_text = ""
        try:
            from app.core.database import SessionLocal
            from app.core.security import get_current_user
            from app.intelligence.personal_model import build_personal_model, render_personal_model
            from app.intelligence.situation import build_situation, render_situation

            with SessionLocal() as db:
                user = get_current_user(db)
                if user:
                    user_name = user.name or "Kirtan"
                    sit = build_situation(db, user)
                    situation_text = render_situation(sit, detail="standard")
                    pm = build_personal_model(db, user)
                    pm_text = render_personal_model(pm, detail="standard")
        except Exception as exc:
            logger.warning("Failed to render situation for voice live: %s", exc)

        client = voice.get_genai_client()
        system_instruction = (
            f"You are IRIS, an intelligent, sovereign personal AI companion and desktop workstation orchestrator.\n"
            f"You are conversing directly with {user_name}.\n"
            "Speak with a natural, concise, intelligent, and warm tone suitable for real-time speech.\n"
            "Keep your responses direct, conversational, and grounded in the user's real situation, tasks, and schedule below.\n"
            "When the user asks you to open or launch an application, create a daily task, check today's tasks, complete a task, run a command, check status, or lock the laptop, ALWAYS use your registered tools to execute the action immediately.\n\n"
            f"{pm_text}\n\n"
            f"{situation_text}\n"
        )

        # Real Sovereign IRIS Tools for Gemini Live Audio
        def launch_laptop_app(app_name: str, directory: str = "") -> str:
            """Launch or open an application on the user's Windows laptop workstation (e.g. terminal, agy, vscode, chrome, explorer, or any installed Windows app)."""
            from app.services import mesh_service as ms
            from app.services import mesh_relay_service as mrs

            with SessionLocal() as db_session:
                if mrs.is_local_windows_host():
                    res = ms.launch_windows_app(app_name, directory=directory)
                    return f"Successfully opened {app_name} on your Windows laptop." if res.get("success") else f"Could not open {app_name}: {res.get('error')}"
                else:
                    if not mrs.is_host_laptop_online(db_session, user.id, threshold_seconds=300.0):
                        return "Your Windows laptop is currently offline or unreachable on the IRIS mesh."
                    mrs.push_relay_message(
                        db=db_session,
                        user_id=user.id,
                        sender_device_id="voice_live_agent",
                        target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
                        msg_type="REMOTE_COMMAND",
                        payload={"command": "LAUNCH_APP", "app": app_name, "directory": directory},
                    )
                    return f"Dispatched launch command for {app_name} to your Windows laptop."

        def launch_mobile_app(app_name: str) -> str:
            """Launch or open an application on the user's mobile phone (e.g. whatsapp, camera, spotify, phonepe, gpay, gallery)."""
            from app.services import mesh_relay_service as mrs

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(websocket.send_json({"type": "launch_mobile_app", "app": app_name}))
            except Exception:
                pass

            with SessionLocal() as db_session:
                mrs.push_relay_message(
                    db=db_session,
                    user_id=user.id,
                    sender_device_id="voice_live_agent",
                    target_device_id=None,
                    msg_type="LAUNCH_APP",
                    payload={"app": app_name, "target": "mobile"},
                )
            return f"Opened {app_name} on your mobile phone."

        def execute_terminal_command(command: str) -> str:
            """Run a shell or PowerShell command on the Windows laptop workstation."""
            from app.services import mesh_service as ms
            from app.services import mesh_relay_service as mrs

            with SessionLocal() as db_session:
                if mrs.is_local_windows_host():
                    res = ms.execute_terminal_command(command)
                    out = (res.get("stdout") or res.get("stderr") or "Command completed.").strip()
                    return f"Output: {out[:500]}"
                else:
                    if not mrs.is_host_laptop_online(db_session, user.id, threshold_seconds=300.0):
                        return "Your Windows laptop is currently offline on the IRIS mesh."
                    mrs.push_relay_message(
                        db=db_session,
                        user_id=user.id,
                        sender_device_id="voice_live_agent",
                        target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
                        msg_type="REMOTE_COMMAND",
                        payload={"command": "TERMINAL_EXEC", "command_line": command},
                    )
                    return f"Dispatched command '{command}' to your Windows laptop."

        def get_laptop_status() -> str:
            """Check the status, battery level, and connectivity of the Windows laptop."""
            from app.services import mesh_relay_service as mrs
            with SessionLocal() as db_session:
                info = mrs.get_laptop_host_info(db_session, user.id, threshold_seconds=300.0)
                status = "Online and active on IRIS mesh" if info.get("is_online") else "Offline"
                bat = f"Battery is at {info.get('battery_level')}%" if info.get('battery_level') is not None else ""
                charging = " (charging)" if info.get('is_charging') else ""
                return f"Laptop workstation is {status}. {bat}{charging}."

        def lock_laptop() -> str:
            """Engage the Sovereign Privacy Shield on the Windows laptop display."""
            from app.services import mesh_service as ms
            from app.services import mesh_relay_service as mrs
            with SessionLocal() as db_session:
                if mrs.is_local_windows_host():
                    ms.lock_windows_pc(mode="shield")
                else:
                    mrs.push_relay_message(
                        db=db_session,
                        user_id=user.id,
                        sender_device_id="voice_live_agent",
                        target_device_id=mrs.LAPTOP_HOST_DEVICE_ID,
                        msg_type="REMOTE_COMMAND",
                        payload={"command": "LOCK_PC", "mode": "shield"},
                    )
                return "Sovereign Privacy Shield engaged: Windows laptop display is locked."

        def create_daily_task(title: str, area: str = "PERSONAL", priority: str = "MEDIUM", estimated_minutes: int = 30) -> str:
            """Create a new daily task or action item in IRIS."""
            from app.models.enums import LifeArea, TaskPriority
            from app.schemas.task import TaskCreate
            from app.services import task_service
            with SessionLocal() as db_session:
                area_val = getattr(LifeArea, area.upper(), LifeArea.PERSONAL)
                pri_val = getattr(TaskPriority, priority.upper(), TaskPriority.MEDIUM)
                task_in = TaskCreate(
                    title=title,
                    area=area_val,
                    priority=pri_val,
                    estimated_duration=estimated_minutes,
                )
                t = task_service.create_task(db_session, user.id, task_in)
                return f"Created task #{t.id}: '{t.title}' ({t.area.title()} · {t.priority.title()} priority)."

        def get_today_tasks() -> str:
            """Retrieve the user's tasks for today, including priority and completion status."""
            from app.models.task import Task
            from app.models.enums import TaskStatus
            from app.utils.datetime import localize_date_boundaries, to_local, utcnow
            tz_str = user.timezone or "UTC"
            now_local = to_local(utcnow(), tz_str)
            today_start_utc, today_end_utc = localize_date_boundaries(now_local.date(), tz_str)

            with SessionLocal() as db_session:
                open_tasks = (
                    db_session.query(Task)
                    .filter(Task.user_id == user.id, Task.status.in_([TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]))
                    .order_by(Task.deadline.asc().nullslast(), Task.priority.desc())
                    .all()
                )
                if not open_tasks:
                    return f"You have no open tasks scheduled or due for today, {now_local.strftime('%A')}."
                lines = [f"You have {len(open_tasks)} tasks for today:"]
                for t in open_tasks[:6]:
                    dur = f" ({t.estimated_duration}m)" if t.estimated_duration else ""
                    lines.append(f"- [{t.priority}] {t.title}{dur}")
                return "\n".join(lines)

        def complete_task(task_title_or_id: str) -> str:
            """Mark a task as completed by its title or ID."""
            from app.models.task import Task
            from app.services import task_service
            with SessionLocal() as db_session:
                t = None
                if task_title_or_id.isdigit():
                    t = db_session.query(Task).filter(Task.user_id == user.id, Task.id == int(task_title_or_id)).first()
                if not t:
                    t = (
                        db_session.query(Task)
                        .filter(Task.user_id == user.id, Task.title.ilike(f"%{task_title_or_id}%"))
                        .first()
                    )
                if not t:
                    return f"Could not find a task matching '{task_title_or_id}'."
                task_service.complete_task(db_session, user.id, t.id, None)
                return f"Marked task #{t.id} '{t.title}' as completed."

        tools_list = [
            launch_laptop_app,
            launch_mobile_app,
            execute_terminal_command,
            get_laptop_status,
            lock_laptop,
            create_daily_task,
            get_today_tasks,
            complete_task,
        ]

        live_config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=settings.ai_tts_voice or "Enceladus")
                )
            ),
            system_instruction=types.Content(parts=[types.Part.from_text(text=system_instruction)]),
            tools=tools_list,
        )

        model_name = settings.ai_live_model or "gemini-3.8-live"
        await websocket.send_json({
            "type": "ready",
            "model": model_name,
            "voice": settings.ai_tts_voice or "Enceladus",
            "sample_rate": 24000,
        })

        async with client.aio.live.connect(model=model_name, config=live_config) as session:
            async def client_to_gemini():
                while True:
                    msg = await websocket.receive()
                    if msg.get("type") == "websocket.disconnect":
                        break
                    if "bytes" in msg and msg["bytes"]:
                        # Raw audio PCM chunk from microphone
                        await session.send_realtime_input(
                            audio=types.Blob(data=msg["bytes"], mime_type="audio/pcm;rate=24000")
                        )
                    elif "text" in msg and msg["text"]:
                        import json
                        try:
                            payload = json.loads(msg["text"])
                        except Exception:
                            payload = {"type": "text", "text": msg["text"]}
                        p_type = payload.get("type", "text")
                        if p_type == "audio":
                            raw = base64.b64decode(payload.get("data", ""))
                            rate = payload.get("rate", 24000)
                            await session.send_realtime_input(
                                audio=types.Blob(data=raw, mime_type=f"audio/pcm;rate={rate}")
                            )
                        elif p_type == "text":
                            text = payload.get("text", "").strip()
                            if text:
                                await session.send_client_content(
                                    turns=[types.Content(role="user", parts=[types.Part.from_text(text=text)])],
                                    turn_complete=True,
                                )
                        elif p_type == "end_of_turn":
                            await session.send_client_content(turns=[], turn_complete=True)
                        elif p_type == "interrupt":
                            pass
                        elif p_type == "ping":
                            await websocket.send_json({"type": "pong"})

            async def gemini_to_client():
                async for response in session.receive():
                    if response.tool_call and response.tool_call.function_calls:
                        responses = []
                        for fc in response.tool_call.function_calls:
                            logger.info("Gemini Live tool call received: %s with args: %s", fc.name, fc.args)
                            func_map = {
                                "launch_laptop_app": launch_laptop_app,
                                "launch_mobile_app": launch_mobile_app,
                                "execute_terminal_command": execute_terminal_command,
                                "get_laptop_status": get_laptop_status,
                                "lock_laptop": lock_laptop,
                                "create_daily_task": create_daily_task,
                                "get_today_tasks": get_today_tasks,
                                "complete_task": complete_task,
                            }
                            fn = func_map.get(fc.name)
                            if fn:
                                try:
                                    args = fc.args or {}
                                    res_val = fn(**args)
                                except Exception as err:
                                    logger.exception("Error executing Live tool %s: %s", fc.name, err)
                                    res_val = f"Error executing {fc.name}: {err}"
                            else:
                                res_val = f"Tool {fc.name} is not recognized."
                            responses.append(
                                types.FunctionResponse(
                                    name=fc.name,
                                    id=fc.id,
                                    response={"result": res_val},
                                )
                            )
                        try:
                            await session.send_tool_response(function_responses=responses)
                        except Exception as e:
                            logger.exception("Failed to send tool response to Gemini Live: %s", e)

                    sc = response.server_content
                    if sc and sc.model_turn:
                        for part in sc.model_turn.parts:
                            if getattr(part, 'text', None):
                                await websocket.send_json({'type': 'text', 'text': part.text})
                            if part.inline_data and part.inline_data.data:
                                await websocket.send_bytes(part.inline_data.data)
                    if sc and sc.turn_complete:
                        await websocket.send_json({"type": "turn_complete"})
                    if sc and sc.interrupted:
                        await websocket.send_json({"type": "interrupted"})

            t1 = asyncio.create_task(client_to_gemini())
            t2 = asyncio.create_task(gemini_to_client())
            done, pending = await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
    except WebSocketDisconnect:
        logger.info("Voice live websocket disconnected by client")
    except Exception as exc:
        logger.warning("Voice live websocket error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
