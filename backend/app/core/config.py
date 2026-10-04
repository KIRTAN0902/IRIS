"""Application configuration.

All runtime configuration is loaded from environment variables (optionally via
a local `.env` file). Nothing here is ever hard-coded elsewhere in the app.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---
    environment: str = "development"
    log_level: str = "INFO"
    default_timezone: str = "Asia/Kolkata"
    api_prefix: str = "/api"

    # --- Database ---
    database_url: str = "sqlite:///./iris.db"

    # --- Security & Network ---
    secret_key: str = "change-me-in-production"
    cors_origins: list[str] = []

    # --- AI ---
    # Which backend serves the model. Any OpenAI-compatible endpoint works:
    # nvidia | openai | openrouter | groq | together | deepseek | mistral |
    # fireworks | anthropic | ollama | lmstudio | vllm | openai_compatible |
    # gemini | mock. See app/ai/factory.py for presets.
    ai_provider: str = "nvidia"
    ai_context_max_tasks: int = 25

    # Provider-neutral model settings. These win over the legacy per-vendor
    # variables below, so switching models is only ever an .env change.
    ai_model: str | None = None
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_timeout_seconds: float | None = None
    ai_temperature: float | None = None
    ai_max_tokens: int | None = None
    # Transport retries on 429/5xx-style transient errors.
    ai_max_retries: int = 2
    # Extra attempts to repair invalid structured (JSON) output.
    ai_structured_retries: int = 1
    # Model calls per agent turn. Past the soft limit the loop continues only while
    # each step makes new, successful progress, up to the hard cap.
    ai_agent_max_steps: int = 8
    ai_agent_max_steps_hard: int = 24
    # JSON overrides for ModelCapabilities, e.g. {"native_tools": false}.
    ai_capabilities: str | None = None
    # JSON merged into every request body, e.g. {"reasoning_effort": "high"}.
    ai_extra_body: str | None = None
    # JSON of extra HTTP headers, e.g. {"HTTP-Referer": "https://iris.local"}.
    ai_extra_headers: str | None = None

    # --- Voice (speech-to-text and text-to-speech) ---
    # gemini | openai_compatible (any /audio/transcriptions + /audio/speech API,
    # e.g. Groq or OpenAI) | none. Gemini reuses GEMINI_API_KEY.
    ai_stt_provider: str = "gemini"
    ai_stt_model: str = "gemini-3.5-transcribe"
    ai_tts_provider: str = "gemini"
    ai_tts_model: str = "gemini-3.8-flash-lite-tts"
    ai_tts_voice: str = "Kore"
    # For openai_compatible voice providers (or to override the Gemini key).
    ai_voice_base_url: str | None = None
    ai_voice_api_key: str | None = None
    ai_voice_timeout_seconds: float = 30.0

    # Legacy per-vendor settings (used when the AI_* equivalents are unset).
    # NVIDIA NIM (OpenAI-compatible API)
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_api_key: str | None = None
    nvidia_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    nvidia_timeout_seconds: float = 45.0

    # Gemini
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: float = 45.0

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

    def json_setting(self, field_name: str) -> dict[str, Any]:
        """Parse a JSON-object setting (blank/invalid -> {})."""
        raw = getattr(self, field_name, None)
        if not raw or not str(raw).strip():
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    @property
    def ai_enabled(self) -> bool:
        """Whether the configured AI provider is usable (delegates to the factory)."""
        from app.ai.factory import get_ai_provider

        try:
            return get_ai_provider().enabled
        except Exception:
            return False


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor; import this instead of constructing Settings."""
    return Settings()


settings = get_settings()
