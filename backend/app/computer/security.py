"""Security policy, action risk classification, and confirmation management for Computer Control."""

from __future__ import annotations

import re
import secrets
import time
from typing import Any

from app.computer.contracts import ActionRiskLevel, ComputerAction, ComputerActionType
from app.core.logging import get_logger

logger = get_logger("iris.computer.security")

# Sensitive commands and destructive patterns
DESTRUCTIVE_PATTERNS = [
    re.compile(r"(?i)\bformat\s+[a-z]:"),
    re.compile(r"(?i)\b(del|rmdir|rm|Remove-Item)\s+.*([a-z]:\\windows|[a-z]:\\system32|/system|/\*|\bc:\\)"),
    re.compile(r"(?i)\b(reg\s+delete|vssadmin\s+delete|bcdedit|diskpart)\b"),
    re.compile(r"(?i)\b(netsh\s+firewall\s+set\s+opmode\s+disable|Set-NetFirewallProfile.*-Enabled\s+False)\b"),
]

SENSITIVE_PATTERNS = [
    re.compile(r"(?i)\b(Stop-Service|Restart-Service|Set-Service|sc\s+stop|taskkill)\b"),
    re.compile(r"(?i)\b(Remove-Item|del|rmdir|rm)\b"),
    re.compile(r"(?i)\b(send-mail|send_email|sendmail|smtp)\b"),
    re.compile(r"(?i)\b(curl|wget|Invoke-WebRequest|Invoke-RestMethod).*(checkout|payment|order|purchase|buy)\b"),
    re.compile(r"(?i)\b(net\s+user|passwd|password)\b"),
    re.compile(r"(?i)\b(pip\s+install|npm\s+install|choco\s+install|winget\s+install)\b"),
    re.compile(r"(?i)\b(runas|Start-Process.*-Verb\s+RunAs)\b"),
]


class ComputerSecurityPolicy:
    """Classifies risk, manages approval tokens, and enforces safety bounds on computer actions."""

    def __init__(self) -> None:
        self._pending_approvals: dict[str, dict[str, Any]] = {}

    def classify_action(self, action: ComputerAction) -> tuple[ActionRiskLevel, str | None]:
        """Classify the risk level of an action before execution."""
        atype = action.action_type
        params = action.params

        # 1. Shell commands inspection
        if atype == ComputerActionType.SHELL_EXECUTE:
            cmd = str(params.get("command", ""))
            for pat in DESTRUCTIVE_PATTERNS:
                if pat.search(cmd):
                    return ActionRiskLevel.DESTRUCTIVE, f"Command contains prohibited destructive pattern: {cmd[:60]}"
            for pat in SENSITIVE_PATTERNS:
                if pat.search(cmd):
                    return ActionRiskLevel.SENSITIVE, f"Command requires confirmation: {cmd[:60]}"
            return ActionRiskLevel.ORDINARY, None

        # 2. File deletion inspection
        if atype == ComputerActionType.FILE_DELETE:
            path = str(params.get("path", "")).lower()
            if any(crit in path for crit in ["windows", "system32", "program files", "appdata"]):
                return ActionRiskLevel.DESTRUCTIVE, "Deletion of system directory is prohibited."
            return ActionRiskLevel.SENSITIVE, f"File deletion requires confirmation: {path}"

        # 3. Process kill inspection
        if atype == ComputerActionType.PROCESS_KILL:
            name = str(params.get("name", "")).lower()
            pid = params.get("pid")
            if any(crit in name for crit in ["explorer", "csrss", "lsass", "smss", "winlogon"]):
                return ActionRiskLevel.DESTRUCTIVE, f"Terminating critical OS process '{name}' is prohibited."
            return ActionRiskLevel.ORDINARY, None

        # 4. Routine GUI & observation actions
        return ActionRiskLevel.ORDINARY, None

    def issue_approval_token(self, action: ComputerAction, reason: str, ttl_seconds: float = 300.0) -> str:
        """Generate a single-use authorization token for a sensitive action with expiration."""
        token = f"appr_{secrets.token_hex(16)}"
        self._pending_approvals[token] = {
            "action_type": action.action_type.value,
            "params": dict(action.params),
            "reason": reason,
            "created_at": time.time(),
            "expires_at": time.time() + ttl_seconds,
        }
        return token

    def verify_and_consume_token(self, token: str, action: ComputerAction) -> bool:
        """Verify and immediately invalidate a single-use approval token.
        
        Enforces single-use, TTL expiration (default 5m), action type match,
        and parameter exact matching to prevent parameter tampering or token reuse.
        """
        pending = self._pending_approvals.pop(token, None)
        if not pending:
            return False

        # Expiry check
        if time.time() > pending.get("expires_at", 0):
            logger.warning("Approval token %s expired.", token)
            return False

        # Action type check
        if pending["action_type"] != action.action_type.value:
            logger.warning("Approval token %s action type mismatch: %s != %s", token, pending["action_type"], action.action_type.value)
            return False

        # Parameter binding check
        if pending["params"] != action.params:
            logger.warning("Approval token %s params mismatch (potential tampering).", token)
            return False

        return True


# Singleton policy instance
security_policy = ComputerSecurityPolicy()
