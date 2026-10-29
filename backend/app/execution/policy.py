"""Security, permission classification, path validation, and secret redaction."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.execution.contracts import PermissionClass

# --- Secret Redaction Patterns -----------------------------------------------

SECRET_PATTERNS = [
    # Google API Key
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    # OpenAI / Anthropic / Generic API Keys
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"github_pat_[a-zA-Z0-9_]{30,}"),
    # Bearer tokens
    re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}"),
    # Environment assignments with secrets
    re.compile(r"(?i)(api[_-]?key|secret|password|token|auth_token)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?"),
]


def redact_secrets(text: str) -> str:
    """Scrub known secret formats and credential assignments from model/log strings."""
    if not text:
        return text
    redacted = text
    for pattern in SECRET_PATTERNS:
        # If it has capture groups (like assignment), mask the second group
        if pattern.groups == 2:
            redacted = pattern.sub(r"\1=[REDACTED_SECRET]", redacted)
        else:
            redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


# --- Dangerous & Sensitive Command Rules --------------------------------------

# Class D: Strictly Privileged or Destructive (Blocked or extreme authorization)
CLASS_D_PATTERNS = [
    re.compile(r"\b(?:runas|takeown|icacls\s+.*\/grant|net\s+user|net\s+localgroup)\b", re.I),
    re.compile(r"\bformat\s+[a-z]:", re.I),
    re.compile(r"\b(?:rmdir\s+\/s\s+\/q\s+[c-z]:\\|del\s+\/[sfq]+\s+[c-z]:\\)", re.I),
    re.compile(r"\bRemove-Item\s+.*-Recurse\s+.*-Force\s+[c-z]:\\", re.I),
    re.compile(r"\b(?:reg\s+(?:add|delete)|bcdedit|vssadmin\s+delete)\b", re.I),
    re.compile(r"\b(?:Set-ExecutionPolicy\s+Unrestricted|Disable-WindowsOptionalFeature)\b", re.I),
    re.compile(r"\btaskkill\s+.*\/im\s+(?:csrss|lsass|svchost|services|smss|wininit|winlogon)\.exe\b", re.I),
]

# Class C: Sensitive (Modifies packages, force git, deletes non-scratch files)
CLASS_C_PATTERNS = [
    re.compile(r"\b(?:pip\s+install|npm\s+install|yarn\s+add|choco\s+install|winget\s+install)\b", re.I),
    re.compile(r"\bgit\s+(?:reset\s+--hard|clean\s+-[a-z]*f|push\s+.*--force)\b", re.I),
    re.compile(r"\b(?:netsh|route\s+(?:add|delete))\b", re.I),
    re.compile(r"\b(?:del\s+|rmdir\s+|Remove-Item\s+)", re.I),
]

# Class A: Read-Only inspection commands
CLASS_A_PATTERNS = [
    re.compile(r"^\s*(?:dir|ls|Get-ChildItem|gci)\b", re.I),
    re.compile(r"^\s*git\s+(?:status|log|diff|branch|show)\b", re.I),
    re.compile(r"^\s*(?:Get-Process|tasklist|ps)\b", re.I),
    re.compile(r"^\s*(?:netstat|Get-NetTCPConnection)\b", re.I),
    re.compile(r"^\s*(?:type|cat|Get-Content|gc)\b", re.I),
    re.compile(r"^\s*echo\b", re.I),
    re.compile(r"^\s*(?:python\s+--version|node\s+-v|git\s+--version)\b", re.I),
]

# Class B: Routine reversible actions (tests, builds, dev server, app launch)
CLASS_B_PATTERNS = [
    re.compile(r"\b(?:pytest|npm\s+test|python\s+-m\s+pytest|python\s+-m\s+unittest)\b", re.I),
    re.compile(r"\b(?:npm\s+run\s+(?:dev|build|preview)|uvicorn|python\s+run_daemon\.py)\b", re.I),
    re.compile(r"\bgit\s+(?:checkout|switch|commit|add|status|pull|fetch)\b", re.I),
    re.compile(r"\bpython\s+(?:-m\s+py_compile|[a-zA-Z0-9_\-\.\/\\]+\.py)\b", re.I),
]


class ExecutionPolicy:
    """Policy engine enforcing permission classes, path security, and approvals."""

    def __init__(
        self,
        allowed_roots: list[Path] | None = None,
        require_approval_for_class_c: bool | None = None,
        block_class_d: bool | None = None,
    ) -> None:
        try:
            from app.core.config import settings
            default_c = getattr(settings, "desktop_cli_require_approval_for_class_c", True)
            default_d = getattr(settings, "desktop_cli_block_class_d", True)
        except Exception:
            default_c = True
            default_d = True

        workspace_root = Path(r"C:\kirtan\IRIS").resolve()
        user_home = Path.home().resolve()
        self.allowed_roots = allowed_roots or [
            workspace_root,
            user_home / "Desktop",
            user_home / "Downloads",
            user_home / "Documents",
            user_home / ".gemini",
            user_home / "AppData" / "Local" / "Temp",
        ]
        self.require_approval_for_class_c = (
            require_approval_for_class_c if require_approval_for_class_c is not None else default_c
        )
        self.block_class_d = (
            block_class_d if block_class_d is not None else default_d
        )
        self._approvals: dict[str, dict[str, Any]] = {}

    def validate_path(self, path: Path | str, write: bool = False) -> tuple[bool, str | None]:
        """Verify that the path is inside approved boundaries and not in system critical roots."""
        try:
            resolved = Path(path).resolve()
        except Exception as exc:
            return False, f"Invalid path syntax: {exc}"

        path_str = str(resolved).lower()

        # Reject Windows system roots for modification
        if write:
            forbidden_write_prefixes = [
                r"c:\windows",
                r"c:\program files",
                r"c:\program files (x86)",
                r"c:\programdata\microsoft",
            ]
            for prefix in forbidden_write_prefixes:
                if path_str.startswith(prefix):
                    return False, f"Path '{resolved}' is in a protected system directory and cannot be modified."

        # Check against allowed roots
        is_allowed = any(
            resolved == root or root in resolved.parents
            for root in self.allowed_roots
        )
        if not is_allowed:
            return False, f"Path '{resolved}' is outside approved workspace roots."

        return True, None

    def classify_command(
        self,
        command: str | list[str],
        cwd: str | None = None,
        capability: str = "shell_command",
    ) -> tuple[PermissionClass, str]:
        """Determine permission category and explanation for a command."""
        cmd_str = " ".join(command) if isinstance(command, list) else command.strip()

        # 1. Capability-specific classification
        if capability in ("read_file", "list_files", "search_files", "inspect_process"):
            return PermissionClass.CLASS_A_READ_ONLY, "Read-only inspection capability."

        if capability in ("launch_app", "open_file"):
            return PermissionClass.CLASS_B_ROUTINE, "Routine application launch."

        # 2. Check for Class D (Privileged/Destructive)
        for pattern in CLASS_D_PATTERNS:
            if pattern.search(cmd_str):
                return PermissionClass.CLASS_D_DESTRUCTIVE, "Privileged or potentially destructive system command."

        # 3. Check for Class C (Sensitive)
        for pattern in CLASS_C_PATTERNS:
            if pattern.search(cmd_str):
                return PermissionClass.CLASS_C_SENSITIVE, "Modifies packages, network, or persistent files."

        # 4. Check for Class A (Read-only shell)
        for pattern in CLASS_A_PATTERNS:
            if pattern.search(cmd_str):
                return PermissionClass.CLASS_A_READ_ONLY, "Safe read-only shell inspection."

        # 5. Check for Class B (Routine reversible)
        for pattern in CLASS_B_PATTERNS:
            if pattern.search(cmd_str):
                return PermissionClass.CLASS_B_ROUTINE, "Routine development or automation command."

        # Default fallback: Class B for general safe user commands
        return PermissionClass.CLASS_B_ROUTINE, "Standard user-level shell operation."

    def _command_hash(self, command: str | list[str], cwd: str | None) -> str:
        cmd_str = " ".join(command) if isinstance(command, list) else command.strip()
        work_dir = (cwd or "").strip().lower()
        key = f"{cmd_str.lower()}|{work_dir}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def issue_approval_token(
        self,
        command: str | list[str],
        cwd: str | None,
        permission_class: PermissionClass,
        ttl_seconds: float = 300.0,
    ) -> tuple[str, str]:
        """Issue a single-use cryptographically bound approval token."""
        token = f"appr_{secrets.token_hex(16)}"
        cmd_hash = self._command_hash(command, cwd)
        now = time.time()
        cmd_str = " ".join(command) if isinstance(command, list) else command.strip()

        self._approvals[token] = {
            "token": token,
            "cmd_hash": cmd_hash,
            "command": cmd_str,
            "cwd": cwd,
            "permission_class": permission_class,
            "created_at": now,
            "expires_at": now + ttl_seconds,
            "consumed": False,
        }

        prompt = (
            f"⚠️ **Approval Required ({permission_class.value})**\n"
            f"IRIS is requesting permission to execute:\n"
            f"```powershell\n{cmd_str}\n```\n"
            f"Working directory: `{cwd or 'C:\\kirtan\\IRIS'}`\n"
            f"Approval Token: `{token}` (Expires in {int(ttl_seconds / 60)}m).\n"
            f"To authorize, reply: `approve {token}`"
        )
        return token, prompt

    def verify_and_consume_token(
        self,
        token: str | None,
        command: str | list[str],
        cwd: str | None,
    ) -> tuple[bool, str]:
        """Validate that token matches exact command and working directory, is unconsumed, and not expired."""
        if not token:
            return False, "No approval token provided."

        record = self._approvals.get(token)
        if not record:
            return False, "Approval token is invalid or does not exist."

        if record.get("consumed"):
            return False, "Approval token has already been consumed (replay attempt rejected)."

        if time.time() > record.get("expires_at", 0):
            return False, "Approval token has expired."

        expected_hash = self._command_hash(command, cwd)
        if record.get("cmd_hash") != expected_hash:
            return False, "Approval token argument mismatch: command or directory was modified."

        # Mark consumed immediately
        record["consumed"] = True
        return True, "Approval token verified and consumed successfully."


# Default global policy instance
default_policy = ExecutionPolicy()
