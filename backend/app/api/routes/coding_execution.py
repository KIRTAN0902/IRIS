"""Governed, persisted coding project and task workflow."""
from __future__ import annotations
import shutil, subprocess, uuid
from datetime import UTC, datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from app.api.deps import current_user
from app.core.database import get_db
from app.models.user import User
from app.models.coding_project import CodingProject
from app.models.coding_task import CodingTaskRecord, CodingSessionRecord
from app.coding.contracts import TaskBrief, TaskStatus, validate_transition
from app.core.execution_provider import require_execution

router = APIRouter(prefix="/coding", tags=["coding-execution"])
task_router = APIRouter(prefix="/coding/execution", tags=["coding-execution"])

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    directory: str
    aliases: list[str] = []
    description: str | None = None

class ProjectUpdate(BaseModel):
    name: str | None = None
    aliases: list[str] | None = None
    description: str | None = None
    read_access: bool | None = None
    write_access: bool | None = None
    command_access: bool | None = None
    allowed_commands: list[str] | None = None
    allowed_domains: list[str] | None = None
    network_access: bool | None = None
    is_active: bool | None = None

    @field_validator("allowed_commands")
    @classmethod
    def validate_command_rules(cls, rules):
        if rules is None:return rules
        if len(rules)>50:raise ValueError("At most 50 command rules are allowed")
        for rule in rules:
            if len(rule)>300 or not rule.startswith("command(") or not rule.endswith(")"):
                raise ValueError("Command permissions must use Antigravity command(...) rule syntax")
        return list(dict.fromkeys(rules))

    @field_validator("allowed_domains")
    @classmethod
    def validate_domains(cls, domains):
        if domains is None:return domains
        import re
        pattern=re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",re.I)
        if len(domains)>50 or any(not pattern.fullmatch(d.strip()) for d in domains):
            raise ValueError("Allowed network entries must be hostnames (for example, pypi.org)")
        return list(dict.fromkeys(d.strip().lower() for d in domains))

class TaskCreate(BaseModel):
    project_id: int
    agent_id: str = "antigravity-cli"
    instruction: str = Field(min_length=3)
    brief: TaskBrief

class ApproveTask(BaseModel):
    prompt: str = Field(min_length=3)

def _project(db, user, ident):
    p = db.query(CodingProject).filter_by(id=ident, user_id=user.id, active=True).first()
    if p is None: raise HTTPException(404, "Coding project not found")
    return p

def _git_snapshot(directory:str):
    if not shutil.which("git"): return None
    try:
        branch=subprocess.run(["git","-C",directory,"branch","--show-current"],capture_output=True,text=True,timeout=8)
        status=subprocess.run(["git","-C",directory,"status","--porcelain"],capture_output=True,text=True,timeout=8)
        root=subprocess.run(["git","-C",directory,"rev-parse","--show-toplevel"],capture_output=True,text=True,timeout=8)
        if branch.returncode or status.returncode or root.returncode:return None
        return {"root":root.stdout.strip(),"branch":branch.stdout.strip(),"status":status.stdout}
    except (OSError,subprocess.SubprocessError): return None

@router.get("/agents")
def agents():
    from app.coding.antigravity import coding_agents
    return coding_agents.discover()

@router.get("/projects")
def list_projects(user: User=Depends(current_user), db: Session=Depends(get_db)):
    projects=db.query(CodingProject).filter_by(user_id=user.id,active=True).order_by(CodingProject.last_accessed_at.desc().nullslast(),CodingProject.name.asc()).all()
    return [{**{k:getattr(p,k) for k in ("id","name","directory","aliases","description","read_access","write_access","command_access","network_access","active","is_active")},
             "allowed_commands":p.allowed_commands or [],
             "allowed_domains":p.allowed_domains or [],
             "exists":Path(p.directory).is_dir()} for p in projects]

