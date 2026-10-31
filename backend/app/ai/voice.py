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
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("iris.ai.voice")

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta"

SUPPORTED_VOICE_LANGUAGES = ("en-IN", "en-US", "en-GB")


def normalise_voice_language(raw: str | None) -> str:
    """Spoken replies default to English (India) and never silently become Spanish."""
    tag = (raw or "").strip().replace("_", "-")
    for candidate in SUPPORTED_VOICE_LANGUAGES:
        if tag.lower() == candidate.lower():
            return candidate
    return "en-IN"


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


class GroqSpeechToText(OpenAICompatibleSpeechToText):
    provider = "groq"

    def __init__(self, api_key: str, model: str = "whisper-large-v3-turbo") -> None:
        super().__init__(
            model=model,
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key,
        )


class ResilientSpeechToText(SpeechToText):
    provider = "resilient_fast"

    def __init__(self, primary: SpeechToText, fallback: SpeechToText | None = None) -> None:
        self.primary = primary
        self.fallback = fallback
        self.provider = primary.provider
        self.model = primary.model

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        try:
            return await self.primary.transcribe(audio, mime_type)
        except Exception as exc:
            if self.fallback:
                logger.warning(
                    "Primary STT (%s) failed: %s; falling back to %s",
                    self.primary.provider,
                    exc,
                    self.fallback.provider,
                )
                return await self.fallback.transcribe(audio, mime_type)
            raise


# --- Text-to-speech ---------------------------------------------------------------


class TextToSpeech:
    provider: str
    model: str
    #: Sample rate of :meth:`stream`'s raw 16-bit mono PCM, or None if unsupported.
    stream_rate: int | None = None

    async def synthesize(self, text: str) -> SpeechAudio:
        raise NotImplementedError

    def stream(self, text: str) -> AsyncIterator[bytes]:
        """Raw 16-bit little-endian mono PCM at ``stream_rate``, as it is generated."""
        raise NotImplementedError


