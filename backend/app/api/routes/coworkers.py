"""Persistent coworker management, task assignment, approvals and governance APIs."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.agent.registry import create_default_registry
from app.core.database import get_db
from app.models.coding_project import CodingProject
from app.models.coworker import Coworker, CoworkerApproval, CoworkerEvent, CoworkerSession, CoworkerTask
from app.models.user import User
from app.coworkers.contracts import coworker_transition, transition
from app.coworkers.execution import run_coworker_task, _fail_dependents
from app.core.execution_provider import require_execution
from app.coworkers.governance import evaluate_capability
from app.coworkers.templates import TEMPLATES
from app.coworkers.computer_use import MockLocalComputerUse, run_mock_demo

router = APIRouter(prefix="/coworkers", tags=["coworkers"])


class CoworkerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=80)
    description: str = ""
    specialisation: str = "general"
    responsibilities: list[str] = []
    system_instructions: str = ""
    preferred_provider: str | None = None
    preferred_model: str | None = None
    allowed_capabilities: list[str] = []
    project_id: int | None = None
    permission_profile: dict = {}


class CoworkerUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = None
    role: str | None = None
    specialisation: str | None = None
    responsibilities: list[str] | None = None
    system_instructions: str | None = None
    preferred_provider: str | None = None
    preferred_model: str | None = None
    allowed_capabilities: list[str] | None = None
    project_id: int | None = None
    permission_profile: dict | None = None
    availability: bool | None = None


class TaskCreate(BaseModel):
    instruction: str = Field(min_length=3, max_length=12000)
    objectives: list[str] = []
    acceptance_criteria: list[str] = []
    required_capabilities: list[str] = []
    project_id: int | None = None
    parent_task_id: str | None = None
    dependencies: list[str] = []
    run: bool = True


class CoworkerChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=15000)
    project_id: int | None = None
    engine: str | None = "antigravity"
    workspace_id: str | None = None


class TaskAssignment(BaseModel):
    coworker_id: str


class CapabilityInvocation(BaseModel):
    arguments: dict = {}


class ApprovalDecision(BaseModel):
    reason: str | None = None


class DeliverableReview(BaseModel):
    accepted: bool = True
    reason: str = Field(min_length=3, max_length=2000)


class RecommendationRequest(BaseModel):
    instruction: str = Field(min_length=3, max_length=12000)
    required_capabilities: list[str] = []


class ComputerUseDemoRequest(BaseModel):
    task_id: str = "harmless-demo"


def _coworker(db: Session, user: User, coworker_id: str) -> Coworker:
    item = db.query(Coworker).filter_by(id=coworker_id, user_id=user.id).first()
    if item is None: raise HTTPException(404, "Coworker not found")
    return item


def _task(db: Session, user: User, task_id: str) -> CoworkerTask:
    item = db.query(CoworkerTask).filter_by(id=task_id, user_id=user.id).first()
    if item is None: raise HTTPException(404, "Coworker task not found")
    return item


def _event(db, user_id, coworker_id, task_id, kind, payload=None):
    db.add(CoworkerEvent(user_id=user_id, coworker_id=coworker_id, task_id=task_id,
                         event_type=kind, payload=payload or {}))


def _coworker_out(c: Coworker, tasks: list | None = None):
    return {"id": c.id, "name": c.name, "description": c.description, "role": c.role,
        "specialisation": c.specialisation, "responsibilities": c.responsibilities or [],
        "system_instructions": c.system_instructions, "preferred_provider": c.preferred_provider,
        "preferred_model": c.preferred_model, "allowed_capabilities": c.allowed_capabilities or [],
        "project_id": c.project_id, "permission_profile": c.permission_profile or {},
        "status": c.status, "availability": c.availability, "config_version": c.config_version,
        "created_at": c.created_at, "updated_at": c.updated_at, "tasks": tasks or []}


def _task_out(t: CoworkerTask):
    return {"id": t.id, "coworker_id": t.coworker_id, "parent_task_id": t.parent_task_id,
        "project_id": t.project_id, "instruction": t.instruction, "objectives": t.objectives or [],
        "acceptance_criteria": t.acceptance_criteria or [], "required_capabilities": t.required_capabilities or [],
        "dependencies": t.dependencies or [], "permission_scope": t.permission_scope or {},
        "status": t.status, "result": t.result, "verification": t.verification, "output": t.output,
        "error": t.error, "session_id": t.session_id, "coding_task_id": t.coding_task_id, "created_at": t.created_at,
        "updated_at": t.updated_at, "started_at": t.started_at, "ended_at": t.ended_at}


def _sync_coding_status(db: Session, user: User, task: CoworkerTask):
    if not task.coding_task_id: return
    from app.models.coding_task import CodingTaskRecord
    coding=db.query(CodingTaskRecord).filter_by(id=task.coding_task_id,user_id=user.id).first()
    if not coding: return
    target={"awaiting_approval":"waiting_input","queued":"working","running":"working",
            "waiting_for_user":"waiting_input","completed":"completed","failed":"failed",
            "cancelled":"cancelled","interrupted":"interrupted"}.get(coding.status)
    previously_reviewed = bool((task.verification or {}).get("state") == "user_reviewed")
    if target == "completed" and (not coding.verification or not coding.verification.get("independently_verified")) and not previously_reviewed:
        target = "completed_with_issues"
    if target and target!=task.status and target in {"completed","completed_with_issues","failed","stopped","interrupted","working","waiting_input"}:
        task.status=target
        task.output="Coding task " + coding.status.replace("_"," ") + ". Review its execution report in Projects."
        task.result={"coding_task_id":coding.id,"status":coding.status,"result":coding.result}
        task.verification=coding.verification or {"state":"pending","independently_verified":False}
        if target in {"completed","completed_with_issues","failed","stopped","interrupted"}: task.ended_at=coding.ended_at or datetime.now(UTC)
        c=db.query(Coworker).filter_by(id=task.coworker_id,user_id=user.id).first()
        if c: c.status=target if target != "cancelled" else "stopped"
        _event(db,user.id,task.coworker_id,task.id,"coding_task_status_synced",{"coding_task_id":coding.id,"status":coding.status})


@router.get("/templates")
def list_templates():
    return TEMPLATES


@router.get("/capabilities")
def list_capabilities():
    return [{"name": t.name, "description": t.description, "risk_level": t.risk_level.value,
             "mutates_state": t.mutates_state, "available": True}
            for t in create_default_registry().list_tools()]


@router.post("/recommend")
def recommend_coworker(data: RecommendationRequest,
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.agent.supervisor import IrisSupervisor
    recommendation = IrisSupervisor().recommend_coworker(db,user,data.instruction,data.required_capabilities)
    if recommendation is None: return {"recommendation": None, "reason": "No available coworker has the requested capability scope."}
    return {"recommendation": recommendation, "reason": "Selected by IRIS Supervisor from configured roles, availability and granted capabilities."}


@router.get("/computer-use/providers")
async def computer_use_providers():
    return [await MockLocalComputerUse().detect()]


@router.post("/computer-use/demo")
async def computer_use_demo(data: ComputerUseDemoRequest, user: User = Depends(current_user)):
    result=await run_mock_demo(data.task_id[:100])
    return {"provider":result.provider,"is_mock":result.is_mock,"status":result.status,
            "evidence":result.evidence,"events":[{"type":e.kind,"detail":e.detail} for e in result.events]}


@router.get("")
def list_coworkers(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_coworker_out(c) for c in db.query(Coworker).filter_by(user_id=user.id).order_by(Coworker.created_at.desc()).all()]


@router.post("", status_code=201)
def create_coworker(data: CoworkerCreate, template: str | None = None,
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    values = data.model_dump()
    if template:
        base = next((x for x in TEMPLATES if x["key"] == template), None)
        if base is None: raise HTTPException(404, "Coworker template not found")
        for key in ("role", "description", "specialisation", "responsibilities", "allowed_capabilities"):
            if key not in data.model_fields_set: values[key] = base[key]
    if data.project_id is not None:
        project = db.query(CodingProject).filter_by(id=data.project_id, user_id=user.id, active=True).first()
        if not project or not project.read_access: raise HTTPException(403, "Project is unavailable or not readable")
    registry = create_default_registry()
    unknown = set(values["allowed_capabilities"]) - {t.name for t in registry.list_tools()}
    if unknown: raise HTTPException(422, f"Unknown IRIS capabilities: {', '.join(sorted(unknown))}")
    c = Coworker(id=str(uuid4()), user_id=user.id, status="idle", **values)
    db.add(c); db.flush(); _event(db,user.id,c.id,None,"coworker_created",{"role":c.role}); db.commit(); db.refresh(c)
    return _coworker_out(c)


@router.get("/{coworker_id:uuid}")
def get_coworker(coworker_id, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _coworker(db,user,str(coworker_id))
    tasks = db.query(CoworkerTask).filter_by(user_id=user.id,coworker_id=c.id).order_by(CoworkerTask.created_at.desc()).limit(50).all()
    for task in tasks: _sync_coding_status(db,user,task)
    db.commit()
    return _coworker_out(c, [_task_out(t) for t in tasks])


@router.patch("/{coworker_id}")
def update_coworker(coworker_id: str, data: CoworkerUpdate,
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _coworker(db,user,coworker_id); changes = data.model_dump(exclude_unset=True)
    if c.status in {"working", "waiting_approval", "waiting_input"} and any(k in changes for k in ("allowed_capabilities", "project_id", "permission_profile")):
        raise HTTPException(409,"Pause or finish active work before changing its permissions/workspace")
    if "project_id" in changes and changes["project_id"] is not None:
        p = db.query(CodingProject).filter_by(id=changes["project_id"],user_id=user.id,active=True).first()
        if not p or not p.read_access: raise HTTPException(403,"Project is unavailable or not readable")
    if "allowed_capabilities" in changes:
        names={t.name for t in create_default_registry().list_tools()}
        unknown=set(changes["allowed_capabilities"] or [])-names
        if unknown: raise HTTPException(422,"One or more capabilities are unavailable")
    for k,v in changes.items(): setattr(c,k,v)
    c.config_version += 1; c.updated_at=datetime.now(UTC)
    _event(db,user.id,c.id,None,"coworker_updated",{"fields":list(changes)}); db.commit(); db.refresh(c)
    return _coworker_out(c)


@router.delete("/{coworker_id}")
def delete_coworker(coworker_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c=_coworker(db,user,coworker_id)
    if c.status=="stopped": return _coworker_out(c)
    active=db.query(CoworkerTask).filter(CoworkerTask.coworker_id==c.id,CoworkerTask.user_id==user.id,CoworkerTask.status.in_(["queued","running","waiting_approval","waiting_input","paused"])).first()
    if active: raise HTTPException(409,"Stop or finish active tasks before removing a coworker")
    c.status=coworker_transition(c.status,"stopped")
    c.availability=False
    _event(db,user.id,c.id,None,"coworker_archived",{"history_retained":True})
    db.commit(); return _coworker_out(c)


@router.post("/{coworker_id}/activate")
def activate_coworker(coworker_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c=_coworker(db,user,coworker_id)
    if c.status!="idle": c.status=coworker_transition(c.status,"idle")
    c.availability=True; _event(db,user.id,c.id,None,"coworker_activated",{}); db.commit()
    return _coworker_out(c)


@router.get("/tasks")
def list_tasks(user: User = Depends(current_user), db: Session = Depends(get_db), status: str | None = None):
    q=db.query(CoworkerTask).filter_by(user_id=user.id)
    if status: q=q.filter_by(status=status)
    tasks=q.order_by(CoworkerTask.created_at.desc()).limit(200).all()
    for task in tasks: _sync_coding_status(db,user,task)
    db.commit()
    return [_task_out(t) for t in tasks]


@router.post("/{coworker_id}/tasks", status_code=202)
def assign_task(coworker_id: str, data: TaskCreate, background: BackgroundTasks,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    if data.run:
        require_execution("coworker")
    c=_coworker(db,user,coworker_id)
    if not c.availability or c.status in {"assigned","working","waiting_approval","waiting_input","paused"}:
        raise HTTPException(409,"Coworker is currently unavailable")
    project_id=data.project_id if data.project_id is not None else c.project_id
    project=None
    if project_id is not None:
        project=db.query(CodingProject).filter_by(id=project_id,user_id=user.id,active=True).first()
        if not project or not project.read_access: raise HTTPException(403,"Selected project is unavailable or lacks read access")
        if c.project_id is not None and c.project_id != project_id: raise HTTPException(403,"Coworker is restricted to its assigned project")
    if data.parent_task_id:
        parent=_task(db,user,data.parent_task_id)
        if parent.coworker_id!=c.id and parent.project_id!=project_id: raise HTTPException(403,"Child task must share its parent workspace")
    if data.dependencies:
        deps=db.query(CoworkerTask).filter(CoworkerTask.id.in_(data.dependencies),CoworkerTask.user_id==user.id).all()
        if len(deps)!=len(set(data.dependencies)): raise HTTPException(422,"Every dependency must belong to this user")
        if any(dep.project_id!=project_id for dep in deps): raise HTTPException(403,"Dependencies must use the same workspace")
    required=data.required_capabilities or []
    if set(required)-set(c.allowed_capabilities or []): raise HTTPException(403,"Task requests capabilities not granted to this coworker")
    if data.parent_task_id=="": raise HTTPException(422,"Parent task ID cannot be empty")
    t=CoworkerTask(id=str(uuid4()),user_id=user.id,coworker_id=c.id,parent_task_id=data.parent_task_id,
        project_id=project_id,instruction=data.instruction,objectives=data.objectives,
        acceptance_criteria=data.acceptance_criteria,required_capabilities=required,
        dependencies=data.dependencies,permission_scope={"project_id":project_id,"capabilities":required,"auto_run":data.run})
    db.add(t); db.flush()
    c.status=coworker_transition(c.status,"assigned") if c.status in {"idle","completed","failed"} else "assigned"
    _event(db,user.id,c.id,t.id,"task_assigned",{"dependencies":data.dependencies,"project_id":project_id})
    db.commit(); db.refresh(t)
    if data.run and not data.dependencies: background.add_task(run_coworker_task,t.id,user.id)
    return _task_out(t)


@router.post("/tasks/{task_id}/run", status_code=202)
def run_task(task_id: str, background: BackgroundTasks,
             user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_execution("coworker")
    task=_task(db,user,task_id)
    if task.status not in {"queued","interrupted","paused"}: raise HTTPException(409,"Task cannot be started from its current state")
    if task.dependencies:
        parents=db.query(CoworkerTask).filter(CoworkerTask.id.in_(task.dependencies),CoworkerTask.user_id==user.id).all()
        if len(parents)!=len(set(task.dependencies)):
            task.status="failed"; task.error="A required dependency is unavailable."; task.ended_at=datetime.now(UTC)
            _event(db,user.id,task.coworker_id,task.id,"task_failed",{"reason":task.error}); db.commit()
            return _task_out(task)
        failed=[parent for parent in parents if parent.status in {"failed","cancelled","stopped"}]
        if failed:
            task.status="failed"; task.error=f"Dependency {failed[0].id} did not complete."; task.ended_at=datetime.now(UTC)
            _event(db,user.id,task.coworker_id,task.id,"task_failed",{"reason":task.error}); _fail_dependents(db,user.id,task.id,task.error); db.commit()
            return _task_out(task)
        if any(parent.status!="completed" for parent in parents):
            raise HTTPException(409,"Task dependencies must be completed first")
    pending=db.query(CoworkerApproval).filter_by(task_id=task.id,user_id=user.id,status="pending").first()
    if pending: raise HTTPException(409,"Resolve pending approvals before continuing")
    if task.status in {"interrupted","paused"}:
        # Retrying interrupted work is an explicit user request; preserve existing output.
        task.status="queued"; task.error=None
    coworker=_coworker(db,user,task.coworker_id)
    _event(db,user.id,coworker.id,task.id,"task_resumed",{"explicit":True}); db.commit()
    background.add_task(run_coworker_task,task.id,user.id)
    return _task_out(task)


@router.post("/tasks/{task_id}/pause")
def pause_task(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task=_task(db,user,task_id)
    if task.status!="queued": raise HTTPException(409,"Only queued work can be paused; the current provider cannot safely suspend an active model call")
    task.status=transition(task.status,"paused")
    c=_coworker(db,user,task.coworker_id); c.status="idle"
    _event(db,user.id,c.id,task.id,"task_paused",{"provider_control":"queued_only"}); db.commit(); return _task_out(task)


@router.patch("/tasks/{task_id}/assign")
def reassign_task(task_id: str, data: TaskAssignment,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    task=_task(db,user,task_id); target=_coworker(db,user,data.coworker_id)
    if task.status not in {"queued","failed","interrupted"}: raise HTTPException(409,"Only queued or stopped work can be reassigned")
    if not target.availability or target.status in {"assigned","working","waiting_approval","waiting_input","paused"}:
        raise HTTPException(409,"Selected coworker is unavailable")
    if task.project_id and target.project_id not in {None,task.project_id}: raise HTTPException(403,"Selected coworker is scoped to a different project")
    if set(task.required_capabilities or [])-set(target.allowed_capabilities or []): raise HTTPException(403,"Selected coworker lacks the task capabilities")
    old=_coworker(db,user,task.coworker_id); old.status="idle"
    task.coworker_id=target.id; target.status="assigned"
    _event(db,user.id,target.id,task.id,"task_reassigned",{"from_coworker_id":old.id})
    db.commit(); return _task_out(task)


@router.post("/tasks/{task_id}/follow-up", status_code=202)
def follow_up(task_id: str, data: TaskCreate, background: BackgroundTasks,
              user: User = Depends(current_user), db: Session = Depends(get_db)):
    if data.run:
        require_execution("coworker")
    parent=_task(db,user,task_id); c=_coworker(db,user,parent.coworker_id)
    if parent.status not in {"completed","failed","cancelled"}: raise HTTPException(409,"Follow-up is only available after the current task stops")
    if c.status in {"assigned","working","waiting_approval","waiting_input","paused"}: raise HTTPException(409,"Coworker has active work")
    if set(data.required_capabilities or [])-set(c.allowed_capabilities or []): raise HTTPException(403,"Follow-up requests ungranted capabilities")
    t=CoworkerTask(id=str(uuid4()),user_id=user.id,coworker_id=c.id,parent_task_id=parent.id,
        project_id=parent.project_id,instruction=data.instruction,objectives=data.objectives,
        acceptance_criteria=data.acceptance_criteria,required_capabilities=data.required_capabilities,
        dependencies=[parent.id],permission_scope={"project_id":parent.project_id,"capabilities":data.required_capabilities,"auto_run":data.run})
    db.add(t); c.status="assigned"; _event(db,user.id,c.id,t.id,"task_assigned",{"parent_task_id":parent.id,"source":"follow_up"})
    db.commit(); db.refresh(t)
    if data.run: background.add_task(run_coworker_task,t.id,user.id)
    return _task_out(t)


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _task(db, user, task_id)
    if t.status in {"completed", "cancelled"}:
        return _task_out(t)

    # Terminate underlying coding session if present
    if t.coding_task_id:
        from app.models.coding_task import CodingTaskRecord, CodingSessionRecord
        from app.coding.antigravity import coding_agents
        ct = db.query(CodingTaskRecord).filter_by(id=t.coding_task_id, user_id=user.id).first()
        if ct:
            ct.status = "cancelled"
            ct.ended_at = datetime.now(UTC)
            if ct.session_id:
                cs = db.query(CodingSessionRecord).filter_by(id=ct.session_id).first()
                if cs:
                    try:
                        coding_agents.get(ct.agent_id or "antigravity-cli").stop(cs.manager_key or "")
                    except Exception:
                        pass
                    cs.status = "stopped"
                    cs.ended_at = datetime.now(UTC)

    if t.session_id:
        sess = db.query(CoworkerSession).filter_by(id=t.session_id).first()
        if sess:
            sess.status = "stopped"
            sess.ended_at = datetime.now(UTC)

    t.status = "cancelled"
    t.ended_at = datetime.now(UTC)
    t.output = (t.output or "") + ("\n\n[Task stopped by user. Process terminated safely.]" if t.output else "Task stopped by user.")
    c = _coworker(db, user, t.coworker_id)
    c.status = "idle"
    _event(db, user.id, c.id, t.id, "task_stopped", {"status": t.status, "reason": "user_cancelled"})
    db.commit()
    return _task_out(t)


@router.post("/{coworker_id}/stop")
def stop_coworker(coworker_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _coworker(db, user, coworker_id)
    active = db.query(CoworkerTask).filter(
        CoworkerTask.coworker_id == c.id,
        CoworkerTask.user_id == user.id,
        CoworkerTask.status.in_(["queued", "running", "working", "waiting_approval", "waiting_input", "paused", "assigned"])
    ).order_by(CoworkerTask.created_at.desc()).first()
    if not active:
        c.status = "idle"
        db.commit()
        return {"stopped": False, "message": "No active task running for this coworker."}
    return cancel_task(active.id, user, db)


@router.get("/{coworker_id}/messages")
def list_coworker_messages(coworker_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _coworker(db, user, coworker_id)
    tasks = db.query(CoworkerTask).filter_by(
        user_id=user.id, coworker_id=c.id
    ).order_by(CoworkerTask.created_at.asc()).all()

    for task in tasks:
        _sync_coding_status(db, user, task)
    db.commit()

    turns = []
    for t in tasks:
        events = db.query(CoworkerEvent).filter_by(
            user_id=user.id, task_id=t.id
        ).order_by(CoworkerEvent.created_at.asc()).all()

        turns.append({
            "id": f"u-{t.id}",
            "role": "user",
            "content": t.instruction,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "task_id": t.id,
        })

        diff_summary = None
        if t.result and isinstance(t.result, dict):
            diff_summary = t.result.get("diff")

        turns.append({
            "id": f"c-{t.id}",
            "role": "coworker",
            "content": t.output or "",
            "error": t.error,
            "status": t.status,
            "created_at": (t.started_at or t.created_at).isoformat() if (t.started_at or t.created_at) else None,
            "ended_at": t.ended_at.isoformat() if t.ended_at else None,
            "task_id": t.id,
            "coding_task_id": t.coding_task_id,
            "project_id": t.project_id,
            "remote_workspace_id": t.remote_workspace_id,
            "task_branch": (t.result or {}).get("task_branch"),
            "agent_id": (t.result or {}).get("agent_id") or "antigravity-cli",
            "worktree_path": (t.result or {}).get("worktree_path"),
            "diff": diff_summary,
            "result": t.result,
            "verification": t.verification,
            "events": [{"id": e.id, "type": e.event_type, "payload": e.payload, "created_at": e.created_at.isoformat()} for e in events],
        })
    return turns


@router.post("/{coworker_id}/chat", status_code=202)
def chat_coworker(coworker_id: str, data: CoworkerChatRequest, background: BackgroundTasks,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_execution("coworker")
    c = _coworker(db, user, coworker_id)
    msg = data.message.strip()
    msg_lower = msg.lower()

    # 1. Stop / Cancel Intent Interception
    stop_phrases = {"stop", "cancel", "terminate", "abort", "halt", "pause", "wait stop", "don't continue", "stop it", "stop please"}
    is_stop_intent = msg_lower in stop_phrases or any(msg_lower.startswith(p + " ") for p in ("stop", "cancel", "abort", "halt"))
    if is_stop_intent:
        active = db.query(CoworkerTask).filter(
            CoworkerTask.coworker_id == c.id,
            CoworkerTask.user_id == user.id,
            CoworkerTask.status.in_(["queued", "running", "working", "waiting_approval", "waiting_input", "paused", "assigned"])
        ).order_by(CoworkerTask.created_at.desc()).first()
        if active:
            stopped_task = cancel_task(active.id, user, db)
            return {
                "action": "stopped",
                "task_id": active.id,
                "message": f"Task stopped upon your request. Active processes terminated safely and changes on branch `{ (active.result or {}).get('task_branch', 'iris/task') }` are preserved.",
                "task": stopped_task
            }

    # 2. Workspace resolution & persistence
    project_id = data.project_id if data.project_id is not None else c.project_id
    if not project_id:
        active_p = db.query(CodingProject).filter_by(user_id=user.id, active=True, is_active=True).first()
        if active_p:
            project_id = active_p.id
    if project_id and c.project_id != project_id:
        c.project_id = project_id
        db.commit()

    # 3. Context linking to last task
    last_task = db.query(CoworkerTask).filter_by(
        user_id=user.id, coworker_id=c.id
    ).order_by(CoworkerTask.created_at.desc()).first()

    task_id = str(uuid4())
    preferred_agent = data.engine or (c.permission_profile or {}).get("preferred_agent") or "antigravity-cli"
    t = CoworkerTask(
        id=task_id,
        user_id=user.id,
        coworker_id=c.id,
        parent_task_id=last_task.id if last_task else None,
        project_id=project_id,
        remote_workspace_id=data.workspace_id,
        instruction=msg,
        objectives=[msg],
        acceptance_criteria=["Deliver verified implementation or natural conversational response."],
        required_capabilities=c.allowed_capabilities or [],
        dependencies=[],
        permission_scope={"project_id": project_id, "workspace_id": data.workspace_id, "preferred_agent": preferred_agent, "auto_run": True, "conversational_auto_execute": True},
        status="queued"
    )
    db.add(t)
    db.flush()
    c.status = "working"
    _event(db, user.id, c.id, t.id, "chat_message_received", {"message": msg, "project_id": project_id, "engine": preferred_agent})
    db.commit()
    db.refresh(t)

    background.add_task(run_coworker_task, t.id, user.id)
    return {
        "action": "dispatched",
        "task_id": t.id,
        "task": _task_out(t),
        "coworker": _coworker_out(c)
    }


@router.get("/tasks/{task_id}/events")
def task_events(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _task(db,user,task_id)
    rows=db.query(CoworkerEvent).filter_by(user_id=user.id,task_id=task_id).order_by(CoworkerEvent.created_at.asc(),CoworkerEvent.id.asc()).all()
    return [{"id":e.id,"type":e.event_type,"payload":e.payload,"created_at":e.created_at} for e in rows]


@router.post("/tasks/{task_id}/review")
def review_deliverable(task_id: str, data: DeliverableReview,
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = _task(db, user, task_id)
    if task.status != "completed_with_issues":
        raise HTTPException(409, "Only deliverables awaiting review can be reviewed")
    if not data.accepted:
        _event(db, user.id, task.coworker_id, task.id, "deliverable_review_rejected", {"reason": data.reason})
        db.commit()
        return _task_out(task)
    task.status = transition(task.status, "completed")
    task.verification = {**(task.verification or {}), "state": "user_reviewed",
                         "independently_verified": False, "reviewed_by": "local-user",
                         "reviewed_at": datetime.now(UTC).isoformat(), "review_reason": data.reason}
    task.result = {**(task.result or {}), "user_review": {"accepted": True, "reason": data.reason}}
    coworker = _coworker(db, user, task.coworker_id)
    coworker.status = "completed"
    _event(db, user.id, coworker.id, task.id, "deliverable_review_accepted", {"reason": data.reason})
    db.commit()
    return _task_out(task)


@router.get("/approvals")
def list_approvals(user: User = Depends(current_user), db: Session = Depends(get_db), status: str = "pending"):
    rows=db.query(CoworkerApproval).filter_by(user_id=user.id,status=status).order_by(CoworkerApproval.created_at.desc()).all()
    return [{"id":a.id,"coworker_id":a.coworker_id,"task_id":a.task_id,"capability":a.capability,
             "action":a.action,"reason":a.reason,"status":a.status,"approver":a.approver,
             "decision_reason":a.decision_reason,"created_at":a.created_at,"expires_at":a.expires_at} for a in rows]


@router.post("/tasks/{task_id}/capabilities/{capability}/invoke")
async def invoke_capability(task_id: str, capability: str, data: CapabilityInvocation,
                            user: User = Depends(current_user), db: Session = Depends(get_db)):
    task=_task(db,user,task_id); c=_coworker(db,user,task.coworker_id)
    decision=evaluate_capability(db,user,c,task,capability,data.arguments)
    if not decision.allowed:
        _event(db,user.id,c.id,task.id,"capability_denied",{"capability":capability,"reason":decision.reason}); db.commit()
        raise HTTPException(403,decision.reason)
    if task.status not in {"running", "queued"}:
        raise HTTPException(409,"Capabilities can only be invoked by an active coworker task")
    if decision.requires_approval:
        approval=CoworkerApproval(id=str(uuid4()),user_id=user.id,coworker_id=c.id,task_id=task.id,
            capability=capability,action=data.arguments,reason=decision.reason,status="pending",
            expires_at=datetime.now(UTC)+timedelta(minutes=10))
        db.add(approval); task.status=transition(task.status,"waiting_approval")
        c.status="waiting_approval"; _event(db,user.id,c.id,task.id,"approval_requested",{"approval_id":approval.id,"capability":capability,"action":data.arguments}); db.commit()
        return {"status":"awaiting_approval","approval_id":approval.id,"reason":decision.reason}
    result=await decision.tool.execute(db,user,**data.arguments)
    _event(db,user.id,c.id,task.id,"tool_invoked",{"capability":capability,"success":result.success,"verified":result.verified})
    db.commit()
    return {"status":"executed" if result.success else "failed","result":result.model_dump()}


@router.post("/approvals/{approval_id}/decision")
async def decide_approval(approval_id: str, approved: bool, data: ApprovalDecision,
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
    approval=db.query(CoworkerApproval).filter_by(id=approval_id,user_id=user.id,status="pending").first()
    if not approval: raise HTTPException(404,"Pending approval not found")
    if approval.expires_at and approval.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        approval.status="expired"; approval.decided_at=datetime.now(UTC)
        task=_task(db,user,approval.task_id)
        if task.status=="waiting_approval": task.status=transition(task.status,"cancelled"); task.ended_at=datetime.now(UTC)
        _event(db,user.id,approval.coworker_id,task.id,"approval_expired",{"approval_id":approval.id})
        db.commit(); raise HTTPException(410,"Approval expired; request the action again")
    task=_task(db,user,approval.task_id); c=_coworker(db,user,approval.coworker_id)
    decision=evaluate_capability(db,user,c,task,approval.capability,approval.action)
    if not decision.allowed: raise HTTPException(403,decision.reason)
    approval.status="approved" if approved else "rejected"; approval.approver="local-user"
    approval.decision_reason=data.reason; approval.decided_at=datetime.now(UTC)
    _event(db,user.id,c.id,task.id,"approval_granted" if approved else "approval_rejected",{"approval_id":approval.id,"capability":approval.capability})
    result=None
    if approved:
        # The approved arguments are immutable and scoped to this one request.
        result=await decision.tool.execute(db,user,approval_token=f"coworker-approval:{approval.id}",**approval.action)
        _event(db,user.id,c.id,task.id,"tool_invoked",{"capability":approval.capability,"success":result.success,"verified":result.verified,"approval_id":approval.id})
        task.status=transition(task.status,"running") if task.status=="waiting_approval" else task.status
        c.status="working"
    else:
        task.status=transition(task.status,"cancelled") if task.status=="waiting_approval" else task.status
        c.status="idle"; task.ended_at=datetime.now(UTC)
    db.commit()
    return {"approval_id":approval.id,"status":approval.status,"execution":result.model_dump() if result else None}
