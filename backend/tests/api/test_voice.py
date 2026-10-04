"""Voice endpoints and providers (all network calls are faked)."""

from __future__ import annotations

import base64

import httpx
import pytest

from app.ai import voice


class FakeSTT(voice.SpeechToText):
    provider, model = "fake", "fake-stt"

    def __init__(self, text: str = "", error: voice.VoiceError | None = None) -> None:
        self.text, self.error, self.calls = text, error, []

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        self.calls.append((audio, mime_type))
        if self.error:
            raise self.error
        return self.text


class FakeTTS(voice.TextToSpeech):
    provider, model = "fake", "fake-tts"

    def __init__(self, error: voice.VoiceError | None = None) -> None:
        self.error, self.calls = error, []

    async def synthesize(self, text: str) -> voice.SpeechAudio:
        self.calls.append(text)
        if self.error:
            raise self.error
        return voice.SpeechAudio(data=b"RIFFfake", mime_type="audio/wav")


def test_status_reports_disabled_without_keys(client):
    body = client.get("/api/voice/status").json()
    assert body["stt"]["enabled"] is False and body["tts"]["enabled"] is False


def test_transcribe_returns_text(client, monkeypatch):
    stt = FakeSTT("kal subah 10 baje meeting add karo")
    monkeypatch.setattr(voice, "get_speech_to_text", lambda: stt)
    r = client.post("/api/voice/transcribe", content=b"\x1a\x45audio", headers={"Content-Type": "audio/webm;codecs=opus"})
    assert r.status_code == 200
    assert r.json() == {"text": "kal subah 10 baje meeting add karo"}
    assert stt.calls == [(b"\x1a\x45audio", "audio/webm")]


@pytest.mark.parametrize(
    ("content", "content_type"),
    [(b"", "audio/webm"), (b"abc", "application/json")],
)
def test_transcribe_rejects_bad_input(client, monkeypatch, content, content_type):
    monkeypatch.setattr(voice, "get_speech_to_text", lambda: FakeSTT("x"))
    r = client.post("/api/voice/transcribe", content=content, headers={"Content-Type": content_type})
    assert r.status_code == 400


def test_transcribe_rejects_oversized_audio(client, monkeypatch):
    monkeypatch.setattr(voice, "get_speech_to_text", lambda: FakeSTT("x"))
    from app.api.routes.voice import MAX_AUDIO_BYTES

    r = client.post("/api/voice/transcribe", content=b"0" * (MAX_AUDIO_BYTES + 1), headers={"Content-Type": "audio/webm"})
    assert r.status_code == 400


