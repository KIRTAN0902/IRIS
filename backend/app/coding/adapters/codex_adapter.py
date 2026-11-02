"""Managed Codex CLI headless sessions using the documented JSONL protocol."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from app.coding.contracts import AgentCapabilities
from app.core.config import settings

SECRET_ENV = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH)", re.I)


def _scrub(value: Any) -> Any:
    from app.execution.policy import redact_secrets

    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [_scrub(x) for x in value]
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    return value


class CodexHeadlessSession:
    def __init__(self, key: str, directory: str, alias: str, process: subprocess.Popen[str]):
        self.key = key
        self.directory = directory
        self.alias = alias
        self.process = process
        self.thread_id: str | None = None
        self.state = "STARTING"
        self.last_result: dict[str, Any] | None = None
        self.output: deque[str] = deque(maxlen=max(100, settings.agy_buffer_lines))
        self.events: deque[dict[str, Any]] = deque(maxlen=1000)
        self.event_total = 0
        self.warnings: deque[str] = deque(maxlen=100)
        self.needs_attention = False
        self.created_at = time.time()
        self.updated_at = time.time()
        self.lock = threading.RLock()
        self.subscribers: list[Any] = []

        # Read streams in background threads
        threading.Thread(target=self._read_stdout, name=f"codex-out-{key[:8]}", daemon=True).start()
        threading.Thread(target=self._read_stderr, name=f"codex-err-{key[:8]}", daemon=True).start()
        threading.Thread(target=self._watch_exit, name=f"codex-wait-{key[:8]}", daemon=True).start()

    def _publish(self, event: dict[str, Any]) -> None:
        event = _scrub(event)
        line = json.dumps(event, ensure_ascii=False)
        with self.lock:
            self.events.append(event)
            self.event_total += 1
            self.updated_at = time.time()

            ev_type = event.get("type")
            if ev_type == "thread.started":
                self.thread_id = event.get("thread_id")
            elif ev_type == "item.completed":
                item = event.get("item", {})
                item_type = item.get("type")
                if item_type == "agent_message":
                    text = item.get("text", "")
                    if text:
                        self.output.append(text + "\n")
                elif item_type in {"command_execution", "tool_call"}:
                    cmd = item.get("command") or item.get("call") or ""
                    out = item.get("output") or ""
                    if cmd:
                        self.output.append(f"$ {cmd}\n")
                    if out:
                        self.output.append(out[:1000] + "\n")
            elif ev_type == "turn.completed":
                self.state = "IDLE"
                usage = event.get("usage", {})
                self.last_result = {
                    "status": "SUCCESS",
                    "thread_id": self.thread_id,
                    "usage": usage,
                    "response": "".join(self.output)[-5000:],
                }

            for q in list(self.subscribers):
                try:
                    q.put_nowait(line)
                except Exception:
                    pass

    def _read_stdout(self) -> None:
        try:
            if self.process.stdout:
                for line in self.process.stdout:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        parsed = json.loads(stripped)
                        if isinstance(parsed, dict):
                            self._publish(parsed)
                    except json.JSONDecodeError:
                        with self.lock:
                            self.output.append(stripped + "\n")
                            self.warnings.append("Codex non-JSON output: " + stripped[:300])
        except Exception as exc:
            with self.lock:
                self.warnings.append(f"Codex stdout stream failed: {exc}")

    def _read_stderr(self) -> None:
        try:
            if self.process.stderr:
                for line in self.process.stderr:
                    val = line.rstrip()
                    if val and not val.startswith("Reading additional input"):
                        with self.lock:
                            if "not logged in" in val.lower() or "unauthorized" in val.lower():
                                self.state = "FAILED"
                                self.last_result = {
                                    "status": "ERROR",
                                    "error": "Codex authentication required. Run 'codex login' or check credentials.",
                                }
                            self.warnings.append(val[:1000])
                            self.output.append(f"[codex notice] {_scrub(val)}\n")
                            self.updated_at = time.time()
        except Exception as exc:
            with self.lock:
                self.warnings.append(f"Codex diagnostic stream failed: {exc}")

    def _watch_exit(self) -> None:
        code = self.process.wait()
        with self.lock:
            if self.state not in ("FAILED", "WAITING_FOR_USER"):
                if code == 0:
                    self.state = "IDLE"
                    if not self.last_result:
                        self.last_result = {
                            "status": "SUCCESS",
                            "thread_id": self.thread_id,
                            "response": "".join(self.output)[-5000:],
                        }
                else:
                    self.state = "FAILED"
                    if not self.last_result:
                        self.last_result = {
                            "status": "ERROR",
                            "error": f"Codex exited with code {code}",
                        }
            self.updated_at = time.time()

    def stop(self) -> None:
        if self.process.poll() is None:
            try:
                self.process.terminate()
            except OSError:
                pass

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "key": self.key,
                "alias": self.alias,
                "directory": self.directory,
                "state": self.state,
                "alive": self.process.poll() is None,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "conversation_id": self.thread_id,
                "last_result": self.last_result,
                "recent_output": "".join(self.output)[-20000:],
                "warnings": [_scrub(w) for w in self.warnings],
                "events": list(self.events),
                "event_total": self.event_total,
            }


class CodexHeadlessManager:
    def __init__(self):
        self.sessions: dict[str, CodexHeadlessSession] = {}
        self.lock = threading.RLock()

    def _resolve_binary(self) -> str:
        bin_path = shutil.which("codex")
        if not bin_path:
            # Common Windows install path
            cand = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"
            if cand.is_file():
                bin_path = str(cand)
        if not bin_path:
            raise RuntimeError("Codex CLI executable was not found on PATH.")
        return bin_path

    def launch(
        self,
        directory: str,
        alias: str,
        prompt: str,
        conversation_id: str | None = None,
        permission_rules: dict[str, Any] | None = None,
    ) -> CodexHeadlessSession:
        path = Path(directory).resolve()
        if not path.is_dir():
            raise RuntimeError(f"Workspace directory does not exist: {directory}")

        codex_bin = self._resolve_binary()
        env = {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}

        # Build command line
        if conversation_id:
            argv = [codex_bin, "exec", "resume", conversation_id, prompt, "--json"]
        else:
            argv = [
                codex_bin,
                "exec",
                prompt,
                "--json",
                "-C",
                str(path),
                "-s",
                "workspace-write",
                "-a",
                "never",
            ]

        proc = subprocess.Popen(
            argv,
            cwd=str(path),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )

        # Close stdin immediately so codex does not block waiting for input
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass

        session = CodexHeadlessSession(str(uuid.uuid4()), str(path), alias, proc)
        with self.lock:
            self.sessions[session.key] = session
        return session

    def get(self, key: str) -> CodexHeadlessSession | None:
        with self.lock:
            return self.sessions.get(key)

    def list_sessions(self) -> list[CodexHeadlessSession]:
        with self.lock:
            return list(self.sessions.values())

    def stop(self, key: str) -> bool:
        session = self.get(key)
        if not session:
            return False
        session.stop()
        return True

    def shutdown(self) -> None:
        with self.lock:
            sessions = list(self.sessions.values())
        for session in sessions:
            session.stop()


codex_headless_manager = CodexHeadlessManager()


class CodexCLIAdapter:
    agent_id = "codex-cli"
    capabilities = AgentCapabilities(
        interactive=False,
        prompt_submission=True,
        streaming_output=True,
        resume=True,
        stop=True,
        follow_up=True,
        structured_events=True,
    )

    def detect(self) -> dict[str, Any]:
        bin_path = shutil.which("codex")
        if not bin_path:
            cand = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"
            if cand.is_file():
                bin_path = str(cand)

        version = None
        authenticated = False
        if bin_path:
            try:
                out = subprocess.run([bin_path, "--version"], capture_output=True, text=True, timeout=5).stdout.strip()
                version = out
            except (OSError, subprocess.SubprocessError):
                pass

            auth_file = Path.home() / ".codex" / "auth.json"
            authenticated = auth_file.is_file()

        return {
            "id": self.agent_id,
            "name": "Codex CLI",
            "available": bool(bin_path),
            "authenticated": authenticated,
            "path": bin_path,
            "version": version,
            "capabilities": self.capabilities.model_dump(),
        }

    def launch(self, directory: str, prompt: str, session_id: str, permissions: dict[str, Any] | None = None) -> Any:
        return codex_headless_manager.launch(directory, session_id, prompt, permission_rules=permissions)

    def send_prompt(self, session_id: str, prompt: str) -> Any:
        session = codex_headless_manager.get(session_id)
        if not session:
            raise RuntimeError("Codex session process is not available")
        # For non-interactive Codex, follow-up initiates a resume turn
        if session.thread_id:
            new_session = codex_headless_manager.launch(
                session.directory,
                session.alias,
                prompt,
                conversation_id=session.thread_id,
            )
            return new_session.snapshot()
        raise RuntimeError("Codex session has not emitted a thread ID for follow-up.")

    def resume_session(
        self,
        directory: str,
        conversation_id: str,
        alias: str = "workspace",
        permissions: dict[str, Any] | None = None,
    ) -> Any:
        return codex_headless_manager.launch(
            directory,
            alias,
            "",
            conversation_id=conversation_id,
            permission_rules=permissions,
        )

    def resume_session_id(
        self,
        directory: str,
        alias: str,
        conversation_id: str,
        permissions: dict[str, Any] | None = None,
    ) -> Any:
        return self.resume_session(directory, conversation_id, alias, permissions)

    def get_status(self, session_id: str) -> dict[str, Any]:
        session = codex_headless_manager.get(session_id)
        snapshot = session.snapshot() if session else None
        return {"active": bool(snapshot and snapshot.get("alive")), "session": snapshot}

    def get_output(self, session_id: str) -> str:
        session = codex_headless_manager.get(session_id)
        return session.snapshot()["recent_output"] if session else ""

    def stop(self, session_id: str) -> bool:
        return codex_headless_manager.stop(session_id)