class GeminiTextToSpeech(TextToSpeech):
    provider = "gemini"
    stream_rate = 24000

    def __init__(self, model: str, voice: str, api_key: str, language: str | None = None) -> None:
        # "a,b": try b when a is rate-limited (free tiers have small per-minute quotas).
        self.models = [m.strip() for m in model.split(",") if m.strip()]
        self.model = self.models[0]
        self.voice = voice
        self.language = normalise_voice_language(language or settings.ai_voice_language)
        self._key = api_key

    @staticmethod
    def _is_live_model(model: str) -> bool:
        return "live" in model.lower()

    async def synthesize(self, text: str) -> SpeechAudio:
        for i, model in enumerate(self.models):
            try:
                return await self._synthesize(model, text)
            except VoiceError as exc:
                if not exc.rate_limited or i == len(self.models) - 1:
                    raise
                logger.info("TTS model %s is rate-limited; trying %s", model, self.models[i + 1])
        raise VoiceError("No TTS model configured.")

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        for i, model in enumerate(self.models):
            started = False
            try:
                async for chunk in self._stream(model, text):
                    started = True
                    yield chunk
                return
            except VoiceError as exc:
                # Once audio has gone out, switching voices mid-sentence is worse than stopping.
                if started or not exc.rate_limited or i == len(self.models) - 1:
                    raise
                logger.info("TTS model %s is rate-limited; trying %s", model, self.models[i + 1])

    async def _stream(self, model: str, text: str) -> AsyncIterator[bytes]:
        if self._is_live_model(model):
            async for chunk in self._stream_live(model, text):
                yield chunk
            return
        async for chunk in self._stream_rest(model, text):
            yield chunk

    async def _stream_live(self, model: str, text: str) -> AsyncIterator[bytes]:
        try:
            from google.genai import types

            client = get_genai_client()
            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    language_code=self.language,
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice)
                    ),
                ),
            )
            prompt = (
                "Read the following text aloud in English with natural conversational intonation. "
                "Do not translate it, do not answer in Spanish, and do not add any preamble or "
                "commentary. Speak only the text:\n\n"
                f"{text}"
            )
            async with client.aio.live.connect(model=model, config=config) as session:
                await session.send_client_content(
                    turns=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
                    turn_complete=True,
                )
                async for response in session.receive():
                    sc = response.server_content
                    if sc and sc.model_turn:
                        for part in sc.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                yield part.inline_data.data
                    if sc and sc.turn_complete:
                        break
        except Exception as exc:
            rate_limited = "429" in str(exc) or "quota" in str(exc).lower()
            logger.warning("Gemini Live TTS streaming failed (model=%s): %s", model, exc)
            raise VoiceError(f"Speech synthesis failed with live model {model}: {exc}", rate_limited=rate_limited) from exc

    async def _stream_rest(self, model: str, text: str) -> AsyncIterator[bytes]:
        try:
            async with httpx.AsyncClient(timeout=settings.ai_voice_timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{GEMINI_API_URL}/models/{model}:streamGenerateContent?alt=sse",
                    headers={"x-goog-api-key": self._key},
                    json=self._request(text),
                ) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        _raise_for(response, "Speech synthesis")
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        event = json.loads(line[5:])
                        for part in (event.get("candidates") or [{}])[0].get("content", {}).get("parts", []):
                            inline = part.get("inlineData")
                            if inline and inline.get("data"):
                                yield base64.b64decode(inline["data"])
        except httpx.HTTPError as exc:
            raise VoiceError(f"Speech synthesis is unreachable: {type(exc).__name__}") from exc

    def _request(self, text: str) -> dict:
        return {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "languageCode": self.language,
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": self.voice}},
                },
            },
        }

    async def _synthesize(self, model: str, text: str) -> SpeechAudio:
        if self._is_live_model(model):
            return await self._synthesize_live(model, text)
        return await self._synthesize_rest(model, text)

    async def _synthesize_live(self, model: str, text: str) -> SpeechAudio:
        chunks = []
        async for chunk in self._stream_live(model, text):
            chunks.append(chunk)
        if not chunks:
            raise VoiceError(f"Speech synthesis returned no audio from live model {model}.")
        pcm = b"".join(chunks)
        wav = _pcm_to_wav(pcm, self.stream_rate)
        return SpeechAudio(data=wav, mime_type="audio/wav")

    async def _synthesize_rest(self, model: str, text: str) -> SpeechAudio:
        response = await _post(
            "Speech synthesis",
            f"{GEMINI_API_URL}/models/{model}:generateContent",
            headers={"x-goog-api-key": self._key},
            json=self._request(text),
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
    """The configured speech-to-text provider, or None when disabled/unconfigured.

    Prefers ultra-fast Groq Whisper LPU (~80-120ms) when configured, with automatic
    resilient fallback to Gemini transcribe.
    """
    name = (settings.ai_stt_provider or "none").lower()
    gemini_stt = GeminiSpeechToText("gemini-3.5-transcribe", _gemini_key()) if _gemini_key() else None

    if name == "groq" and settings.groq_api_key:
        groq_model = (
            settings.ai_stt_model
            if settings.ai_stt_model and "whisper" in settings.ai_stt_model.lower()
            else "whisper-large-v3-turbo"
        )
        return ResilientSpeechToText(
            primary=GroqSpeechToText(api_key=settings.groq_api_key, model=groq_model),
            fallback=gemini_stt,
        )

    if name == "gemini" and gemini_stt:
        return gemini_stt

    if name == "openai_compatible" and settings.ai_voice_base_url:
        return OpenAICompatibleSpeechToText(
            settings.ai_stt_model, settings.ai_voice_base_url, settings.ai_voice_api_key
        )

    # Auto fallback if groq key is available
    if settings.groq_api_key and name in {"auto", "default", ""}:
        return ResilientSpeechToText(
            primary=GroqSpeechToText(api_key=settings.groq_api_key, model="whisper-large-v3-turbo"),
            fallback=gemini_stt,
        )

    return gemini_stt


def get_text_to_speech() -> TextToSpeech | None:
    """The configured text-to-speech provider, or None when disabled/unconfigured."""
    name = (settings.ai_tts_provider or "none").lower()
    if name == "gemini" and _gemini_key():
        return GeminiTextToSpeech(
            settings.ai_tts_model,
            settings.ai_tts_voice,
            _gemini_key(),
            settings.ai_voice_language,
        )
    if name == "openai_compatible" and settings.ai_voice_base_url:
        return OpenAICompatibleTextToSpeech(
            settings.ai_tts_model, settings.ai_tts_voice, settings.ai_voice_base_url, settings.ai_voice_api_key
        )
    return None


def is_live_enabled() -> bool:
    """Whether Gemini Live conversational model is enabled."""
    return bool(_gemini_key() and getattr(settings, "ai_live_enabled", True))


def get_genai_client():
    """Returns an authenticated google.genai.Client instance."""
    key = _gemini_key()
    if not key:
        raise VoiceError("Gemini API key is not configured.")
    from google import genai

    return genai.Client(api_key=key)
