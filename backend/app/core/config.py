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
    ai_provider: str = "gemini"
    ai_context_max_tasks: int = 25

    # Provider-neutral model settings. These win over the legacy per-vendor
    # variables below, so switching models is only ever an .env change.
    ai_model: str | None = "gemini-3.1-flash-lite"
    ai_fallback_model: str | None = "gemini-3.5-flash-lite"
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_timeout_seconds: float | None = None
    ai_temperature: float | None = None
    ai_max_tokens: int | None = None
    # Transport retries on 429/5xx-style transient errors.
    ai_max_retries: int = 3
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

    # --- Voice & Live Conversational Audio ---
    # groq (ultra-fast Whisper LPU) | gemini | openai_compatible | none.
    ai_stt_provider: str = "groq"
    ai_stt_model: str = "whisper-large-v3-turbo"
    ai_tts_provider: str = "gemini"
    # Comma-separated: later models are tried when an earlier one is rate-limited.
    ai_tts_model: str = "gemini-3.8-live,gemini-3.8-flash-tts,gemini-3.1-flash-tts-preview"
    ai_tts_voice: str = "Puck"
    ai_live_model: str = "gemini-3.8-live"
    ai_live_enabled: bool = True
    # For openai_compatible voice providers (or to override the Gemini key).
    ai_voice_base_url: str | None = None
    ai_voice_api_key: str | None = None
    ai_voice_timeout_seconds: float = 30.0

    # Legacy per-vendor settings (used when the AI_* equivalents are unset).
    # NVIDIA NIM (OpenAI-compatible API)
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_api_key: str | None = None
    nvidia_model: str = "google/gemma-4-31b-it"
    nvidia_timeout_seconds: float = 90.0

    # Gemini
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_fallback_model: str | None = "gemini-3.5-flash-lite"
    gemini_timeout_seconds: float = 45.0

    # Groq Cloud (Ultra-fast LPU inference)
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_api_key: str | None = None
    groq_model: str = "qwen/qwen3.8-27b"
    groq_timeout_seconds: float = 30.0

    # Multi-Agent Routing & System 1 Decision Router (Jev alternative)
    ai_multi_agent_enabled: bool = True
    ai_router_model: str = "groq:qwen/qwen3.8-27b"
    ai_orchestrator_model: str = "gemini:gemini-3.1-flash-lite"
    ai_operator_model: str = "gemini:gemini-3.1-flash-lite"
    ai_planner_model: str = "gemini:gemini-3.1-flash-lite"
    ai_scribe_model: str = "gemini:gemini-3.1-flash-lite"
    ai_bubba_model: str = "gemini:gemini-3.1-flash-lite"
    ai_vision_model: str = "gemini:gemini-3.1-flash-lite"

    # --- Ephemeral Vision ---
    # Default to ultra-fast Gemini Flash with resilient serial fallback on rate limits
    # and secondary fallback to NVIDIA NIM.
    vision_provider: str = "gemini"
    vision_model_name: str = "gemini-3.1-flash-lite"
    vision_max_image_mb: int = 10
    vision_timeout_seconds: float = 45.0
    vision_fallback_model: str | None = "gemini-3.5-flash"
    vision_serial_processing: bool = False

    # --- Antigravity (agy) ConPTY Bridge ---
    # Executable or command used to launch the Antigravity CLI inside the PTY.
    agy_cli_command: str = "agy"
    agy_default_directory: str = r"C:\kirtan\IRIS"
    # Seconds of quiet output after a prompt before a task counts as complete.
    agy_quiet_window_seconds: float = 2.5
    agy_buffer_lines: int = 500
    agy_auto_voice: bool = True
    agy_tts_enabled: bool = True
    # JSON object mapping project aliases to absolute paths.
    agy_project_aliases: str | None = None

    # --- Gmail Integration ---
    gmail_client_id: str | None = None
    gmail_client_secret: str | None = None
    gmail_redirect_uri: str = "http://localhost:8000/api/email/auth/callback"

    # --- Google Drive Integration ---
    google_drive_client_id: str | None = None
    google_drive_client_secret: str | None = None
    google_drive_redirect_uri: str = "http://localhost:8085/"

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
