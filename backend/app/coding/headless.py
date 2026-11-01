"""Managed Antigravity headless sessions using the documented NDJSON protocol."""
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

from app.core.config import settings

SECRET_ENV = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH)", re.I)

def _scrub(value):
    from app.execution.policy import redact_secrets
    if isinstance(value,str):return redact_secrets(value)
    if isinstance(value,list):return [_scrub(x) for x in value]
    if isinstance(value,dict):return {k:_scrub(v) for k,v in value.items()}
    return value

class HeadlessSession:
    def __init__(self,key:str,directory:str,alias:str,process:subprocess.Popen[str]):
        self.key=key; self.directory=directory; self.alias=alias; self.process=process
        self.conversation_id:str|None=None; self.state="STARTING"; self.last_result:dict[str,Any]|None=None
        self.output=deque(maxlen=max(100,settings.agy_buffer_lines)); self.events=deque(maxlen=1000); self.event_total=0
        self.warnings=deque(maxlen=100); self.needs_attention=False; self.created_at=time.time(); self.updated_at=time.time()
        self.lock=threading.RLock(); self.subscribers:list[Any]=[]
        threading.Thread(target=self._read_stdout,name=f"agy-out-{key[:8]}",daemon=True).start()
        threading.Thread(target=self._read_stderr,name=f"agy-err-{key[:8]}",daemon=True).start()
        threading.Thread(target=self._watch_exit,name=f"agy-wait-{key[:8]}",daemon=True).start()

    def _publish(self,event:dict[str,Any]):
        event=_scrub(event)
        line=json.dumps(event,ensure_ascii=False)
        with self.lock:
            self.events.append(event); self.event_total+=1; self.updated_at=time.time()
            data=event.get("step_update",{})
            delta=data.get("text_delta")
            if delta:self.output.append(str(delta))
            if event.get("event")=="init": self.conversation_id=event.get("conversation_id")
            if event.get("event")=="result":
                self.last_result=event.get("result",{}); status=self.last_result.get("status")
                self.state="WAITING_FOR_USER" if self.needs_attention or status=="WAITING" else ("IDLE" if status=="SUCCESS" else "FAILED")
            for q in list(self.subscribers):
                try:q.put_nowait(line)
                except Exception:pass

    def _read_stdout(self):
        try:
            for line in self.process.stdout:
                try:self._publish(json.loads(line))
                except (json.JSONDecodeError,TypeError):
                    self.warnings.append("Invalid NDJSON event from Antigravity: "+line[:500])
        except Exception as exc:self.warnings.append(f"Output stream failed: {exc}")

    def _read_stderr(self):
        try:
            for line in self.process.stderr:
                value=line.rstrip()
                if value:
                    with self.lock:
                        if "not logged into antigravity" in value.lower() or "authentication required" in value.lower():
                            self.state="FAILED"; self.last_result={"status":"ERROR","error":"Antigravity authentication is required. Sign in with the CLI and retry."}
                            self.warnings.append("Antigravity authentication is required. Sign in with the CLI and retry.")
                            try:self.process.terminate()
                            except OSError:pass
                        if "soft-den" in value.lower() or "permission" in value.lower() and "allow" in value.lower():
                            self.needs_attention=True
                        self.warnings.append(value[:2000]); self.updated_at=time.time()
                        self.output.append("[agent notice] "+_scrub(value))
        except Exception as exc:self.warnings.append(f"Diagnostic stream failed: {exc}")

    def _watch_exit(self):
        code=self.process.wait()
        with self.lock:
            if self.state not in ("FAILED","WAITING_FOR_USER"):
                if self.last_result and self.last_result.get("status")=="SUCCESS": self.state="IDLE"
                else:self.state="INTERRUPTED" if code<0 else "FAILED"
            self.updated_at=time.time()

    def send(self,prompt:str):
        if self.process.poll() is not None:raise RuntimeError("Antigravity session process has exited")
        with self.lock:self.state="BUSY"; self.last_result=None; self.needs_attention=False
        payload={"event":"user","message":{"content":prompt.strip()}}
        try:
            self.process.stdin.write(json.dumps(payload,ensure_ascii=False)+"\n"); self.process.stdin.flush()
        except (OSError,AttributeError) as exc:
            with self.lock:self.state="FAILED"
            raise RuntimeError(f"Could not submit prompt: {exc}") from exc

    def stop(self):
        if self.process.poll() is None:self.process.terminate()

    def snapshot(self):
        with self.lock:
            return {"key":self.key,"alias":self.alias,"directory":self.directory,"state":self.state,
                    "alive":self.process.poll() is None,"created_at":self.created_at,"updated_at":self.updated_at,
                    "conversation_id":self.conversation_id,"last_result":self.last_result,
                    "recent_output":"".join(self.output)[-20000:],"warnings":[_scrub(w) for w in self.warnings],"events":list(self.events),"event_total":self.event_total}

