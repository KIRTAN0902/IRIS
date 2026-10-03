"""AI Provider Health & Connectivity Tracker.

Tracks operational status, timeouts, network outages, and failure reasons
for the active AI provider (whatever model is configured). When a provider fails to respond,
IRIS automatically falls back to deterministic decision logic and reports
the degradation so the UI can prominently alert the user.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.utils.datetime import utcnow

logger = get_logger("iris.ai.health")


class AIHealthTracker:
    """Monitors live responsiveness and error states of the active AI provider."""

    def __init__(self) -> None:
        self._last_success_at: datetime | None = None
        self._last_failure_at: datetime | None = None
        self._last_error: str | None = None
        self._consecutive_failures: int = 0
        self._provider_name: str = settings.ai_provider
        self._model_name: str | None = None

    def record_success(self, provider_name: str, model_name: str) -> None:
        """Record a successful AI completion."""
        self._provider_name = provider_name
        self._model_name = model_name
        self._last_success_at = utcnow()
        self._consecutive_failures = 0
        self._last_error = None
        logger.debug("AI health success recorded for provider=%s model=%s", provider_name, model_name)

    def record_failure(self, provider_name: str, model_name: str, error: Exception | str) -> None:
        """Record an AI completion failure (timeout, network error, status error)."""
        self._provider_name = provider_name
        self._model_name = model_name
        self._last_failure_at = utcnow()
        self._consecutive_failures += 1

        err_str = str(error).strip()
        # Clean up long traceback strings if passed
        if len(err_str) > 200:
            err_str = err_str[:200] + "..."
        self._last_error = err_str

        logger.warning(
            "AI health failure recorded (count=%d): provider=%s error=%s",
            self._consecutive_failures,
            provider_name,
            self._last_error,
        )

    def get_status(self) -> dict[str, Any]:
        """Return the current diagnostic status of the AI provider."""
        from app.ai.factory import get_ai_provider

        provider = get_ai_provider()
        provider_name = provider.name
        model_name = provider.model
        configured = provider.enabled
        harness = {
            "strategy": "native_tools" if provider.capabilities.native_tools else "structured_json",
            "capabilities": provider.capabilities.to_dict(),
        }

        if not configured:
            return {
                **harness,
                "provider": provider_name,
                "model": model_name,
                "configured": False,
                "responding": False,
                "status": "NOT_CONFIGURED",
                "message": f"AI provider '{provider_name}' is not configured (missing API key, model or base URL).",
                "last_error": self._last_error or "Missing AI_API_KEY, AI_MODEL or AI_BASE_URL configuration",
                "consecutive_failures": self._consecutive_failures,
                "last_checked_at": (self._last_failure_at or self._last_success_at or utcnow()).isoformat(),
            }

        # If failures occurred and no subsequent success occurred
        if self._consecutive_failures > 0:
            return {
                **harness,
                "provider": provider_name,
                "model": model_name,
                "configured": True,
                "responding": False,
                "status": "NOT_RESPONDING",
                "message": (
                    f"AI provider '{provider_name}' ({model_name}) is not responding. "
                    "IRIS is operating in deterministic fallback mode."
                ),
                "last_error": self._last_error,
                "consecutive_failures": self._consecutive_failures,
                "last_checked_at": (self._last_failure_at or utcnow()).isoformat(),
            }

        return {
            **harness,
            "provider": provider_name,
            "model": model_name,
            "configured": True,
            "responding": True,
            "status": "OPERATIONAL",
            "message": f"AI provider '{provider_name}' ({model_name}) is operational.",
            "last_error": None,
            "consecutive_failures": 0,
            "last_checked_at": (self._last_success_at or utcnow()).isoformat(),
        }

    def reset(self) -> None:
        """Reset internal failure counters (useful for testing)."""
        self._last_success_at = None
        self._last_failure_at = None
        self._last_error = None
        self._consecutive_failures = 0


# Global singleton instance
ai_health = AIHealthTracker()
