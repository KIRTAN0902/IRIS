"""Tests for Codex CLI adapter and headless session manager."""
import io
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

from app.coding.adapters.codex_adapter import (
    CodexCLIAdapter,
    CodexHeadlessSession,
    codex_headless_manager,
)


def test_codex_adapter_capabilities():
    adapter = CodexCLIAdapter()
    assert adapter.agent_id == "codex-cli"
    det = adapter.detect()
    assert det["id"] == "codex-cli"
    assert "capabilities" in det
    assert det["capabilities"]["structured_events"] is True
    assert det["capabilities"]["resume"] is True


def test_codex_headless_session_jsonl_events():
    jsonl_data = (
        '{"type":"thread.started","thread_id":"thread-abc-123"}\n'
        '{"type":"turn.started"}\n'
        '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"Refactoring complete"}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":100,"output_tokens":20}}\n'
    )

    class MockProc:
        stdout = io.StringIO(jsonl_data)
        stderr = io.StringIO("")
        def poll(self): return 0
        def wait(self): return 0

    session = CodexHeadlessSession("codex-test-key", ".", "test-alias", MockProc())
    for _ in range(50):
        if len(session.events) >= 4:
            break
        time.sleep(0.02)

    snap = session.snapshot()
    assert snap["conversation_id"] == "thread-abc-123"
    assert snap["state"] == "IDLE"
    assert snap["last_result"]["status"] == "SUCCESS"
    assert "Refactoring complete" in snap["recent_output"]


def test_codex_headless_session_failure_on_error():
    jsonl_data = '{"type":"thread.started","thread_id":"thread-err-1"}\n'

    class MockErrProc:
        stdout = io.StringIO(jsonl_data)
        stderr = io.StringIO("Fatal error: connection dropped")
        def poll(self): return 1
        def wait(self): return 1

    session = CodexHeadlessSession("codex-err-key", ".", "test-alias", MockErrProc())
    time.sleep(0.1)

    snap = session.snapshot()
    assert snap["state"] == "FAILED"
    assert snap["last_result"]["status"] == "ERROR"
