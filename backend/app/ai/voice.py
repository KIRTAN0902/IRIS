"""Voice I/O: speech-to-text and text-to-speech behind swappable providers.

Like the chat models, voice is configuration only (``AI_STT_*`` / ``AI_TTS_*``):

- ``gemini``: Gemini's transcribe and TTS models over the native REST API.
- ``openai_compatible``: any ``/audio/transcriptions`` + ``/audio/speech`` API
  (Groq, OpenAI, a local Whisper server, ...) via ``AI_VOICE_BASE_URL``.
- ``none``: disabled; the app falls back to the phone's own speech engines.

Failures raise :class:`VoiceError` so the API can tell the client to fall back.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("iris.ai.voice")

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta"


class VoiceError(Exception):
    """A voice provider failed; ``rate_limited`` means try again later."""

    def __init__(self, message: str, *, rate_limited: bool = False) -> None:
        super().__init__(message)
        self.rate_limited = rate_limited


@dataclass(frozen=True)
class SpeechAudio:
    data: bytes
    mime_type: str


def _raise_for(response: httpx.Response, what: str) -> None:
    if response.status_code < 400:
        return
    detail = response.text[:300]
    logger.warning("%s failed: HTTP %s %s", what, response.status_code, detail)
    raise VoiceError(
        f"{what} failed (HTTP {response.status_code}).",
        rate_limited=response.status_code == 429,
    )


async def _post(what: str, url: str, **kwargs) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=settings.ai_voice_timeout_seconds) as client:
            response = await client.post(url, **kwargs)
    except httpx.HTTPError as exc:
        raise VoiceError(f"{what} is unreachable: {type(exc).__name__}") from exc
    _raise_for(response, what)
    return response


# --- Speech-to-text --------------------------------------------------------------


class SpeechToText:
    provider: str
    model: str

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        raise NotImplementedError


class GeminiSpeechToText(SpeechToText):
    provider = "gemini"

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self._key = api_key

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        response = await _post(
            "Speech recognition",
            f"{GEMINI_API_URL}/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self._key},
            json={
                "contents": [
                    {"parts": [{"inlineData": {"mimeType": mime_type, "data": base64.b64encode(audio).decode()}}]}
                ]
            },
        )
        parts = (response.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        # Transcribe models answer in `audioTranscription`; general models in `text`.
        return " ".join(
            (p.get("audioTranscription") or {}).get("text") or p.get("text") or "" for p in parts
        ).strip()


class OpenAICompatibleSpeechToText(SpeechToText):
    provider = "openai_compatible"

    def __init__(self, model: str, base_url: str, api_key: str | None) -> None:
        self.model = model
        self._url = base_url.rstrip("/")
        self._key = api_key

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        ext = mime_type.split("/")[-1].split(";")[0] or "webm"
        response = await _post(
            "Speech recognition",
            f"{self._url}/audio/transcriptions",
            headers={"Authorization": f"Bearer {self._key}"} if self._key else {},
            files={"file": (f"speech.{ext}", audio, mime_type)},
            data={"model": self.model},
        )
        return (response.json().get("text") or "").strip()


# --- Text-to-speech ---------------------------------------------------------------


class TextToSpeech:
    provider: str
    model: str

    async def synthesize(self, text: str) -> SpeechAudio:
        raise NotImplementedError


class GeminiTextToSpeech(TextToSpeech):
    provider = "gemini"

    def __init__(self, model: str, voice: str, api_key: str) -> None:
        self.model = model
        self.voice = voice
        self._key = api_key

    async def synthesize(self, text: str) -> SpeechAudio:
        response = await _post(
            "Speech synthesis",
            f"{GEMINI_API_URL}/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self._key},
            json={
                "contents": [{"parts": [{"text": text}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": self.voice}}},
                },
            },
        )
        for part in (response.json().get("candidates") or [{}])[0].get("content", {}).get("parts", []):
            inline = part.get("inlineData")
            if inline and inline.get("data"):
                data = base64.b64decode(inline["data"])
                mime = inline.get("mimeType") or "audio/wav"
                # Some models return raw 16-bit PCM; wrap it so browsers can play it.
                if mime.startswith("audio/l16") or "pcm" in mime:
                    data, mime = _pcm_to_wav(data, _rate_from_mime(mime)), "audio/wav"
                return SpeechAudio(data=data, mime_type=mime)
        raise VoiceError("Speech synthesis returned no audio.")


class OpenAICompatibleTextToSpeech(TextToSpeech):
    provider = "openai_compatible"

    def __init__(self, model: str, voice: str, base_url: str, api_key: str | None) -> None:
        self.model = model
        self.voice = voice
        self._url = base_url.rstrip("/")
        self._key = api_key

    async def synthesize(self, text: str) -> SpeechAudio:
        response = await _post(
            "Speech synthesis",
            f"{self._url}/audio/speech",
            headers={"Authorization": f"Bearer {self._key}"} if self._key else {},
            json={"model": self.model, "voice": self.voice, "input": text, "response_format": "mp3"},
        )
        return SpeechAudio(data=response.content, mime_type="audio/mpeg")


def _rate_from_mime(mime: str) -> int:
    for piece in mime.split(";"):
        key, _, value = piece.strip().partition("=")
        if key == "rate" and value.isdigit():
            return int(value)
    return 24000


def _pcm_to_wav(pcm: bytes, rate: int) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buf.getvalue()


# --- Factory ----------------------------------------------------------------------


def _gemini_key() -> str | None:
    return settings.ai_voice_api_key or settings.gemini_api_key or None


def get_speech_to_text() -> SpeechToText | None:
    """The configured speech-to-text provider, or None when disabled/unconfigured."""
    name = (settings.ai_stt_provider or "none").lower()
    if name == "gemini" and _gemini_key():
        return GeminiSpeechToText(settings.ai_stt_model, _gemini_key())
    if name == "openai_compatible" and settings.ai_voice_base_url:
        return OpenAICompatibleSpeechToText(
            settings.ai_stt_model, settings.ai_voice_base_url, settings.ai_voice_api_key
        )
    return None


def get_text_to_speech() -> TextToSpeech | None:
    """The configured text-to-speech provider, or None when disabled/unconfigured."""
    name = (settings.ai_tts_provider or "none").lower()
    if name == "gemini" and _gemini_key():
        return GeminiTextToSpeech(settings.ai_tts_model, settings.ai_tts_voice, _gemini_key())
    if name == "openai_compatible" and settings.ai_voice_base_url:
        return OpenAICompatibleTextToSpeech(
            settings.ai_tts_model, settings.ai_tts_voice, settings.ai_voice_base_url, settings.ai_voice_api_key
        )
    return None
