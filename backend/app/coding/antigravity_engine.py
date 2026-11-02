"""Antigravity implementation of the provider-neutral ICodingEngine interface."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from datetime import UTC, datetime
from typing import Any

from app.coding.engine_base import EngineEvent, EngineSessionInfo, ICodingEngine
from app.coding.git_workspace import run_git


class AntigravityEngine(ICodingEngine):
    """Integrates official Google Antigravity via headless NDJSON streaming."""

    def __init__(self, cli_path: str | None = None) -> None:
        self._cli_path = cli_path or shutil.which("agy") or shutil.which("agy.exe")
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "antigravity"

    def detect(self) -> dict[str, Any]:
        """Detect agy CLI version, authentication status, and available models."""
        available = bool(self._cli_path and os.path.isfile(self._cli_path))
        version = None
        models = []

        if available:
            try:
                proc = subprocess.run([self._cli_path, "--version"], capture_output=True, text=True, timeout=5)
                if proc.returncode == 0:
                    version = proc.stdout.strip()
            except (OSError, subprocess.SubprocessError):
                pass

            try:
                proc = subprocess.run([self._cli_path, "models"], capture_output=True, text=True, timeout=8)
                if proc.returncode == 0:
                    for line in proc.stdout.splitlines():
                        parts = line.strip().split("\t")
                        if len(parts) >= 2:
                            models.append({"id": parts[0], "name": parts[1]})
            except (OSError, subprocess.SubprocessError):
                pass

        # Also inspect Python SDK availability
        sdk_available = False
        try:
            import google.antigravity  # noqa: F401
            sdk_available = True
        except ImportError:
            pass

        return {
            "name": self.name,
            "available": available,
            "cli_path": self._cli_path,
            "version": version,
            "models_count": len(models),
            "models": models[:5],
            "sdk_available": sdk_available,
            "headless_ndjson_supported": True,
            "resumable_sessions_supported": True,
        }

    def start_session(
        self,
        workspace_dir: str,
        session_id: str,
        conversation_id: str | None = None,
        permissions: dict[str, Any] | None = None,
    ) -> EngineSessionInfo:
        """Launch headless NDJSON session inside the workspace."""
        if not self._cli_path:
            raise RuntimeError("Antigravity CLI (agy) is not available.")

        argv = [
            self._cli_path,
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--mode", "auto",
            "--dangerously-skip-permissions",
        ]

        if conversation_id:
            argv.extend(["--conversation", conversation_id])

        # Enforce sandbox if requested
        if permissions and permissions.get("sandbox"):
            argv.append("--sandbox")

        env = os.environ.copy()
        if permissions and permissions.get("adc_auth"):
            env["AGY_ADC_AUTH"] = "true"

        proc = subprocess.Popen(
            argv,
            cwd=workspace_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )

        session_state = {
            "proc": proc,
            "workspace_dir": workspace_dir,
            "events": [],
            "conversation_id": conversation_id,
            "cursor": 0,
            "alive": True,
            "started_at": datetime.now(UTC),
        }

        # Background reader thread to consume NDJSON events
        def _read_stdout():
            try:
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        ev_type = data.get("event") or data.get("type") or "message"
                        text = (
                            data.get("text_delta")
                            or data.get("content")
                            or data.get("result", {}).get("response", "")
                            or ""
                        )
                        event = EngineEvent(
                            event_type=ev_type,
                            payload=data,
                            text=str(text),
                        )
                        with self._lock:
                            session_state["events"].append(event)
                            if "conversation_id" in data:
                                session_state["conversation_id"] = data["conversation_id"]
                    except json.JSONDecodeError:
                        event = EngineEvent(event_type="raw_text", text=line)
                        with self._lock:
                            session_state["events"].append(event)
            finally:
                if proc.poll() is not None:
                    session_state["alive"] = False

        reader = threading.Thread(target=_read_stdout, daemon=True)
        reader.start()

        with self._lock:
            self._sessions[session_id] = session_state

        return EngineSessionInfo(
            session_id=session_id,
            engine_name=self.name,
            workspace_dir=workspace_dir,
            conversation_id=conversation_id,
            is_active=True,
        )

    def submit_prompt(self, session_id: str, prompt: str) -> None:
        """Send prompt NDJSON line to the engine."""
        session = self._sessions.get(session_id)
        if not session or not session["alive"]:
            raise RuntimeError(f"Session {session_id} is not running.")

        proc = session["proc"]
        payload = json.dumps({"type": "prompt", "text": prompt}) + "\n"
        proc.stdin.write(payload)
        proc.stdin.flush()

    def stream_events(self, session_id: str) -> list[EngineEvent]:
        """Fetch and advance event stream."""
        session = self._sessions.get(session_id)
        if not session:
            return []

        with self._lock:
            cursor = session["cursor"]
            events = session["events"][cursor:]
            session["cursor"] = len(session["events"])
            return events

    def stop(self, session_id: str) -> bool:
        """Terminate process tree and cancel session."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        proc = session.get("proc")
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        session["alive"] = False
        return True

    def get_diff(self, workspace_dir: str) -> dict[str, Any]:
        """Capture git diff and changed files in the workspace."""
        try:
            status_proc = run_git(workspace_dir, "status", "--porcelain")
            changed_files = []
            for line in status_proc.stdout.splitlines():
                if len(line) >= 4:
                    status_code = line[:2].strip()
                    file_path = line[3:].strip()
                    changed_files.append({"path": file_path, "status": status_code})

            stat_proc = run_git(workspace_dir, "diff", "--stat")
            diff_proc = run_git(workspace_dir, "diff")

            return {
                "changed_files": changed_files,
                "stat": stat_proc.stdout.strip(),
                "diff": diff_proc.stdout[:15000],
                "total_files": len(changed_files),
            }
        except Exception as e:
            return {"error": str(e), "changed_files": [], "total_files": 0}