def test_transcribe_unconfigured_is_503(client):
    r = client.post("/api/voice/transcribe", content=b"abc", headers={"Content-Type": "audio/webm"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "VOICE_UNAVAILABLE"


def test_provider_rate_limit_is_429(client, monkeypatch):
    monkeypatch.setattr(
        voice, "get_speech_to_text", lambda: FakeSTT(error=voice.VoiceError("quota", rate_limited=True))
    )
    r = client.post("/api/voice/transcribe", content=b"abc", headers={"Content-Type": "audio/webm"})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "VOICE_RATE_LIMITED"


def test_speak_returns_audio(client, monkeypatch):
    tts = FakeTTS()
    monkeypatch.setattr(voice, "get_text_to_speech", lambda: tts)
    r = client.post("/api/voice/speak", json={"text": "  Done, added it.  "})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content == b"RIFFfake"
    assert tts.calls == ["Done, added it."]


def test_speak_provider_failure_is_503(client, monkeypatch):
    monkeypatch.setattr(voice, "get_text_to_speech", lambda: FakeTTS(error=voice.VoiceError("down")))
    assert client.post("/api/voice/speak", json={"text": "hi"}).status_code == 503


def test_factory_uses_gemini_key_and_config(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(settings, "ai_stt_provider", "gemini")
    monkeypatch.setattr(settings, "ai_tts_model", "some-tts")
    monkeypatch.setattr(settings, "ai_tts_voice", "Puck")
    stt, tts = voice.get_speech_to_text(), voice.get_text_to_speech()
    assert isinstance(stt, voice.GeminiSpeechToText) and stt.model == settings.ai_stt_model
    assert isinstance(tts, voice.GeminiTextToSpeech) and (tts.model, tts.voice) == ("some-tts", "Puck")
    assert tts.models == ["some-tts"]

    monkeypatch.setattr(settings, "ai_stt_provider", "openai_compatible")
    monkeypatch.setattr(settings, "ai_voice_base_url", "https://api.groq.com/openai/v1")
    assert isinstance(voice.get_speech_to_text(), voice.OpenAICompatibleSpeechToText)

    monkeypatch.setattr(settings, "ai_tts_provider", "none")
    assert voice.get_text_to_speech() is None


def _fake_post(payload: dict, captured: list):
    async def post(what, url, **kwargs):
        captured.append((url, kwargs))
        return httpx.Response(200, json=payload)

    return post


async def test_gemini_transcribe_reads_audio_transcription(monkeypatch):
    captured: list = []
    payload = {"candidates": [{"content": {"parts": [{"audioTranscription": {"text": "Maine task add kar diya."}}]}}]}
    monkeypatch.setattr(voice, "_post", _fake_post(payload, captured))
    text = await voice.GeminiSpeechToText("gemini-3.5-transcribe", "k").transcribe(b"abc", "audio/webm")
    assert text == "Maine task add kar diya."
    url, kwargs = captured[0]
    assert url.endswith("/models/gemini-3.5-transcribe:generateContent")
    inline = kwargs["json"]["contents"][0]["parts"][0]["inlineData"]
    assert inline == {"mimeType": "audio/webm", "data": base64.b64encode(b"abc").decode()}


async def test_gemini_tts_wraps_raw_pcm_as_wav(monkeypatch):
    pcm = b"\x00\x00" * 240
    payload = {"candidates": [{"content": {"parts": [{"inlineData": {
        "mimeType": "audio/L16;codec=pcm;rate=24000", "data": base64.b64encode(pcm).decode()}}]}}]}
    monkeypatch.setattr(voice, "_post", _fake_post(payload, []))
    audio = await voice.GeminiTextToSpeech("tts", "Kore", "k").synthesize("hello")
    assert audio.mime_type == "audio/wav"
    assert audio.data[:4] == b"RIFF" and audio.data.endswith(pcm)


def test_chat_passes_voice_flag_to_agent(client, monkeypatch):
    from app.agent.agent import default_agent

    seen = {}

    async def fake_run_turn(**kwargs):
        seen.update(kwargs)
        raise RuntimeError("stop here")

    monkeypatch.setattr(default_agent, "run_turn", fake_run_turn)
    conv = client.post("/api/chat/conversations").json()
    with pytest.raises(RuntimeError, match="stop here"):
        client.post(f"/api/chat/conversations/{conv['id']}/messages", json={"content": "hi", "voice": True})
    assert seen["voice"] is True


async def test_gemini_tts_falls_back_to_next_model_when_rate_limited(monkeypatch):
    tried = []

    async def post(what, url, **kwargs):
        tried.append(url.rsplit("/", 1)[-1])
        if "lite" in url:
            raise voice.VoiceError("quota", rate_limited=True)
        data = base64.b64encode(b"RIFFok").decode()
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [
            {"inlineData": {"mimeType": "audio/wav", "data": data}}]}}]})

    monkeypatch.setattr(voice, "_post", post)
    tts = voice.GeminiTextToSpeech("tts-lite, tts-full", "Kore", "k")
    audio = await tts.synthesize("hi")
    assert audio.data == b"RIFFok"
    assert tried == ["tts-lite:generateContent", "tts-full:generateContent"]


async def test_gemini_tts_other_errors_do_not_fall_back(monkeypatch):
    tried = []

    async def post(what, url, **kwargs):
        tried.append(url)
        raise voice.VoiceError("bad request")

    monkeypatch.setattr(voice, "_post", post)
    with pytest.raises(voice.VoiceError):
        await voice.GeminiTextToSpeech("a,b", "Kore", "k").synthesize("hi")
    assert len(tried) == 1
