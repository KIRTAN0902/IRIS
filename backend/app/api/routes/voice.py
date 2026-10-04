"""Voice endpoints: transcribe the user's speech and speak IRIS's replies.

The phone records audio and posts it raw; replies come back as audio bytes.
A 429/503 here tells the client to fall back to the phone's own speech engines.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.ai import voice
from app.api.deps import current_user
from app.core.errors import AppError
from app.models.user import User

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
