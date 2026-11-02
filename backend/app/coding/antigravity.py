"""Antigravity CLI adapter over IRIS's existing persistent terminal bridge."""
from __future__ import annotations
import shutil, subprocess
from typing import Any
from app.coding.contracts import AgentCapabilities
from app.services.agy_bridge import agy_manager, _command_argv, AgyError
from app.coding.headless import headless_manager

class AntigravityCLIAdapter:
    agent_id = "antigravity-cli"
    capabilities = AgentCapabilities(interactive=False,prompt_submission=True,streaming_output=True,resume=True,stop=True,follow_up=True,structured_events=True)

    def detect(self) -> dict[str, Any]:
        argv=_command_argv(); path=shutil.which(argv[0]) if argv else None
        version=None
        if path:
            try: version=subprocess.run([path,"--version"],capture_output=True,text=True,timeout=5).stdout.strip()
            except (OSError,subprocess.SubprocessError): pass
        return {"id":self.agent_id,"name":"Antigravity CLI","available":bool(path),"path":path,"version":version,"capabilities":self.capabilities.model_dump()}

    def launch(self,directory:str,prompt:str,session_id:str,permissions:dict[str,Any]|None=None) -> Any:
        try:return headless_manager.launch(directory,session_id,prompt,permission_rules=permissions)
        except Exception as exc:raise AgyError(str(exc)) from exc

    def send_prompt(self,session_id:str,prompt:str) -> Any:
        session=headless_manager.get(session_id)
        if not session:raise AgyError("Antigravity session process is not available")
        session.send(prompt);return session.snapshot()

    def resume_session(self,session_id:str) -> Any:
        session=agy_manager.find_session(session_id)
        if not session or not session.alive:
            raise AgyError("Session is not active; use resume_project_session for workspace-scoped CLI continuation")
        return session

    def resume_session(self,directory:str,conversation_id:str,alias:str="workspace",permissions:dict[str,Any]|None=None) -> Any:
        try:return headless_manager.launch(directory,alias,"",conversation_id=conversation_id,permission_rules=permissions)
        except Exception as exc:raise AgyError(str(exc)) from exc

    def resume_session_id(self,directory:str,alias:str,conversation_id:str,permissions:dict[str,Any]|None=None) -> Any:
        return self.resume_session(directory,conversation_id,alias,permissions)

    def get_status(self,session_id:str) -> dict[str,Any]:
        session=headless_manager.get(session_id)
        snapshot=session.snapshot() if session else None
        return {"active":bool(snapshot and snapshot.get("alive")),"session":snapshot}
    def get_output(self,session_id:str) -> str:
        session=headless_manager.get(session_id)
        return session.snapshot()["recent_output"] if session else ""
    def stop(self,session_id:str) -> bool: return headless_manager.stop(session_id)

class CodingAgentRegistry:
    def __init__(self): self._adapters={}
    def register(self,adapter): self._adapters[adapter.agent_id]=adapter
    def get(self,agent_id:str): return self._adapters.get(agent_id)
    def discover(self): return [a.detect() for a in self._adapters.values()]

from app.coding.adapters.codex_adapter import CodexCLIAdapter

coding_agents=CodingAgentRegistry()
coding_agents.register(AntigravityCLIAdapter())
coding_agents.register(CodexCLIAdapter())
