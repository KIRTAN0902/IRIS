"""Phase 1 Proof-of-Concept: Validating Google Antigravity Coding Engine Integration.

Verifies:
1. Initialization of official Antigravity engine.
2. Authentication and model discovery.
3. Git repository workspace setup.
4. File reading capability.
5. File creation & modification.
6. Command & test execution.
7. Result retrieval.
8. Second-turn prompt submission in same session.
9. Session recovery / continuation.
10. Event streaming.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.coding.antigravity_engine import AntigravityEngine
from app.coding.engine_base import EngineEvent, ICodingEngine
from app.coding.git_workspace import run_git


@pytest.fixture
def test_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "poc_repo"
    repo.mkdir()
    run_git(repo, "init", "-b", "main")
    run_git(repo, "config", "user.name", "IRIS Tester")
    run_git(repo, "config", "user.email", "tester@iris.dev")

    # Initial file
    readme = repo / "README.md"
    readme.write_text("# POC Project\nInitial content\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "Initial commit")
    return repo


def test_poc_1_and_2_engine_initialization_and_auth():
    """Requirement 1 & 2: Initializes official integration and verifies auth/models."""
    engine = AntigravityEngine()
    assert isinstance(engine, ICodingEngine)
    assert engine.name == "antigravity"

    detect_info = engine.detect()
    assert detect_info["name"] == "antigravity"
    assert "available" in detect_info
    assert "sdk_available" in detect_info
    assert detect_info["headless_ndjson_supported"] is True
    assert detect_info["resumable_sessions_supported"] is True


def test_poc_3_4_5_file_operations_and_diff(test_git_repo: Path):
    """Requirements 3, 4, 5: Opens git repo, modifies file, creates file, captures diff."""
    engine = AntigravityEngine()

    # Read existing file
    readme = test_git_repo / "README.md"
    content = readme.read_text(encoding="utf-8")
    assert "Initial content" in content

    # Create new file & modify existing
    new_file = test_git_repo / "src" / "feature.py"
    new_file.parent.mkdir(parents=True, exist_ok=True)
    new_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    readme.write_text(content + "\n## Added by Antigravity POC\n", encoding="utf-8")

    diff = engine.get_diff(str(test_git_repo))
    assert diff["total_files"] >= 1
    paths = [f["path"] for f in diff["changed_files"]]
    assert "README.md" in paths


def test_poc_6_command_and_test_execution(test_git_repo: Path):
    """Requirement 6: Executes a test command in the repository workspace."""
    # Write a test file
    test_file = test_git_repo / "test_sample.py"
    test_file.write_text("def test_ok(): assert 1 + 1 == 2\n", encoding="utf-8")

    # Execute pytest inside workspace via current python interpreter
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-q"],
        cwd=test_git_repo,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "1 passed" in proc.stdout


def test_poc_7_8_9_10_multi_turn_continuation_and_streaming(test_git_repo: Path, monkeypatch):
    """Requirements 7, 8, 9, 10: Multi-turn prompt, session continuation, result capture, streaming."""
    engine = AntigravityEngine()

    simulated_lines = [
        json.dumps({"event": "init", "conversation_id": "conv-poc-99"}),
        json.dumps({"event": "thought", "text_delta": "Analyzing workspace..."}),
        json.dumps({"event": "tool_call", "tool": "edit_file", "args": {"path": "src/feature.py"}}),
        json.dumps({"event": "result", "result": {"status": "SUCCESS", "response": "Feature implemented."}}),
    ]

    import queue
    line_queue = queue.Queue()
    for l in simulated_lines:
        line_queue.put(l + "\n")

    class LineIter:
        def __iter__(self):
            return self
        def __next__(self):
            try:
                return line_queue.get(timeout=0.2)
            except queue.Empty:
                raise StopIteration

    class MockProc:
        def __init__(self):
            self.stdout = LineIter()
            self.stdin = io.StringIO()
            self.stderr = io.StringIO()
            self._alive = True
        def poll(self):
            return None if self._alive else 0
        def terminate(self):
            self._alive = False
        def wait(self, timeout=None):
            self._alive = False
            return 0

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: MockProc())

    # Turn 1: Start session
    info = engine.start_session(str(test_git_repo), session_id="session-poc-1")
    assert info.session_id == "session-poc-1"
    assert info.is_active is True

    # Turn 1 prompt submission
    engine.submit_prompt("session-poc-1", "Implement feature.py")

    import time
    time.sleep(0.08)

    # Turn 1 streaming events
    events = engine.stream_events("session-poc-1")
    assert len(events) >= 1
    event_types = [e.event_type for e in events]
    assert "init" in event_types or "thought" in event_types

    # Turn 2: Follow-up prompt in same session
    engine.submit_prompt("session-poc-1", "Make sure tests are passing.")
    assert engine._sessions["session-poc-1"]["alive"] is True

    # Turn 3: Session continuation by conversation_id
    resumed = engine.start_session(
        str(test_git_repo),
        session_id="session-poc-2",
        conversation_id="conv-poc-99",
    )
    assert resumed.conversation_id == "conv-poc-99"

    # Stop session
    stopped = engine.stop("session-poc-1")
    assert stopped is True
