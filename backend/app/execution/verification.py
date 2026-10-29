"""Postcondition verification for desktop operations."""

from __future__ import annotations

import re
import socket
from pathlib import Path
from typing import Any

from app.execution.contracts import ExecutionResult


def verify_postcondition(spec: dict[str, Any] | None, result: ExecutionResult) -> tuple[bool, str]:
    """Verify that the intended outcome of a command or action actually occurred."""
    if not spec:
        # Default verification: exit code 0
        if result.exit_code == 0:
            return True, "Command exited cleanly with return code 0."
        return False, f"Command exited with non-zero return code {result.exit_code}."

    v_type = spec.get("type", "").lower()

    # 1. File Exists Verification
    if v_type == "file_exists":
        raw_path = spec.get("path")
        if not raw_path:
            return False, "Verification failed: No file path provided in specification."
        p = Path(raw_path)
        if not p.exists():
            return False, f"Verification failed: Expected file '{p}' was not found."

        min_size = spec.get("min_size_bytes", 0)
        actual_size = p.stat().st_size
        if actual_size < min_size:
            return False, f"Verification failed: File '{p}' exists but size ({actual_size}b) < expected ({min_size}b)."

        contains = spec.get("contains_text")
        if contains:
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                if contains not in content:
                    return False, f"Verification failed: File '{p}' exists but does not contain expected snippet."
            except Exception as e:
                return False, f"Verification failed to read '{p}': {e}"

        return True, f"Verified: File '{p}' exists ({actual_size} bytes)."

    # 2. File Contains Text Verification
    if v_type == "file_contains":
        raw_path = spec.get("path")
        needle = spec.get("text")
        if not raw_path or not needle:
            return False, "Verification failed: 'path' and 'text' are required for file_contains."
        p = Path(raw_path)
        if not p.exists():
            return False, f"Verification failed: File '{p}' does not exist."
        content = p.read_text(encoding="utf-8", errors="replace")
        if needle in content:
            return True, f"Verified: Found expected text in '{p}'."
        return False, f"Verification failed: '{needle}' not found in '{p}'."

    # 3. Port Listening Verification
    if v_type == "port_listening":
        port = spec.get("port")
        host = spec.get("host", "127.0.0.1")
        if not port:
            return False, "Verification failed: No port specified."
        try:
            with socket.create_connection((host, int(port)), timeout=2.0):
                return True, f"Verified: Port {port} on {host} is open and accepting TCP connections."
        except OSError:
            return False, f"Verification failed: Port {port} on {host} is not listening."

    # 4. Output Pattern Verification
    if v_type == "output_contains":
        pattern = spec.get("pattern") or spec.get("text")
        if not pattern:
            return False, "Verification failed: No pattern specified for output_contains."
        combined = f"{result.stdout}\n{result.stderr}"
        if re.search(pattern, combined, re.IGNORECASE):
            return True, f"Verified: Output contains expected pattern '{pattern}'."
        return False, f"Verification failed: Pattern '{pattern}' not matched in stdout/stderr."

    # 5. Exit Code Verification
    if v_type == "exit_code_zero":
        if result.exit_code == 0:
            return True, "Verified: Command exit code is 0."
        return False, f"Verification failed: Exit code is {result.exit_code} (expected 0)."

    return True, "No specific verifier required."
