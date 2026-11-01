from __future__ import annotations
import json
import io
from app.services.agy_bridge import _command_argv

def test_governed_argv_keeps_review_and_workspace_boundaries(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings,"agy_cli_command","agy")
    argv=_command_argv(governed=True)
    config=json.loads(argv[argv.index("--settings")+1])
    assert config["toolPermission"]=="request-review"
    assert config["enableTerminalSandbox"] is True
    assert config["allowNonWorkspaceAccess"] is False
    assert "--sandbox" in argv
    assert "--dangerously-skip-permissions" not in argv

def test_resume_uses_verified_continue_flag(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings,"agy_cli_command","agy")
    assert "--continue" in _command_argv(resume=True)

def test_headless_ndjson_events_capture_conversation_and_result():
    from app.coding.headless import HeadlessSession
    class Proc:
        stdout=io.StringIO('{"event":"init","conversation_id":"conversation-1"}\n{"event":"step_update","step_update":{"state":"DONE","step_type":"agent_response","text_delta":"done"}}\n{"event":"result","result":{"status":"SUCCESS","response":"done"}}\n')
        stderr=io.StringIO("")
        def poll(self):return 0
        def wait(self):return 0
    session=HeadlessSession("task-session",".","fixture",Proc())
    import time
    for _ in range(100):
        if len(session.events)>=3:break
        time.sleep(.01)
    snap=session.snapshot()
    assert snap["conversation_id"]=="conversation-1"
    assert snap["state"]=="IDLE"
    assert snap["last_result"]["status"]=="SUCCESS"
    assert "done" in snap["recent_output"]

def test_headless_argv_forces_safe_ndjson_policy(monkeypatch):
    from app.coding.headless import AntigravityHeadlessManager
    from app.core.config import settings
    monkeypatch.setattr(settings,"agy_cli_command","agy --dangerously-skip-permissions")
    argv=AntigravityHeadlessManager()._argv()
    cfg=json.loads(argv[argv.index("--settings")+1])
    assert "--dangerously-skip-permissions" not in argv
    assert argv[argv.index("--input-format")+1]=="stream-json"
    assert argv[argv.index("--output-format")+1]=="stream-json"
    assert cfg["toolPermission"]=="request-review"
    assert cfg["allowNonWorkspaceAccess"] is False
    assert "read_url(*)" in cfg["permissions"]["deny"]

def test_headless_project_permissions_are_narrow():
    from app.coding.headless import AntigravityHeadlessManager
    argv=AntigravityHeadlessManager()._argv(permission_rules={"allowed_commands":["command(git)"],"allowed_domains":["pypi.org"],"network_access":True})
    cfg=json.loads(argv[argv.index("--settings")+1])
    assert cfg["permissions"]["allow"]==["command(git)","read_url(pypi.org)","execute_url(pypi.org)"]
    assert not cfg["permissions"]["deny"]