class AntigravityHeadlessManager:
    def __init__(self):self.sessions:dict[str,HeadlessSession]={};self.lock=threading.RLock()

    def _argv(self,conversation_id:str|None=None,permission_rules:dict[str,Any]|None=None):
        from app.services.agy_bridge import _command_argv
        argv=_command_argv()[:]
        if not shutil.which(argv[0]) and not Path(argv[0]).is_file():raise RuntimeError("Antigravity CLI executable was not found")
        # The managed adapter owns transport and security flags; never inherit a
        # configured permission bypass or an output mode that breaks NDJSON.
        value_flags={"--settings","--input-format","--output-format","--conversation","--model","--effort","--agent","--project"}
        kept=[argv[0]]; skip=False
        for arg in argv[1:]:
            if skip:skip=False;continue
            if arg=="--dangerously-skip-permissions":continue
            if arg in value_flags:skip=True;continue
            if any(arg.startswith(flag+"=") for flag in value_flags):continue
            if arg in {"--sandbox","--continue","-c","--print","-p","--prompt","--prompt-interactive","-i"}:continue
            kept.append(arg)
        argv=kept
        config={"toolPermission":"request-review","enableTerminalSandbox":True,"allowNonWorkspaceAccess":False}
        rules=(permission_rules or {}).get("allowed_commands") or []
        domains=(permission_rules or {}).get("allowed_domains") or []
        allow=list(rules)
        deny=[] if (permission_rules or {}).get("network_access") else ["read_url(*)","execute_url(*)"]
        if permission_rules and permission_rules.get("network_access"):
            allow.extend([f"read_url({domain})" for domain in domains])
            allow.extend([f"execute_url({domain})" for domain in domains])
        if allow or deny:config["permissions"]={"allow":allow,"deny":deny}
        argv.extend(["--input-format","stream-json","--output-format","stream-json","--settings",json.dumps(config),"--sandbox"])
        if conversation_id:argv.extend(["--conversation",conversation_id])
        return argv

    def launch(self,directory:str,alias:str,prompt:str,conversation_id:str|None=None,permission_rules:dict[str,Any]|None=None)->HeadlessSession:
        path=Path(directory).resolve()
        if not path.is_dir():raise RuntimeError("Selected project directory does not exist")
        env={k:v for k,v in os.environ.items() if not SECRET_ENV.search(k)}
        proc=subprocess.Popen(self._argv(conversation_id,permission_rules),cwd=str(path),stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,text=True,encoding="utf-8",errors="replace",bufsize=1,env=env,
            creationflags=0x08000000 if os.name=="nt" else 0)
        session=HeadlessSession(str(uuid.uuid4()),str(path),alias,proc)
        with self.lock:self.sessions[session.key]=session
        if prompt:session.send(prompt)
        return session

    def get(self,key:str)->HeadlessSession|None:
        with self.lock:return self.sessions.get(key)

    def list_sessions(self)->list[HeadlessSession]:
        with self.lock:return list(self.sessions.values())

    def stop(self,key:str)->bool:
        session=self.get(key)
        if not session:return False
        session.stop();return True

    def shutdown(self):
        with self.lock:sessions=list(self.sessions.values())
        for session in sessions:session.stop()

headless_manager=AntigravityHeadlessManager()
