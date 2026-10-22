"""Persistent ConPTY bridge for the Antigravity (``agy``) CLI.

Keeps one long-lived interactive process per project so IRIS can drive the
Antigravity coding agent from a phone, the Mesh relay, the Operator agent, or
the local terminal without respawning or losing conversation context.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, AsyncGenerator

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("iris.services.agy_bridge")

ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1B\\))")
STAT_RE = re.compile(r"(\d+)\s+files?\s+changed(?:,\s+(\d+)\s+insertions?\(\+\))?(?:,\s+(\d+)\s+deletions?\(-\))?")
LOCAL_AGENT_ID = "laptop_host_primary"

DEFAULT_PROJECT_ALIASES: dict[str, str] = {
    "iris": r"C:\kirtan\IRIS",
    "notebook": r"C:\kirtan\Notebook",
    "marketory": r"C:\kirtan\Marketory",
    "nexus": r"C:\kirtan\Nexus",
}

NATIVE_SLASH_COMMANDS = {
    "/resume",
    "/models",
    "/usage",
    "/clear",
    "/compact",
    "/status",
    "/help",
}


class AgyError(RuntimeError):
    """Raised when an Antigravity session cannot be created or driven."""


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text).replace("\r", "")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _command_argv() -> list[str]:
    raw = (settings.agy_cli_command or "agy").strip()
    try:
        argv = shlex.split(raw, posix=False)
    except ValueError:
        argv = [raw]
    if not argv:
        argv = ["agy"]
    resolved = shutil.which(argv[0])
    if resolved:
        argv[0] = resolved
    return argv


_fallback_loop: asyncio.AbstractEventLoop | None = None
_fallback_loop_lock = threading.Lock()


def _get_fallback_loop() -> asyncio.AbstractEventLoop:
    global _fallback_loop
    with _fallback_loop_lock:
        if _fallback_loop is None or _fallback_loop.is_closed():
            loop = asyncio.new_event_loop()
            thread = threading.Thread(
                target=loop.run_forever,
                name="iris-agy-loop",
                daemon=True,
            )
            thread.start()
            _fallback_loop = loop
        return _fallback_loop


class AgySession:
    """One interactive Antigravity process bound to a project directory."""

    def __init__(self, key: str, directory: str, alias: str) -> None:
        self.key = key
        self.directory = directory
        self.alias = alias
        self.state = "STARTING"
        self.process: Any = None
        self.pty: Any = None
        self.reader_task: asyncio.Task[Any] | None = None
        self.monitor_task: asyncio.Task[Any] | None = None
        self.buffer: deque[str] = deque(maxlen=max(50, settings.agy_buffer_lines))
        self.subscribers: list[asyncio.Queue[str]] = []
        self.created_at = _now_iso()
        self.last_output_at = time.monotonic()
        self.last_prompt = ""
        self.last_slash_command = ""
        self.last_diff_stat = ""
        self.last_diff = ""
        self.last_summary = ""
        self.pending_prompt = ""
        self.task_serial = 0
        self.output_since_prompt = False

    @property
    def alive(self) -> bool:
        if self.pty is not None:
            probe = getattr(self.pty, "isalive", True)
            return bool(probe() if callable(probe) else probe)
        if self.process is not None:
            return self.process.poll() is None
        return False

    def recent(self, lines: int = 60) -> str:
        if lines <= 0:
            return ""
        return "\n".join(list(self.buffer)[-lines:])

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "alias": self.alias,
            "directory": self.directory,
            "state": self.state,
            "alive": self.alive,
            "created_at": self.created_at,
            "last_output_at": self.last_output_at,
            "last_prompt": self.last_prompt,
            "last_slash_command": self.last_slash_command,
            "last_diff_stat": self.last_diff_stat,
            "last_summary": self.last_summary,
            "pending_prompt": self.pending_prompt,
            "buffer_lines": len(self.buffer),
        }


class AgySessionManager:
    """Registry, PTY driver, output fan-out and completion harvester."""

    def __init__(self) -> None:
        self.active_sessions: dict[str, AgySession] = {}
        self.current_session_key: str | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.RLock()
        self._aliases: dict[str, str] = dict(DEFAULT_PROJECT_ALIASES)

    # -- lifecycle ---------------------------------------------------------

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self._loop = loop or asyncio.get_event_loop()
        self._aliases = self._load_aliases()

    async def shutdown(self) -> None:
        for session in list(self.active_sessions.values()):
            self.close_session(session.key)

    def close_session(self, key: str) -> bool:
        session = self.find_session(key)
        if session is None:
            return False
        with self._lock:
            self.active_sessions.pop(session.key, None)
        for task in (session.reader_task, session.monitor_task):
            if task and not task.done():
                task.cancel()
        try:
            if session.pty is not None:
                session.pty.close(force=True)
            elif session.process is not None and session.process.poll() is None:
                session.process.terminate()
        except Exception:
            logger.debug("Failed closing agy session %s", session.key, exc_info=True)
        if self.current_session_key == session.key:
            self.current_session_key = next(iter(self.active_sessions), None)
        return True

    # -- workspace resolution ---------------------------------------------

    def _load_aliases(self) -> dict[str, str]:
        aliases = dict(DEFAULT_PROJECT_ALIASES)
        raw = settings.agy_project_aliases
        if raw:
            try:
                extra = json.loads(raw)
            except (TypeError, ValueError):
                extra = {}
            if isinstance(extra, dict):
                aliases.update({str(k).lower(): str(v) for k, v in extra.items()})
        return aliases

    def list_workspaces(self) -> list[dict[str, Any]]:
        seen: set[str] = set()
        workspaces: list[dict[str, Any]] = []
        for alias, raw_path in self._aliases.items():
            path = Path(raw_path)
            seen.add(str(path).lower())
            workspaces.append(
                {
                    "alias": alias,
                    "path": str(path),
                    "exists": path.is_dir(),
                    "is_git": (path / ".git").exists(),
                    "source": "alias",
                }
            )
        root = Path(r"C:\kirtan")
        if root.is_dir():
            try:
                children = sorted(root.iterdir(), key=lambda p: p.name.lower())
            except OSError:
                children = []
            for child in children:
                if not child.is_dir() or str(child).lower() in seen:
                    continue
                if not (child / ".git").exists():
                    continue
                alias = child.name.lower().replace(" ", "_")
                self._aliases.setdefault(alias, str(child))
                workspaces.append(
                    {
                        "alias": alias,
                        "path": str(child),
                        "exists": True,
                        "is_git": True,
                        "source": "discovered",
                    }
                )
        return workspaces

    def resolve_directory(self, value: str | None) -> tuple[str, str]:
        raw = (value or "").strip().strip('"').strip("'")
        if not raw:
            raw = settings.agy_default_directory
        alias_key = raw.lower()
        if alias_key in self._aliases:
            path = Path(self._aliases[alias_key])
            return str(path), alias_key

        candidate = Path(os.path.expandvars(os.path.expanduser(raw)))
        if not candidate.is_absolute():
            candidate = Path(r"C:\kirtan") / raw
        if not candidate.is_dir():
            raise AgyError(f"Workspace not found: {raw}")
        resolved = str(candidate.resolve())
        alias = next(
            (name for name, path in self._aliases.items() if str(Path(path)).lower() == resolved.lower()),
            candidate.name.lower().replace(" ", "_") or "workspace",
        )
        self._aliases.setdefault(alias, resolved)
        return resolved, alias

    def find_session(self, key: str | None) -> AgySession | None:
        if not key:
            return self.active_sessions.get(self.current_session_key or "")
        needle = key.strip().lower()
        if needle in self.active_sessions:
            return self.active_sessions[needle]
        for session in self.active_sessions.values():
            if needle in {
                session.alias.lower(),
                session.directory.lower(),
                Path(session.directory).name.lower(),
            }:
                return session
        return None

    # -- spawning ----------------------------------------------------------

    def spawn_or_attach(self, directory: str | None = None, alias: str | None = None) -> AgySession:
        resolved, resolved_alias = self.resolve_directory(directory or alias)
        key = (alias or resolved_alias).strip().lower().replace(" ", "_")
        with self._lock:
            existing = self.active_sessions.get(key)
            if existing is not None and existing.alive:
                self.current_session_key = existing.key
                return existing
            if existing is not None:
                self.active_sessions.pop(key, None)
            session = AgySession(key=key, directory=resolved, alias=resolved_alias)
            self.active_sessions[key] = session
            self.current_session_key = key

        try:
            self._start_process(session)
        except Exception as exc:
            with self._lock:
                self.active_sessions.pop(key, None)
            raise AgyError(f"Could not start Antigravity in {resolved}: {exc}") from exc

        session.state = "IDLE"
        self._append(session, f"[iris] Attached to {resolved_alias} ({resolved}).\n")
        session.reader_task = self._schedule(self._reader_loop(session))
        return session

    def _start_process(self, session: AgySession) -> None:
        argv = _command_argv()
        if os.name == "nt":
            try:
                from winpty import PtyProcess
            except Exception:
                PtyProcess = None  # type: ignore[assignment]
            if PtyProcess is not None:
                try:
                    session.pty = PtyProcess.spawn(
                        argv,
                        cwd=session.directory,
                        dimensions=(40, 160),
                    )
                    return
                except Exception:
                    logger.warning("pywinpty spawn failed; falling back to pipes", exc_info=True)
        self._start_pipe_process(session, argv)

    def _start_pipe_process(self, session: AgySession, argv: list[str]) -> None:
        if os.name == "nt":
            command = (
                "Set-Location -LiteralPath "
                + "'"
                + session.directory.replace("'", "''")
                + "'; & "
                + " ".join(json.dumps(part) for part in argv)
            )
            popen_argv = ["powershell.exe", "-NoLogo", "-NoExit", "-Command", command]
            creationflags = 0x00000200
        else:
            popen_argv = argv
            creationflags = 0
        session.process = subprocess.Popen(
            popen_argv,
            cwd=session.directory,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )

    def _schedule(self, coro: Any) -> Any:
        try:
            return asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            pass
        loop = self._loop
        if loop is not None and loop.is_running():
            return asyncio.run_coroutine_threadsafe(coro, loop)
        return asyncio.run_coroutine_threadsafe(coro, _get_fallback_loop())

    # -- I/O ---------------------------------------------------------------

    async def _reader_loop(self, session: AgySession) -> None:
        try:
            while True:
                if session.pty is not None:
                    try:
                        chunk = await asyncio.to_thread(session.pty.read, 4096)
                    except EOFError:
                        break
                    except Exception:
                        if not session.alive:
                            break
                        logger.debug("PTY read error for %s", session.key, exc_info=True)
                        await asyncio.sleep(0.1)
                        continue
                    text = chunk if isinstance(chunk, str) else chunk.decode("utf-8", "replace")
                else:
                    if session.process is None:
                        break
                    line = await asyncio.to_thread(session.process.stdout.readline)
                    if not line:
                        break
                    text = line.decode("utf-8", "replace") if isinstance(line, bytes) else str(line)
                cleaned = strip_ansi(text)
                if cleaned:
                    self._publish(session, cleaned)
                else:
                    await asyncio.sleep(0.02)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("agy reader failed for %s", session.key)
        finally:
            if session.state == "BUSY":
                self._schedule(self._on_task_complete(session))

    def _publish(self, session: AgySession, text: str) -> None:
        session.last_output_at = time.monotonic()
        if session.state == "BUSY" and text.strip():
            session.output_since_prompt = True
        for line in text.splitlines():
            if line.strip():
                session.buffer.append(line)
        for queue in list(session.subscribers):
            try:
                queue.put_nowait(text)
            except asyncio.QueueFull:
                pass

    def _append(self, session: AgySession, text: str) -> None:
        self._publish(session, text)

    def _write(self, session: AgySession, payload: str) -> None:
        if session.pty is not None:
            session.pty.write(payload)
            return
        if session.process is None or session.process.stdin is None:
            raise AgyError("Session has no writable process")
        stream = session.process.stdin
        buffer = getattr(stream, "buffer", stream)
        buffer.write(payload.encode("utf-8"))
        buffer.flush()

    def send_raw_input(self, key: str, payload: str) -> dict[str, Any]:
        session = self.find_session(key)
        if session is None:
            raise AgyError(f"No active Antigravity session: {key}")
        if not payload.endswith(("\n", "\r")):
            payload += "\r\n"
        self._write(session, payload)
        if payload.strip().startswith("/"):
            session.last_slash_command = payload.strip().split()[0]
        return {
            "session": session.to_dict(),
            "recent_output": session.recent(40),
        }

    def send_prompt(self, key: str, prompt: str) -> dict[str, Any]:
        session = self.find_session(key)
        if session is None:
            raise AgyError(f"No active Antigravity session: {key}")
        prompt = prompt.strip()
        if not prompt:
            raise AgyError("Prompt is empty")
        with self._lock:
            session.state = "BUSY"
            session.last_prompt = prompt
            session.pending_prompt = prompt
            session.task_serial += 1
            session.output_since_prompt = False
            session.last_output_at = time.monotonic()
        self._write(session, prompt + "\r\n")
        if session.monitor_task and not session.monitor_task.done():
            session.monitor_task.cancel()
        session.monitor_task = self._schedule(self._await_quiet(session))
        return {
            "session": session.to_dict(),
            "recent_output": session.recent(20),
        }

    async def _await_quiet(self, session: AgySession) -> None:
        serial = session.task_serial
        deadline = time.monotonic() + 60 * 60
        try:
            while time.monotonic() < deadline:
                await asyncio.sleep(0.25)
                if session.task_serial != serial or session.state != "BUSY":
                    return
                if not session.output_since_prompt:
                    continue
                quiet_for = time.monotonic() - session.last_output_at
                if quiet_for >= settings.agy_quiet_window_seconds:
                    await self._on_task_complete(session)
                    return
        except asyncio.CancelledError:
            raise

    async def _on_task_complete(self, session: AgySession) -> None:
        with self._lock:
            if session.state != "BUSY":
                return
            session.state = "IDLE"
        session.pending_prompt = ""
        report = await asyncio.to_thread(self._git_report, session.directory)
        session.last_diff_stat = report["diff_stat"]
        session.last_diff = report["diff"]
        summary = report["summary"]
        session.last_summary = summary
        self._append(session, f"\n[iris] Task complete. {summary}\n")

        payload = {
            "session_key": session.key,
            "alias": session.alias,
            "directory": session.directory,
            "prompt": session.last_prompt,
            "summary": summary,
            "files_modified": report["files_modified"],
            "insertions": report["insertions"],
            "deletions": report["deletions"],
            "diff_stat": report["diff_stat"],
            "diff": report["diff"][:8000],
            "completed_at": _now_iso(),
        }
        await self._store_coding_memory(session, payload)
        await self._broadcast_completion(payload)
        if settings.agy_auto_voice and settings.agy_tts_enabled:
            await self._announce(session, summary)

    # -- git harvesting ----------------------------------------------------

    def _git_report(self, directory: str) -> dict[str, Any]:
        fallback = {
            "summary": "Workspace is not a git repository.",
            "files_modified": 0,
            "insertions": 0,
            "deletions": 0,
            "diff_stat": "",
            "diff": "",
        }
        if not Path(directory).is_dir() or shutil.which("git") is None:
            return fallback

        def run(*args: str) -> str:
            try:
                completed = subprocess.run(
                    ["git", "-C", directory, *args],
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=12,
                    creationflags=0x08000000 if os.name == "nt" else 0,
                )
            except (OSError, subprocess.SubprocessError):
                return ""
            return completed.stdout.strip()

        status = run("status", "--short")
        if not status and not (Path(directory) / ".git").exists():
            return fallback
        diff_stat = run("diff", "--stat")
        diff = run("diff")
        match = STAT_RE.search(diff_stat)
        files = int(match.group(1)) if match else len([line for line in status.splitlines() if line.strip()])
        insertions = int(match.group(2) or 0) if match else 0
        deletions = int(match.group(3) or 0) if match else 0
        if not match:
            for line in diff_stat.splitlines():
                short = re.search(r"(\d+) insertions?\(\+\)", line)
                if short:
                    insertions += int(short.group(1))
                short = re.search(r"(\d+) deletions?\(-\)", line)
                if short:
                    deletions += int(short.group(1))
        if files:
            summary = f"Modified {files} file{'s' if files != 1 else ''} (+{insertions}/-{deletions})."
        else:
            summary = "No file changes detected."
        return {
            "summary": summary,
            "files_modified": files,
            "insertions": insertions,
            "deletions": deletions,
            "diff_stat": diff_stat,
            "diff": diff,
        }

    # -- side effects ------------------------------------------------------

    async def _store_coding_memory(self, session: AgySession, payload: dict[str, Any]) -> None:
        def store() -> None:
            from app.core.database import SessionLocal
            from app.core.security import get_current_user
            from app.services.memory_service import memory_service

            db = SessionLocal()
            try:
                user = get_current_user(db)
                key = f"agy:{session.alias}:{int(time.time())}"
                memory_service.store_memory(
                    db,
                    user,
                    content=json.dumps(payload, ensure_ascii=False),
                    category="coding_session",
                    key=key,
                    importance=0.75,
                    source="AGENT_TOOL",
                )
            finally:
                db.close()

        try:
            await asyncio.to_thread(store)
        except Exception:
            logger.warning("Failed storing agy coding memory", exc_info=True)

    async def _broadcast_completion(self, payload: dict[str, Any]) -> None:
        try:
            from app.core.database import SessionLocal
            from app.core.security import get_current_user
            from app.services import mesh_service
            from app.services import mesh_relay_service

            message = mesh_service.MeshMessage(
                type="AGY_TASK_COMPLETED",
                sender_device=LOCAL_AGENT_ID,
                payload=payload,
            )
            await mesh_service.hub.broadcast(message, exclude_sender=False)

            def relay() -> None:
                db = SessionLocal()
                try:
                    user = get_current_user(db)
                    mesh_relay_service.push_relay_message(
                        db,
                        user.id,
                        LOCAL_AGENT_ID,
                        None,
                        "AGY_COMPLETION_CARD",
                        payload,
                    )
                finally:
                    db.close()

            await asyncio.to_thread(relay)
        except Exception:
            logger.warning("Failed broadcasting agy completion", exc_info=True)

    async def _announce(self, session: AgySession, summary: str) -> None:
        try:
            from app.ai.voice import get_text_to_speech

            tts = get_text_to_speech()
            if tts is None:
                return
            audio = await tts.synthesize(
                f"Antigravity finished in {session.alias}. {summary}"
            )
            if "wav" in audio.mime_type.lower():
                await asyncio.to_thread(self._play_audio, audio.data)
        except Exception:
            logger.debug("agy voice announcement failed", exc_info=True)

    @staticmethod
    def _play_audio(data: bytes) -> None:
        if os.name != "nt" or not data:
            return
        import tempfile

        path = Path(tempfile.gettempdir()) / f"iris_agy_{int(time.time() * 1000)}.wav"
        path.write_bytes(data)
        try:
            import winsound

            winsound.PlaySound(str(path), winsound.SND_FILENAME)
        except Exception:
            logger.debug("winsound playback failed", exc_info=True)
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    # -- read API ----------------------------------------------------------

    def list_sessions(self) -> list[dict[str, Any]]:
        return [session.to_dict() for session in self.active_sessions.values()]

    def status(self, key: str | None = None) -> dict[str, Any]:
        session = self.find_session(key)
        if session is None:
            return {"active": False, "sessions": self.list_sessions()}
        return {
            "active": True,
            "session": session.to_dict(),
            "recent_output": session.recent(80),
        }

    def recent_output(self, key: str | None = None, lines: int = 80) -> str:
        session = self.find_session(key)
        return session.recent(lines) if session else ""

    async def stream_output(
        self, key: str, backlog_lines: int = 80
    ) -> AsyncGenerator[str, None]:
        session = self.find_session(key)
        if session is None:
            raise AgyError(f"No active Antigravity session: {key}")
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=512)
        backlog = session.recent(backlog_lines)
        if backlog:
            yield backlog
        session.subscribers.append(queue)
        try:
            while session.alive or not queue.empty():
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ""
                    continue
                yield chunk
        finally:
            if queue in session.subscribers:
                session.subscribers.remove(queue)


agy_manager = AgySessionManager()
