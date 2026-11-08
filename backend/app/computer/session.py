"""Session lifecycle, state management, and emergency kill-switch for Computer Control."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
from typing import Callable
import uuid

from app.computer.contracts import ActionRiskLevel, ComputerActionType, SessionInfo, SessionState
from app.core.logging import get_logger

logger = get_logger("iris.computer.session")

EMERGENCY_KILL_SIGNAL_FILE = Path(tempfile.gettempdir()) / "iris_emergency_stop.signal"


class SessionSecurityError(PermissionError):
    """Raised when an operation is attempted outside an authorized active session."""
    pass


class KillSwitchTriggeredError(RuntimeError):
    """Raised when an action is aborted due to emergency kill-switch engagement."""
    pass


class ComputerSessionManager:
    """Governs the authorization state, inactivity expiry, and emergency termination of desktop control."""

    def __init__(self, default_expiry_minutes: int = 5) -> None:
        self._lock = threading.RLock()
        self.default_expiry_minutes = default_expiry_minutes

        self._state: SessionState = SessionState.BACKGROUND
        self._session_id: str | None = None
        self._session_token: str | None = None
        self._created_at: datetime | None = None
        self._expires_at: datetime | None = None
        self._last_activity_at: datetime | None = None
        self._reason: str = "Idle background mode"
        self._kill_switch_engaged: bool = False
        self._kill_switch_source: str | None = None
        self._actions_count: int = 0
        self._on_kill_callbacks: list[Callable[[], None]] = []

    def _sync_external_kill_signal_locked(self) -> None:
        """Check for out-of-band sentinel signal file created by Electron or local emergency stops."""
        if not self._kill_switch_engaged and EMERGENCY_KILL_SIGNAL_FILE.exists():
            try:
                data = json.loads(EMERGENCY_KILL_SIGNAL_FILE.read_text(encoding="utf-8"))
                source = data.get("source", "external_sentinel_file")
            except Exception:
                source = "external_sentinel_file"
            self._kill_switch_engaged = True
            self._kill_switch_source = source
            prev_id = self._session_id
            self._state = SessionState.TERMINATED
            self._reason = f"EMERGENCY KILL SWITCH TRIGGERED ({source})"
            self._session_token = None
            logger.warning("Emergency kill detected via sentinel signal file (%s)! Revoked session %s", source, prev_id)
            self._fire_kill_callbacks_locked()

    def _fire_kill_callbacks_locked(self) -> None:
        for cb in self._on_kill_callbacks:
            try:
                cb()
            except Exception as exc:
                logger.error("Error in kill-switch callback: %s", exc)

    def get_info(self) -> SessionInfo:
        """Return the current session state and telemetry."""
        with self._lock:
            self._sync_external_kill_signal_locked()
            self._check_expiry_locked()
            now = datetime.now(timezone.utc)
            return SessionInfo(
                session_id=self._session_id or "none",
                state=self._state,
                created_at=self._created_at or now,
                expires_at=self._expires_at or now,
                last_activity_at=self._last_activity_at or now,
                reason=self._reason,
                is_interactive_desktop=True,
                kill_switch_engaged=self._kill_switch_engaged,
                kill_switch_source=self._kill_switch_source,
                session_token=self._session_token,
                actions_count=self._actions_count,
            )

    @property
    def is_active(self) -> bool:
        """True if a valid, unpaused, non-expired session is currently active."""
        with self._lock:
            self._sync_external_kill_signal_locked()
            self._check_expiry_locked()
            return self._state == SessionState.ACTIVE and not self._kill_switch_engaged

    @property
    def is_kill_switch_engaged(self) -> bool:
        with self._lock:
            self._sync_external_kill_signal_locked()
            return self._kill_switch_engaged

    @property
    def session_token(self) -> str | None:
        with self._lock:
            return self._session_token

    def validate_session_token(self, token: str | None) -> bool:
        """Verify that caller holds the active session token."""
        with self._lock:
            if not self.is_active or not self._session_token:
                return False
            if not token:
                return False
            return secrets.compare_digest(token, self._session_token)

    def activate_session(
        self,
        reason: str,
        expiry_minutes: int | None = None,
        authorized_by: str = "user",
    ) -> SessionInfo:
        """Explicitly activate a computer-control session upon verified user request."""
        with self._lock:
            self._sync_external_kill_signal_locked()
            if self._kill_switch_engaged:
                raise KillSwitchTriggeredError(
                    f"Kill-switch is currently engaged (triggered by {self._kill_switch_source}). "
                    "Reset the kill-switch before activating a new session."
                )

            mins = expiry_minutes or self.default_expiry_minutes
            now = datetime.now(timezone.utc)

            self._session_id = f"csess_{uuid.uuid4().hex[:12]}"
            self._session_token = f"cst_{secrets.token_hex(16)}"
            self._state = SessionState.ACTIVE
            self._created_at = now
            self._last_activity_at = now
            self._expires_at = now + timedelta(minutes=mins)
            self._reason = reason or "User requested computer control"
            self._actions_count = 0

            logger.info(
                "Computer control session activated: session_id=%s, reason='%s', expires_in=%dm, authorized_by=%s",
                self._session_id,
                self._reason,
                mins,
                authorized_by,
            )
            return self.get_info()

    def touch(self) -> None:
        """Refresh last activity time and extend expiry while active."""
        with self._lock:
            self._sync_external_kill_signal_locked()
            self._check_expiry_locked()
            if self._state == SessionState.ACTIVE:
                now = datetime.now(timezone.utc)
                self._last_activity_at = now
                self._expires_at = now + timedelta(minutes=self.default_expiry_minutes)
                self._actions_count += 1

    def pause_session(self, reason: str | None = None) -> SessionInfo:
        """Pause computer control; stops new actions and screen captures."""
        with self._lock:
            self._sync_external_kill_signal_locked()
            if self._state == SessionState.ACTIVE:
                self._state = SessionState.PAUSED
                if reason:
                    self._reason = reason
                logger.info("Computer control session paused: session_id=%s", self._session_id)
            return self.get_info()

    def resume_session(self) -> SessionInfo:
        """Resume a paused computer-control session."""
        with self._lock:
            self._sync_external_kill_signal_locked()
            if self._kill_switch_engaged:
                raise KillSwitchTriggeredError("Cannot resume while kill-switch is engaged.")
            self._check_expiry_locked()
            if self._state == SessionState.PAUSED:
                now = datetime.now(timezone.utc)
                self._state = SessionState.ACTIVE
                self._last_activity_at = now
                self._expires_at = now + timedelta(minutes=self.default_expiry_minutes)
                logger.info("Computer control session resumed: session_id=%s", self._session_id)
            return self.get_info()

    def terminate_session(self, reason: str = "User completed task") -> SessionInfo:
        """Terminate the active session and return to background mode."""
        with self._lock:
            prev_id = self._session_id
            self._state = SessionState.TERMINATED
            self._reason = reason
            self._session_token = None
            logger.info("Computer control session terminated: session_id=%s, reason='%s'", prev_id, reason)
            # Reset back to background state for subsequent availability
            self._state = SessionState.BACKGROUND
            self._session_id = None
            return self.get_info()

    def trigger_kill_switch(self, source: str = "user_ui") -> None:
        """Emergency immediate stop mechanism. Revokes access independently of the AI model."""
        with self._lock:
            self._kill_switch_engaged = True
            self._kill_switch_source = source
            prev_id = self._session_id
            self._state = SessionState.TERMINATED
            self._reason = f"EMERGENCY KILL SWITCH TRIGGERED ({source})"
            self._session_token = None
            logger.warning(
                "EMERGENCY KILL SWITCH ENGAGED! source=%s, aborted_session=%s",
                source,
                prev_id,
            )

            # Write out-of-band sentinel signal file
            try:
                EMERGENCY_KILL_SIGNAL_FILE.write_text(
                    json.dumps({"source": source, "timestamp": time.time()}),
                    encoding="utf-8",
                )
            except Exception as exc:
                logger.debug("Failed writing sentinel signal file: %s", exc)

            # Fire registered cancellation callbacks
            self._fire_kill_callbacks_locked()

    def reset_kill_switch(self) -> SessionInfo:
        """Reset the kill switch state back to background mode."""
        with self._lock:
            # Remove sentinel signal file
            try:
                if EMERGENCY_KILL_SIGNAL_FILE.exists():
                    EMERGENCY_KILL_SIGNAL_FILE.unlink()
            except Exception as exc:
                logger.debug("Failed removing sentinel signal file: %s", exc)

            self._kill_switch_engaged = False
            self._kill_switch_source = None
            self._state = SessionState.BACKGROUND
            self._session_id = None
            self._session_token = None
            self._reason = "Kill switch reset to background mode"
            logger.info("Computer control kill-switch reset.")
            return self.get_info()

    def register_kill_callback(self, callback: Callable[[], None]) -> None:
        """Register a cleanup/cancellation hook to be invoked when kill switch is hit."""
        with self._lock:
            if callback not in self._on_kill_callbacks:
                self._on_kill_callbacks.append(callback)

    def validate_action_allowed(self, action_type: ComputerActionType | str) -> None:
        """Guard method called before any desktop, screen, or clipboard action is executed."""
        with self._lock:
            self._sync_external_kill_signal_locked()
            if self._kill_switch_engaged:
                raise KillSwitchTriggeredError(
                    f"Action blocked: Emergency kill-switch is engaged ({self._kill_switch_source})."
                )

            self._check_expiry_locked()

            # Session status inspection and stop are allowed in background
            if action_type in (
                ComputerActionType.SESSION_STATUS,
                ComputerActionType.SESSION_STOP,
                "computer.session.status",
                "computer.session.stop",
            ):
                return

            if self._state == SessionState.PAUSED:
                raise SessionSecurityError("Computer control is paused. Resume the session to continue.")

            if self._state != SessionState.ACTIVE:
                raise SessionSecurityError(
                    f"Desktop access is disabled in {self._state.value} mode. "
                    "An authorized computer-control session must be explicitly activated."
                )

            self.touch()

    def _check_expiry_locked(self) -> None:
        """Inactivity expiration check."""
        if self._state == SessionState.ACTIVE and self._expires_at:
            if datetime.now(timezone.utc) > self._expires_at:
                logger.info(
                    "Computer control session expired due to inactivity: session_id=%s",
                    self._session_id,
                )
                self._state = SessionState.TERMINATED
                self._reason = "Expired due to inactivity"
                self._session_id = None
                self._session_token = None
                self._state = SessionState.BACKGROUND


# Global singleton instance
session_manager = ComputerSessionManager()
