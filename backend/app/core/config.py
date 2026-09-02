"""Application configuration.

All runtime configuration is loaded from environment variables (optionally via
a local `.env` file). Nothing here is ever hard-coded elsewhere in the app.
"""

from functools import lru_cache
from pathlib import Path

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
    ai_provider: str = "omniroute"
    ai_context_max_tasks: int = 25

    # OmniRoute (OpenAI-compatible)
    omniroute_base_url: str = "http://localhost:20128/v1"
    omniroute_api_key: str | None = None
    omniroute_model: str = "auto/best-fast"
    omniroute_timeout_seconds: float = 45.0

    # Gemini
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: float = 45.0

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

    @property
    def ai_enabled(self) -> bool:
        prov = self.ai_provider.lower()
        if prov == "omniroute":
            return bool(self.omniroute_base_url)
        elif prov == "gemini":
            return bool(self.gemini_api_key)
        elif prov == "mock":
            return True
        return False


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor; import this instead of constructing Settings."""
    return Settings()


settings = get_settings()
