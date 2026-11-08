"""Session lifecycle, state management, and emergency kill-switch for Computer Control."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile
import threading
import time
from typing import Callable
import uuid

from app.computer.contracts import ActionRiskLevel, ComputerActionType, SessionInfo, SessionState
from app.core.logging import get_logger

logger = get_logger("iris.computer.session")


def get_secure_sentinel_dir() -> Path:
    """Resolve and initialize a secure, user-private directory for sentinel signals and device keys."""
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data and os.name == "nt":
        base_dir = Path(local_app_data) / "IRIS"
    else:
        base_dir = Path.home() / ".iris"
    base_dir.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            base_dir.chmod(0o700)
        except Exception:
            pass
    return base_dir


EMERGENCY_KILL_SIGNAL_FILE = get_secure_sentinel_dir() / "iris_emergency_stop.signal"


def is_safe_sentinel_path(path: Path) -> bool:
    """Verify that the sentinel path is a regular file owned by the user, without symlinks or reparse points."""
    try:
        if not path.exists():
            return False
        # Reject symlinks on all platforms
        if path.is_symlink():
            logger.warning("Rejected emergency sentinel file: detected symlink at %s", path)
            return False
        st = os.lstat(str(path))
        if stat.S_ISLNK(st.st_mode):
            logger.warning("Rejected emergency sentinel file: detected symlink mode at %s", path)
            return False
        # Windows reparse point check (0x400 = FILE_ATTRIBUTE_REPARSE_POINT)
        file_attrs = getattr(st, "st_file_attributes", 0)
        if file_attrs & 0x400:
            logger.warning("Rejected emergency sentinel file: detected Windows reparse point at %s", path)
            return False
        # Must be regular file
        if not stat.S_ISREG(st.st_mode):
            logger.warning("Rejected emergency sentinel file: not a regular file at %s", path)
            return False
        # Size sanity check (e.g. 10 bytes to 4096 bytes)
        if st.st_size <= 0 or st.st_size > 4096:
            logger.warning("Rejected emergency sentinel file: invalid file size (%d bytes) at %s", st.st_size, path)
            return False
        return True
    except Exception as exc:
        logger.warning("Error inspecting emergency sentinel path %s: %s", path, exc)
        return False


def write_secure_sentinel(source: str = "user_ui") -> bool:
    """Atomically create the emergency sentinel file in the user-private directory."""
    sentinel_path = EMERGENCY_KILL_SIGNAL_FILE
    sentinel_dir = sentinel_path.parent
    sentinel_dir.mkdir(parents=True, exist_ok=True)
    temp_path = sentinel_dir / f"emergency_{int(time.time() * 1000)}_{secrets.token_hex(4)}.tmp"
    try:
        payload = {
            "signal": "EMERGENCY_STOP",
            "source": str(source)[:100],
            "timestamp": time.time(),
            "nonce": secrets.token_hex(16),
            "pid": os.getpid(),
        }
        temp_path.write_text(json.dumps(payload), encoding="utf-8")
        if os.name != "nt":
            try:
                temp_path.chmod(0o600)
            except Exception:
                pass
        # Atomic file replacement in same filesystem directory
        os.replace(str(temp_path), str(sentinel_path))
        return True
    except Exception as exc:
        logger.warning("Failed writing secure emergency sentinel: %s", exc)
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        return False


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
        self._device_id: str | None = None
        self._created_at: datetime | None = None
        self._expires_at: datetime | None = None
        self._last_activity_at: datetime | None = None
        self._reason: str = "Idle background mode"
        self._kill_switch_engaged: bool = False
        self._kill_switch_source: str | None = None
        self._actions_count: int = 0
        self._on_kill_callbacks: list[Callable[[], None]] = []
        self._last_reset_timestamp: float = 0.0
        self._last_handled_sentinel_timestamp: float = 0.0

    def _sync_external_kill_signal_locked(self) -> None:
        """Check for out-of-band sentinel signal file created by Electron or local emergency stops."""
        sentinel_path = EMERGENCY_KILL_SIGNAL_FILE
        if not is_safe_sentinel_path(sentinel_path):
            return

        try:
            content = sentinel_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if not isinstance(data, dict):
                logger.warning("Rejected emergency sentinel file: payload is not a JSON object")
                return

            sig_time = float(data.get("timestamp", 0.0))
            now = time.time()

            # Reject if timestamp is in future (>60s skew) or older than 24h
            if sig_time > now + 60.0 or sig_time < now - 86400.0:
                logger.warning("Rejected emergency sentinel file: stale or future timestamp (%f vs now %f)", sig_time, now)
                return

            # Reject if this signal was already reset
            if sig_time <= self._last_reset_timestamp:
                return

            source = str(data.get("source", "external_sentinel_file"))[:100]
            self._kill_switch_engaged = True
            self._kill_switch_source = source
            prev_id = self._session_id
            self._state = SessionState.TERMINATED
            self._reason = f"EMERGENCY KILL SWITCH TRIGGERED ({source})"
            self._session_token = None
            self._device_id = None
            self._last_handled_sentinel_timestamp = sig_time
            logger.warning("Emergency kill detected via secure sentinel signal file (%s)! Revoked session %s", source, prev_id)
            self._fire_kill_callbacks_locked()
        except Exception as exc:
            logger.warning("Failed processing emergency sentinel file: %s", exc)

    def _fire_kill_callbacks_locked(self) -> None:
        for cb in self._on_kill_callbacks:
            try:
                cb()
            except Exception as exc:
                logger.error("Error in kill-switch callback: %s", exc)

    def get_info(self, include_token: bool = False) -> SessionInfo:
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
                session_token=self._session_token if include_token else None,
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

    def validate_session_token(self, token: str | None, device_id: str | None = None) -> bool:
        """Verify that caller holds the active session token."""
        valid, _ = self.verify_session_token_detailed(token, device_id)
        return valid

    def verify_session_token_detailed(
        self, token: str | None, device_id: str | None = None
    ) -> tuple[bool, str | None]:
        """Validate session token with detailed error reason."""
        with self._lock:
            self._sync_external_kill_signal_locked()
            if self._kill_switch_engaged:
                return False, f"Emergency kill-switch is engaged ({self._kill_switch_source})."
            self._check_expiry_locked()
            if self._state != SessionState.ACTIVE or not self._session_token:
                return False, "No active computer control session. Session may have expired or terminated."
            if not token:
                return False, "Missing mandatory computer session token."
            if not secrets.compare_digest(token, self._session_token):
                return False, "Invalid, expired, or revoked computer session token."
            if device_id and self._device_id and device_id != self._device_id:
                return False, f"Session token is bound to device '{self._device_id}', not '{device_id}'."
            return True, None

    def activate_session(
        self,
        reason: str,
        expiry_minutes: int | None = None,
        authorized_by: str = "user",
        device_id: str | None = None,
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
            self._session_token = f"cst_{secrets.token_hex(24)}"
            self._device_id = device_id or "laptop_host_primary"
            self._state = SessionState.ACTIVE
            self._created_at = now
            self._last_activity_at = now
            self._expires_at = now + timedelta(minutes=mins)
            self._reason = reason or "User requested computer control"
            self._actions_count = 0

            logger.info(
                "Computer control session activated: session_id=%s, reason='%s', expires_in=%dm, authorized_by=%s, device_id=%s",
                self._session_id,
                self._reason,
                mins,
                authorized_by,
                self._device_id,
            )
            return self.get_info(include_token=True)

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
            self._device_id = None
            logger.info("Computer control session terminated: session_id=%s, reason='%s'", prev_id, reason)
            # Reset back to background state for subsequent availability
            self._state = SessionState.BACKGROUND
            self._session_id = None
            return self.get_info(include_token=False)

    def trigger_kill_switch(self, source: str = "user_ui") -> None:
        """Emergency immediate stop mechanism. Revokes access independently of the AI model."""
        with self._lock:
            self._kill_switch_engaged = True
            self._kill_switch_source = source
            prev_id = self._session_id
            self._state = SessionState.TERMINATED
            self._reason = f"EMERGENCY KILL SWITCH TRIGGERED ({source})"
            self._session_token = None
            self._device_id = None
            logger.warning(
                "EMERGENCY KILL SWITCH ENGAGED! source=%s, aborted_session=%s",
                source,
                prev_id,
            )

            # Atomically write out-of-band sentinel signal file
            write_secure_sentinel(source=source)

            # Fire registered cancellation callbacks
            self._fire_kill_callbacks_locked()

    def reset_kill_switch(self) -> SessionInfo:
        """Reset the kill switch state back to background mode."""
        with self._lock:
            # Safely remove sentinel signal file without following symlinks
            try:
                sentinel_path = EMERGENCY_KILL_SIGNAL_FILE
                if sentinel_path.is_symlink():
                    logger.warning("Unlinking symlink at sentinel location during reset.")
                    sentinel_path.unlink()
                elif is_safe_sentinel_path(sentinel_path):
                    sentinel_path.unlink()
                elif sentinel_path.exists():
                    sentinel_path.unlink()
            except Exception as exc:
                logger.debug("Failed removing sentinel signal file: %s", exc)

            self._last_reset_timestamp = time.time()
            self._kill_switch_engaged = False
            self._kill_switch_source = None
            self._state = SessionState.BACKGROUND
            self._session_id = None
            self._session_token = None
            self._device_id = None
            self._reason = "Kill switch reset to background mode"
            logger.info("Computer control kill-switch reset.")
            return self.get_info(include_token=False)

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