@router.get("/projects/active")
def get_active_project(user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=db.query(CodingProject).filter_by(user_id=user.id,active=True,is_active=True).first()
    return {"project":{"id":p.id,"name":p.name,"directory":p.directory} if p else None}

@router.get("/projects/resolve")
def resolve_project(q:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    """Resolve only unique exact name/alias matches; callers must clarify ambiguity."""
    needle=q.strip().casefold()
    if not needle: raise HTTPException(400,"Project name or alias is required")
    rows=db.query(CodingProject).filter_by(user_id=user.id,active=True).all()
    hits=[p for p in rows if p.name.casefold()==needle or needle in [a.casefold() for a in (p.aliases or [])]]
    if len(hits)>1: return {"status":"ambiguous","matches":[{"id":p.id,"name":p.name,"directory":p.directory} for p in hits]}
    if not hits: return {"status":"not_found","matches":[]}
    p=hits[0]
    return {"status":"resolved","project":{"id":p.id,"name":p.name,"directory":p.directory}}

@router.get("/projects/{project_id}/workspace")
def workspace_status(project_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=_project(db,user,project_id)
    path=Path(p.directory)
    if not path.is_dir(): return {"exists":False,"directory":p.directory,"git":None}
    def git(*args):
        if not shutil.which("git"): return None
        try:
            x=subprocess.run(["git","-C",str(path),*args],capture_output=True,text=True,timeout=8)
            return x.stdout.strip() if x.returncode==0 else None
        except (OSError,subprocess.SubprocessError): return None
    root=git("rev-parse","--show-toplevel")
    if root is None: return {"exists":True,"directory":str(path),"git":None}
    return {"exists":True,"directory":str(path),"git":{"root":root,"branch":git("branch","--show-current"),"status":git("status","--short"),"has_uncommitted_changes":bool(git("status","--porcelain"))}}

@router.post("/projects", status_code=201)
def create_project(data: ProjectCreate, user: User=Depends(current_user), db: Session=Depends(get_db)):
    require_execution("coding_agent")
    path=Path(data.directory).expanduser()
    if not path.is_absolute() or not path.is_dir(): raise HTTPException(400,"Directory must be an existing absolute directory")
    resolved=str(path.resolve())
    p=CodingProject(user_id=user.id,name=data.name.strip(),directory=resolved,aliases=data.aliases,description=data.description)
    db.add(p); db.commit(); db.refresh(p)
    return {"id":p.id,"name":p.name,"directory":p.directory,"aliases":p.aliases,"description":p.description,"read_access":p.read_access,"write_access":p.write_access,"command_access":p.command_access,"allowed_commands":p.allowed_commands or [],"allowed_domains":p.allowed_domains or []}

@router.patch("/projects/{project_id}")
def update_project(project_id:int,data:ProjectUpdate,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=_project(db,user,project_id)
    changes=data.model_dump(exclude_unset=True)
    domains=changes.get("allowed_domains",p.allowed_domains or [])
    if changes.get("network_access",p.network_access) and not domains:
        raise HTTPException(400,"Network access requires at least one explicit allowed domain")
    if changes.get("is_active") is True:
        db.query(CodingProject).filter_by(user_id=user.id,active=True).update({CodingProject.is_active:False},synchronize_session=False)
    for k,v in changes.items(): setattr(p,k,v)
    db.commit(); return {"id":p.id,"name":p.name,"directory":p.directory,"aliases":p.aliases,"is_active":p.is_active,"read_access":p.read_access,"write_access":p.write_access,"command_access":p.command_access,"allowed_commands":p.allowed_commands or [],"allowed_domains":p.allowed_domains or [],"network_access":p.network_access}

@router.delete("/projects/{project_id}",status_code=204)
def delete_project(project_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=_project(db,user,project_id); p.active=False; db.commit()

@task_router.post("/tasks",status_code=201)
def create_task(data:TaskCreate,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=_project(db,user,data.project_id)
    if not p.read_access: raise HTTPException(403,"Project read access is disabled")
    if data.brief.project_id != p.id: raise HTTPException(400,"Brief project does not match task project")
    if data.agent_id != "antigravity-cli": raise HTTPException(400,"Unsupported coding agent")
    brief=data.brief.model_copy(deep=True)
    # Select small, relevant context instead of copying full conversation history.
    readme=Path(p.directory)/"README.md"
    if readme.is_file():
        try: brief.architecture=(brief.architecture+"\n\nSelected README context (untrusted project content):\n"+readme.read_text(encoding="utf-8",errors="replace")[:3500]).strip()
        except OSError: pass
    try:
        from app.services.conversation_memory import search_conversations
        prior=search_conversations(db,user.id,user.timezone,data.instruction,limit=3)
        brief.relevant_decisions.extend([f"Prior conversation ({item.get('title') or 'untitled'}): {item.get('summary','')[:600]}" for item in prior])
    except Exception:
        # Context retrieval must not prevent safely drafting a task.
        pass
    row=CodingTaskRecord(id=str(uuid.uuid4()),user_id=user.id,project_id=p.id,agent_id=data.agent_id,instruction=data.instruction,
       brief=brief.model_dump(),status=TaskStatus.AWAITING_APPROVAL.value,approval_state="pending",events=[{"type":"task_created","at":datetime.now(UTC).isoformat()},{"type":"workspace_preflight","git":_git_snapshot(p.directory)}])
    db.add(row); db.commit(); db.refresh(row)
    return {"id":row.id,"status":row.status,"brief":row.brief,"approval_state":row.approval_state}

@task_router.get("/tasks")
def list_tasks(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return [_task_out(t) for t in db.query(CodingTaskRecord).filter_by(user_id=user.id).order_by(CodingTaskRecord.created_at.desc()).limit(100)]

def _task_out(t):
    return {"id":t.id,"parent_task_id":t.parent_task_id,"project_id":t.project_id,"agent_id":t.agent_id,"instruction":t.instruction,"brief":t.brief,"status":t.status,"approval_state":t.approval_state,"result":t.result,"verification":t.verification,"events":t.events,"session_id":t.session_id}

@task_router.post("/tasks/{task_id}/approve")
def approve_task(task_id:str,data:ApproveTask,user:User=Depends(current_user),db:Session=Depends(get_db)):
    require_execution("coding_agent")
    t=db.query(CodingTaskRecord).filter_by(id=task_id,user_id=user.id).first()
    if not t: raise HTTPException(404,"Task not found")
    if t.status != TaskStatus.AWAITING_APPROVAL: raise HTTPException(409,"Task is not awaiting approval")
    p=_project(db,user,t.project_id)
    if not p.read_access: raise HTTPException(403,"Project read access is disabled")
    if not p.write_access: raise HTTPException(403,"Enable project write access before approving agent execution")
    if not p.command_access: raise HTTPException(403,"Enable command execution access before approving agent execution")
    original=next((e.get("git") for e in (t.events or []) if e.get("type")=="workspace_preflight"),None)
    current=_git_snapshot(p.directory)
    if original != current: raise HTTPException(409,"Workspace Git state changed since this brief was prepared. Refresh/review the workspace state before approval.")
    agent=agents()[0]
    if not agent["available"]: raise HTTPException(503,"Antigravity CLI is not available")
    prompt=data.prompt.strip()
    if len(prompt)<3: raise HTTPException(400,"Approved prompt is empty")
    validate_transition(TaskStatus(t.status),TaskStatus.QUEUED)
    t.approved_prompt=prompt; t.approval_state="approved"; t.status=TaskStatus.QUEUED.value
    t.events=list(t.events or [])+[{"type":"approval_granted","at":datetime.now(UTC).isoformat()}]
    db.commit()
    from app.coding.antigravity import coding_agents
    from app.services.agy_bridge import AgyError
    sid=str(uuid.uuid4())
    try:
        adapter=coding_agents.get(t.agent_id)
        session=adapter.launch(p.directory,prompt,str(uuid.uuid4()),permissions={"allowed_commands":p.allowed_commands or [],"allowed_domains":p.allowed_domains or [],"network_access":p.network_access})
    except AgyError as e:
        validate_transition(TaskStatus(t.status),TaskStatus.FAILED)
        t.status=TaskStatus.FAILED.value; t.result={"error":str(e)}; t.ended_at=datetime.now(UTC); db.commit()
        raise HTTPException(502,str(e)) from e
    validate_transition(TaskStatus(t.status),TaskStatus.RUNNING)
    t.status=TaskStatus.RUNNING.value; t.started_at=datetime.now(UTC); t.session_id=sid
    t.events=list(t.events or [])+[{"type":"agent_launched","at":datetime.now(UTC).isoformat(),"session_key":session.key}]
    db.add(CodingSessionRecord(id=sid,task_id=t.id,agent_id=t.agent_id,project_id=p.id,directory=p.directory,external_session_id=None,manager_key=session.key,status="running",resume_supported=True,output="",started_at=datetime.now(UTC)))
    p.last_accessed_at=datetime.now(UTC); db.commit()
    return _task_out(t)

@task_router.post("/tasks/{task_id}/follow-up")
def follow_up(task_id:str,data:ApproveTask,user:User=Depends(current_user),db:Session=Depends(get_db)):
    require_execution("coding_agent")
    t=db.query(CodingTaskRecord).filter_by(id=task_id,user_id=user.id).first()
    if not t or not t.session_id: raise HTTPException(404,"Active session not found")
    sess=db.query(CodingSessionRecord).filter_by(id=t.session_id).first()
    if not sess: raise HTTPException(404,"Session not found")
    p=_project(db,user,t.project_id)
    if not p.read_access or not p.write_access: raise HTTPException(403,"Project read/write access is not granted")
    from app.coding.antigravity import coding_agents
    from app.services.agy_bridge import AgyError
    adapter=coding_agents.get(t.agent_id)
    try:
        live=adapter.get_status(sess.manager_key or "")
        if t.status==TaskStatus.WAITING_FOR_USER.value and live.get("active"):
            adapter.stop(sess.manager_key or "")
            live={"active":False}
        if not live.get("active"):
            if not sess.external_session_id: raise AgyError("The CLI has not emitted a conversation ID for recovery yet")
            resumed=adapter.resume_session_id(sess.directory,p.name,sess.external_session_id,{"allowed_commands":p.allowed_commands or [],"allowed_domains":p.allowed_domains or [],"network_access":p.network_access})
            sess.manager_key=resumed.key
        adapter.send_prompt(sess.manager_key or "",data.prompt)
    except AgyError as e: raise HTTPException(409,str(e)) from e
    if t.status==TaskStatus.COMPLETED.value:
        child_id=str(uuid.uuid4()); child_session_id=str(uuid.uuid4())
        brief=dict(t.brief or {}); brief["objective"]=data.prompt
        child=CodingTaskRecord(id=child_id,user_id=user.id,project_id=t.project_id,parent_task_id=t.id,agent_id=t.agent_id,
            instruction=data.prompt,brief=brief,approved_prompt=data.prompt,status=TaskStatus.RUNNING.value,approval_state="approved",
            events=[{"type":"task_created","at":datetime.now(UTC).isoformat(),"source":"follow_up"},{"type":"approval_granted","at":datetime.now(UTC).isoformat()}],
            session_id=child_session_id,started_at=datetime.now(UTC))
        # Flush the child first so its FK target exists before the dependent
        # persisted session is inserted (SQLite test DBs enforce this strictly).
        db.add(child); db.flush()
        child_session=CodingSessionRecord(id=child_session_id,task_id=child_id,agent_id=t.agent_id,project_id=t.project_id,directory=sess.directory,
            external_session_id=sess.external_session_id,manager_key=sess.manager_key,status="running",resume_supported=True,output=sess.output,
            event_cursor=sess.event_cursor,started_at=datetime.now(UTC))
        db.add(child_session); db.commit(); db.refresh(child)
        return _task_out(child)
    if t.status==TaskStatus.WAITING_FOR_USER.value:
        validate_transition(TaskStatus(t.status),TaskStatus.RUNNING);t.status=TaskStatus.RUNNING.value
    sess.status="running"
    t.events=list(t.events or [])+[{"type":"follow_up_requested","instruction":data.prompt,"at":datetime.now(UTC).isoformat()}]
    db.commit(); return _task_out(t)

@task_router.post("/tasks/{task_id}/resume")
def resume_task(task_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    require_execution("coding_agent")
    t=db.query(CodingTaskRecord).filter_by(id=task_id,user_id=user.id).first()
    if not t: raise HTTPException(404,"Task not found")
    if t.status not in (TaskStatus.INTERRUPTED.value,TaskStatus.RUNNING.value): raise HTTPException(409,"Task is not resumable")
    p=_project(db,user,t.project_id)
    if not p.read_access or not p.write_access: raise HTTPException(403,"Project read/write access is not granted")
    s=db.query(CodingSessionRecord).filter_by(id=t.session_id,task_id=t.id).first() if t.session_id else None
    if not s: raise HTTPException(409,"No persisted Antigravity session is available")
    from app.coding.antigravity import coding_agents
    from app.services.agy_bridge import AgyError
    adapter=coding_agents.get(t.agent_id)
    if t.status==TaskStatus.RUNNING.value:
        live=adapter.get_status(s.manager_key or "")
        if live.get("active"):
            raise HTTPException(409,"This Antigravity session is still running; send a follow-up or stop it first")
        validate_transition(TaskStatus.RUNNING,TaskStatus.INTERRUPTED)
        t.status=TaskStatus.INTERRUPTED.value; s.status="interrupted"
        t.events=list(t.events or [])+[{"type":"execution_interrupted","at":datetime.now(UTC).isoformat()}]
        db.commit()
    if not s.external_session_id: raise HTTPException(409,"No Antigravity conversation ID has been persisted")
    try: session=adapter.resume_session_id(p.directory,p.name,s.external_session_id,{"allowed_commands":p.allowed_commands or [],"allowed_domains":p.allowed_domains or [],"network_access":p.network_access})
    except AgyError as e: raise HTTPException(409,str(e)) from e
    if t.status==TaskStatus.INTERRUPTED.value:
        validate_transition(TaskStatus.INTERRUPTED,TaskStatus.RUNNING)
        t.status=TaskStatus.RUNNING.value
    t.events=list(t.events or [])+[{"type":"session_resumed","at":datetime.now(UTC).isoformat()}]
    if t.session_id:
        s=db.query(CodingSessionRecord).filter_by(id=t.session_id).first()
        if s: s.manager_key=session.key; s.status="running"
    db.commit(); return _task_out(t)

@task_router.get("/tasks/{task_id}/session")
def task_session(task_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    require_execution("coding_agent")
    t=db.query(CodingTaskRecord).filter_by(id=task_id,user_id=user.id).first()
    if not t: raise HTTPException(404,"Task not found")
    if not t.session_id: return {"task":_task_out(t),"session":None}
    s=db.query(CodingSessionRecord).filter_by(id=t.session_id).first()
    from app.coding.antigravity import coding_agents
    adapter=coding_agents.get(t.agent_id)
    live=adapter.get_status(s.manager_key or "") if s else {"active":False}
    persisted_live_state=(live.get("session") or {}).get("state") if live else None
    if s and (live.get("active") or persisted_live_state in {"IDLE","FAILED","WAITING_FOR_USER"}):
        live_session=live.get("session") or {}
        s.output=live_session.get("recent_output","")
        s.external_session_id=live_session.get("conversation_id") or s.external_session_id
        events=live_session.get("events") or []
        event_total=int(live_session.get("event_total",len(events)))
        event_start=max(0,event_total-len(events))
        if s.event_cursor<event_start:
            t.events=list(t.events or [])+[{"type":"event_buffer_overrun","lost_events":event_start-s.event_cursor,"at":datetime.now(UTC).isoformat()}]
        new_events=events[max(0,s.event_cursor-event_start):]
        for event in new_events:
            t.events=list(t.events or [])+[{"type":"agent_event","event":event,"at":datetime.now(UTC).isoformat()}]
        s.event_cursor=event_total
        if live_session.get("state")=="WAITING_FOR_USER" and t.status==TaskStatus.RUNNING.value:
            validate_transition(TaskStatus(t.status),TaskStatus.WAITING_FOR_USER); t.status=TaskStatus.WAITING_FOR_USER.value
            t.events=list(t.events or [])+[{"type":"follow_up_requested","at":datetime.now(UTC).isoformat(),"source":"agent_waiting"}]
            s.status="waiting_for_user"
        elif live_session.get("state")=="FAILED" and t.status in (TaskStatus.RUNNING.value,TaskStatus.WAITING_FOR_USER.value):
            validate_transition(TaskStatus(t.status),TaskStatus.FAILED)
            t.status=TaskStatus.FAILED.value;t.ended_at=datetime.now(UTC);s.status="failed";s.ended_at=t.ended_at
            t.result={"agent_reported":False,"error":(live_session.get("last_result") or {}).get("error","Antigravity CLI failed")}
            t.events=list(t.events or [])+[{"type":"execution_failed","at":datetime.now(UTC).isoformat()}]
        elif live_session.get("state")=="IDLE" and t.status==TaskStatus.RUNNING.value:
            validate_transition(TaskStatus(t.status),TaskStatus.COMPLETED)
            t.status=TaskStatus.COMPLETED.value; t.ended_at=datetime.now(UTC)
            s.status="agent_reported_completion"; s.ended_at=t.ended_at
            result=live_session.get("last_result") or {}
            events=live_session.get("events") or []
            commands=[]; changed_files=[]
            for event in events:
                step=event.get("step_update",{})
                if step.get("step_type")=="tool" and step.get("tool_name")=="run_command":
                    info=step.get("tool_info") or {}; commands.append({"command":(info.get("parameters") or {}).get("CommandLine"),"output":info.get("output"),"error":info.get("error")})
                elif step.get("step_type")=="tool" and step.get("state")=="DONE" and step.get("tool_name") in {"write_file","write_to_file","replace_file_content","multi_replace_file_content","notebook_edit"}:
                    params=(step.get("tool_info") or {}).get("parameters") or {}
                    path=next((params.get(k) for k in ("Path","path","FilePath","file_path","notebook_path") if params.get(k)),None)
                    if path and path not in changed_files: changed_files.append(path)
            t.result={"agent_reported":True,"status":result.get("status"),"summary":result.get("response",""),"changed_files_reported_by_tools":changed_files,"commands_executed":commands}
            t.verification={"independently_verified":False,"tests_observed":[c["command"] for c in commands if c.get("command") and any(x in c["command"].lower() for x in ("pytest","npm test","vitest","jest","cargo test"))],"test_results":"Not independently verified; inspect captured command output.","note":"A successful agent turn does not itself establish tests passed."}
            t.events=list(t.events or [])+[{"type":"completion_reported","at":datetime.now(UTC).isoformat()}]
        db.commit()
    elif s and t.status==TaskStatus.RUNNING.value:
        validate_transition(TaskStatus(t.status),TaskStatus.INTERRUPTED)
        t.status=TaskStatus.INTERRUPTED.value; s.status="interrupted"
        s.error="IRIS process no longer has an active Antigravity process for this session. Resume is workspace-scoped to the CLI's latest conversation."
        t.events=list(t.events or [])+[{"type":"execution_interrupted","at":datetime.now(UTC).isoformat()}]
        db.commit()
    if s: db.commit()
    return {"task":_task_out(t),"session":{**live,"persisted_id":s.id if s else None,"persisted_output":s.output if s else ""}}

@task_router.post("/tasks/{task_id}/stop")
def stop_task(task_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    require_execution("coding_agent")
    t=db.query(CodingTaskRecord).filter_by(id=task_id,user_id=user.id).first()
    if not t: raise HTTPException(404,"Task not found")
    if not t.session_id: raise HTTPException(409,"Task has no active session")
    s=db.query(CodingSessionRecord).filter_by(id=t.session_id).first()
    from app.coding.antigravity import coding_agents
    if s: coding_agents.get(t.agent_id).stop(s.manager_key or ""); s.status="stopped"; s.ended_at=datetime.now(UTC)
    if t.status in (TaskStatus.RUNNING.value,TaskStatus.WAITING_FOR_USER.value):
        validate_transition(TaskStatus(t.status),TaskStatus.CANCELLED); t.status=TaskStatus.CANCELLED.value
    t.ended_at=datetime.now(UTC); t.events=list(t.events or [])+[{"type":"session_stopped","at":datetime.now(UTC).isoformat()}]
    db.commit(); return _task_out(t)
