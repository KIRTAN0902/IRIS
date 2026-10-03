"""Action tools: give the agent the same write access the app's UI has.

Each tool calls the *same* service function or route handler the UI uses, with
the *same* Pydantic schemas, so the agent gets identical validation,
ownership checks and conflict rules, and stays in sync with the app as it
evolves. Covered: projects, goals, routines, focus sessions, daily reviews,
the user's profile, bulk task edits, and the startup CRM (leads, experiments,
startup details).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date as Date
from typing import Any

from pydantic import BaseModel, Field, create_model
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import Tool
from app.models.enums import FocusStatus, LifeArea, ProjectStatus
from app.models.user import User
from app.schemas.experiment import ExperimentCreate, ExperimentOut, ExperimentUpdate
from app.schemas.lead import LeadCreate, LeadOut, LeadUpdate
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.schemas.startup import StartupOut, StartupUpdate
from app.schemas.task import TaskUpdate

RunFn = Callable[..., tuple[Any, str]]


def _dump(value: Any) -> Any:
    """JSON-safe data from Pydantic models, ORM rows (some handlers return them), lists."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_dump(v) for v in value]
    if hasattr(value, "__table__"):
        row = {c.key: getattr(value, c.key) for c in sa_inspect(value).mapper.column_attrs}
        return json.loads(json.dumps(row, default=str))
    return value


def make_tool(
    *,
    name: str,
    description: str,
    run: RunFn,
    params: type[BaseModel] | None = None,
    read_only: bool | None = None,
    destructive: bool = False,
) -> Tool:
    """Build a Tool from a ``run(db, user, **params) -> (data, summary)`` function."""

    async def _run(self: Tool, db: Session, user: User, **kwargs: Any) -> ToolResult:
        data, summary = run(db, user, **kwargs)
        return ToolResult(tool_name=self.name, success=True, data=_dump(data), summary=summary)

    cls = type(
        "".join(p.title() for p in name.split("_")) + "Tool",
        (Tool,),
        {
            "name": name,
            "description": description,
            "parameters_schema": params,
            "read_only": read_only,
            "is_destructive": destructive,
            "run": _run,
        },
    )
    return cls()


def _with_id(base: type[BaseModel], id_field: str, what: str) -> type[BaseModel]:
    """``base``'s fields plus a required ``<id_field>`` (for update tools)."""
    return create_model(
        f"{base.__name__}With{id_field.title().replace('_', '')}",
        __base__=base,
        **{id_field: (int, Field(..., description=f"ID of the {what}"))},
    )


def _id_only(id_field: str, what: str) -> type[BaseModel]:
    return create_model(
        f"{id_field.title().replace('_', '')}Params",
        **{id_field: (int, Field(..., description=f"ID of the {what}"))},
    )


def _split(kwargs: dict[str, Any], id_field: str) -> tuple[int, dict[str, Any]]:
    kwargs = dict(kwargs)
    return kwargs.pop(id_field), kwargs


# --- Projects -------------------------------------------------------------------


class GetProjectsParams(BaseModel):
    area: LifeArea | None = Field(None, description="Filter by area")
    status: ProjectStatus | None = Field(None, description="Filter by status")


def _get_projects(db: Session, user: User, **kw: Any):
    from app.api.routes import projects

    rows = projects.list_projects(
        area=kw.get("area"), project_status=kw.get("status"), user=user, db=db
    )
    return rows, f"{len(rows)} projects"


def _create_project(db: Session, user: User, **kw: Any):
    from app.api.routes import projects

    out = projects.create_project(data=ProjectCreate(**kw), user=user, db=db)
    return out, f"Created project #{out.id} '{out.name}'"


def _update_project(db: Session, user: User, **kw: Any):
    from app.api.routes import projects

    project_id, patch = _split(kw, "project_id")
    out = projects.update_project(project_id=project_id, data=ProjectUpdate(**patch), user=user, db=db)
    return out, f"Updated project #{out.id} '{out.name}' ({', '.join(patch) or 'no changes'})"


def _delete_project(db: Session, user: User, **kw: Any):
    from app.api.routes import projects

    name = projects.get_project(project_id=kw["project_id"], user=user, db=db).name
    projects.delete_project(project_id=kw["project_id"], user=user, db=db)
    return {"deleted_project_id": kw["project_id"]}, f"Deleted project #{kw['project_id']} '{name}'"


# --- Goals & routines ---------------------------------------------------------------


def _delete_goal(db: Session, user: User, **kw: Any):
    from app.services import goal_service

    name = goal_service.get_goal(db, user.id, kw["goal_id"]).name
    goal_service.delete_goal(db, user.id, kw["goal_id"])
    return {"deleted_goal_id": kw["goal_id"]}, f"Deleted goal #{kw['goal_id']} '{name}'"


def _delete_routine(db: Session, user: User, **kw: Any):
    from app.api.routes import intelligence
    from app.models.recurring_schedule import RecurringSchedule

    sched = (
        db.query(RecurringSchedule)
        .filter(RecurringSchedule.id == kw["schedule_id"], RecurringSchedule.user_id == user.id)
        .first()
    )
    name = sched.name if sched else f"#{kw['schedule_id']}"
    intelligence.delete_recurring_schedule(schedule_id=kw["schedule_id"], user=user, db=db)
    return {"deleted_schedule_id": kw["schedule_id"]}, f"Removed routine '{name}'"


# --- Focus sessions ------------------------------------------------------------------


class StartFocusParams(BaseModel):
    task_id: int | None = Field(None, description="Task to focus on (optional)")
    planned_duration: int | None = Field(None, gt=0, le=24 * 60, description="Planned minutes")
    notes: str | None = Field(None, max_length=1000)


class FinishFocusParams(BaseModel):
    status: FocusStatus = Field(
        FocusStatus.COMPLETED, description="COMPLETED, PARTIAL or ABANDONED"
    )
    notes: str | None = None


def _start_focus(db: Session, user: User, **kw: Any):
    from app.api.routes import focus
    from app.schemas.common import FocusStartIn

    out = focus.start_focus(data=FocusStartIn(**kw), user=user, db=db)
    mins = f" for {out.planned_duration}m" if out.planned_duration else ""
    return out, f"Started a focus session{mins}"


def _finish_focus(db: Session, user: User, **kw: Any):
    from app.api.routes import focus
    from app.core.errors import NotFoundError
    from app.models.focus_session import FocusSession
    from app.schemas.common import FocusCompleteIn

    running = (
        db.query(FocusSession)
        .filter(FocusSession.user_id == user.id, FocusSession.status == FocusStatus.RUNNING.value)
        .first()
    )
    if not running:
        raise NotFoundError("No focus session is running.")
    out = focus.complete_focus(session_id=running.id, data=FocusCompleteIn(**kw), user=user, db=db)
    return out, f"Ended focus session ({out.status.lower()}, {out.actual_duration or 0}m)"


# --- Daily review -------------------------------------------------------------------


class DailyReviewParams(BaseModel):
    date: Date | None = Field(None, description="Day being reviewed (default: today)")
    productivity_rating: int | None = Field(None, ge=1, le=5, description="1 (bad) to 5 (great)")
    blockers: str | None = Field(None, description="What got in the way")
    notes: str | None = Field(None, description="Anything else worth recording")


def _save_review(db: Session, user: User, **kw: Any):
    from app.api.routes import reviews
    from app.schemas.common import DailyReviewIn, DailyReviewUpdate
    from app.utils.datetime import to_local, utcnow

    day = kw.pop("date", None) or to_local(utcnow(), user.timezone).date()
    if reviews._get_review(db, user, day):
        out = reviews.update_review(day=day, data=DailyReviewUpdate(**kw), user=user, db=db)
        return out, f"Updated the review for {day:%a %d %b}"
    out = reviews.submit_review(data=DailyReviewIn(date=day, **kw), user=user, db=db)
    return out, f"Saved the review for {day:%a %d %b}"


# --- Profile ------------------------------------------------------------------------


class UpdateProfileParams(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    timezone: str | None = Field(None, description="IANA timezone, e.g. Asia/Kolkata")
    facts: dict[str, Any] | None = Field(
        None,
        description="Facts to add or change, merged into the profile. Wake/sleep times "
        "drive scheduling: use keys wake_time and sleep_time as HH:MM "
        "(e.g. {'wake_time': '06:30', 'sleep_time': '23:30'})",
    )
    preferences: dict[str, Any] | None = Field(
        None, description="Preferences to add or change, merged into the profile"
    )
    remove_keys: list[str] | None = Field(
        None, description="Fact/preference keys to remove from the profile"
    )


def _update_profile(db: Session, user: User, **kw: Any):
    from app.api.routes import users
    from app.schemas.common import UserUpdate

    remove = set(kw.pop("remove_keys", None) or [])
    patch: dict[str, Any] = {k: v for k, v in kw.items() if k in {"name", "timezone"}}
    from app.intelligence.profile_facts import FACT_ALIASES, normalize_facts

    # Removing "wake" also removes its canonical twin "wake_time", and vice versa.
    remove |= {FACT_ALIASES[k] for k in remove if k in FACT_ALIASES}
    remove |= {a for a, c in FACT_ALIASES.items() if c in remove}
    if kw.get("facts") or remove:
        current = normalize_facts(user.facts)
        incoming = normalize_facts(kw.get("facts"), strict=True)  # validates times
        merged = {**current, **incoming}
        patch["facts"] = {k: v for k, v in merged.items() if k not in remove}
    if kw.get("preferences") or remove:
        merged = {**(user.preferences or {}), **(kw.get("preferences") or {})}
        patch["preferences"] = {k: v for k, v in merged.items() if k not in remove}
    out = users.update_me(data=UserUpdate(**patch), user=user, db=db)
    changed = [*(kw.get("facts") or {}), *(kw.get("preferences") or {}), *patch.keys() - {"facts", "preferences"}]
    summary = "Updated your profile"
    if changed:
        summary += f": {', '.join(changed)}"
    if remove:
        summary += f" (removed {', '.join(sorted(remove))})"
    return {"name": out.name, "timezone": out.timezone, "facts": out.facts, "preferences": out.preferences}, summary


# --- Bulk task edits ------------------------------------------------------------------


# TaskUpdate's fields (same validation) minus the title, which is per task.
BulkTaskUpdate = create_model(
    "BulkTaskUpdate",
    task_ids=(list[int], Field(..., min_length=1, max_length=100, description="Tasks to change")),
    **{n: (f.annotation, f) for n, f in TaskUpdate.model_fields.items() if n != "title"},
)


def _update_tasks(db: Session, user: User, **kw: Any):
    from app.services import task_service

    ids = list(dict.fromkeys(kw.pop("task_ids")))
    kw.pop("title", None)
    patch = TaskUpdate(**kw)
    done, failed = [], []
    for task_id in ids:
        try:
            t = task_service.update_task(db, user.id, task_id, patch)
            done.append({"task_id": t.id, "title": t.title})
        except Exception as exc:  # noqa: BLE001 - report per task, keep going
            failed.append({"task_id": task_id, "error": str(exc) or type(exc).__name__})
    if not done:
        raise ValueError("; ".join(f"#{f['task_id']}: {f['error']}" for f in failed))
    summary = f"Updated {len(done)} task{'s' if len(done) != 1 else ''} ({', '.join(kw)})"
    if failed:
        summary += f"; {len(failed)} failed"
    return {"done": done, "failed": failed}, summary


# --- Startup CRM ----------------------------------------------------------------------


class GetLeadsParams(BaseModel):
    status: str | None = Field(None, description="LEAD, CONTACTED, REPLIED, INTERESTED, MEETING, CUSTOMER, LOST")
    follow_up_due: bool | None = Field(None, description="Only leads whose follow-up is due")
    limit: int = Field(50, ge=1, le=200)


def _startup_id(db: Session, user: User, startup_id: int | None) -> int:
    from app.services import startup_service

    return startup_service.get_startup(db, user.id, startup_id).id


def _get_leads(db: Session, user: User, **kw: Any):
    from app.services import startup_service

    rows, total = startup_service.list_leads(
        db, user.id, status=kw.get("status"), follow_up_due=kw.get("follow_up_due"), limit=kw.get("limit", 50)
    )
    return [LeadOut.model_validate(r) for r in rows], f"{len(rows)} of {total} leads"


CreateLeadParams = create_model(
    "CreateLeadParams",
    __base__=LeadCreate,
    startup_id=(int | None, Field(None, description="Defaults to the user's startup")),
)


def _create_lead(db: Session, user: User, **kw: Any):
    from app.services import startup_service

    kw["startup_id"] = _startup_id(db, user, kw.get("startup_id"))
    lead = startup_service.create_lead(db, user.id, LeadCreate(**kw).model_dump())
    return LeadOut.model_validate(lead), f"Added lead #{lead.id} {lead.name}"


def _update_lead(db: Session, user: User, **kw: Any):
    from app.services import startup_service

    lead_id, patch = _split(kw, "lead_id")
    data = LeadUpdate(**patch).model_dump(exclude_unset=True)
    lead = startup_service.update_lead(db, user.id, lead_id, data)
    return LeadOut.model_validate(lead), f"Updated lead #{lead.id} {lead.name} ({', '.join(data)})"


def _delete_lead(db: Session, user: User, **kw: Any):
    from app.services import startup_service

    name = startup_service.get_lead(db, user.id, kw["lead_id"]).name
    startup_service.delete_lead(db, user.id, kw["lead_id"])
    return {"deleted_lead_id": kw["lead_id"]}, f"Deleted lead #{kw['lead_id']} {name}"


class GetExperimentsParams(BaseModel):
    status: str | None = Field(None, description="PLANNED, RUNNING, COMPLETED, ABANDONED")


def _get_experiments(db: Session, user: User, **kw: Any):
    from app.services import startup_service

    rows = startup_service.list_experiments(db, user.id, status=kw.get("status"))
    return [ExperimentOut.model_validate(r) for r in rows], f"{len(rows)} experiments"


CreateExperimentParams = create_model(
    "CreateExperimentParams",
    __base__=ExperimentCreate,
    startup_id=(int | None, Field(None, description="Defaults to the user's startup")),
)


def _create_experiment(db: Session, user: User, **kw: Any):
    from app.services import startup_service

    kw["startup_id"] = _startup_id(db, user, kw.get("startup_id"))
    exp = startup_service.create_experiment(db, user.id, ExperimentCreate(**kw).model_dump())
    return ExperimentOut.model_validate(exp), f"Started tracking experiment #{exp.id} '{exp.name}'"


def _update_experiment(db: Session, user: User, **kw: Any):
    from app.services import startup_service

    exp_id, patch = _split(kw, "experiment_id")
    data = ExperimentUpdate(**patch).model_dump(exclude_unset=True)
    exp = startup_service.update_experiment(db, user.id, exp_id, data)
    return ExperimentOut.model_validate(exp), f"Updated experiment #{exp.id} '{exp.name}' ({', '.join(data)})"


UpdateStartupParams = create_model(
    "UpdateStartupParams",
    __base__=StartupUpdate,
    startup_id=(int | None, Field(None, description="Defaults to the user's startup")),
)


def _update_startup(db: Session, user: User, **kw: Any):
    from app.services import startup_service

    startup_id = _startup_id(db, user, kw.pop("startup_id", None))
    data = StartupUpdate(**kw).model_dump(exclude_unset=True)
    s = startup_service.update_startup(db, user.id, startup_id, data)
    return StartupOut.model_validate(s), f"Updated {s.name} ({', '.join(data)})"


# --- Registry ---------------------------------------------------------------------------


def action_tools() -> list[Tool]:
    return [
        # Projects
        make_tool(name="get_projects", description="List the user's projects (with task counts).",
                  params=GetProjectsParams, run=_get_projects, read_only=True),
        make_tool(name="create_project", description="Create a project to group related tasks.",
                  params=ProjectCreate, run=_create_project),
        make_tool(name="update_project", description="Change a project's name, description, area, status or deadline.",
                  params=_with_id(ProjectUpdate, "project_id", "project"), run=_update_project),
        make_tool(name="delete_project", description="Permanently delete a project. Only when the user asked.",
                  params=_id_only("project_id", "project"), run=_delete_project, destructive=True),
        # Goals & routines
        make_tool(name="delete_goal", description="Permanently delete a goal (it must have no child goals).",
                  params=_id_only("goal_id", "goal"), run=_delete_goal, destructive=True),
        make_tool(name="delete_recurring_schedule",
                  description="Remove a recurring routine/commitment from the weekly schedule. "
                  "To pause it instead, use update_recurring_schedule with status INACTIVE.",
                  params=_id_only("schedule_id", "recurring schedule"), run=_delete_routine, destructive=True),
        # Focus
        make_tool(name="start_focus", description="Start a focus session, optionally on a task, for planned minutes.",
                  params=StartFocusParams, run=_start_focus),
        make_tool(name="finish_focus", description="End the running focus session (COMPLETED, PARTIAL or ABANDONED).",
                  params=FinishFocusParams, run=_finish_focus),
        # Review & profile
        make_tool(name="save_daily_review",
                  description="Record or update the end-of-day review: productivity rating (1-5), blockers, notes.",
                  params=DailyReviewParams, run=_save_review),
        make_tool(name="update_profile",
                  description="Change the user's profile: name, timezone, and facts/preferences such as "
                  "wake_time, sleep_time, college or job details. Facts and preferences are merged, not replaced.",
                  params=UpdateProfileParams, run=_update_profile),
        # Bulk task edits
        make_tool(name="update_tasks",
                  description="Change several tasks in ONE call: the same new priority, status, area, deadline, "
                  "estimate, energy level, goal or project for every listed task. "
                  "Use instead of repeated update_task calls.",
                  params=BulkTaskUpdate, run=_update_tasks),
        # Startup CRM
        make_tool(name="get_leads", description="List startup CRM leads, optionally by status or due follow-ups.",
                  params=GetLeadsParams, run=_get_leads, read_only=True),
        make_tool(name="create_lead", description="Add a lead (prospect/customer contact) to the startup CRM.",
                  params=CreateLeadParams, run=_create_lead),
        make_tool(name="update_lead", description="Change a lead's details, status or next follow-up date.",
                  params=_with_id(LeadUpdate, "lead_id", "lead"), run=_update_lead),
        make_tool(name="delete_lead", description="Permanently delete a lead. Only when the user asked.",
                  params=_id_only("lead_id", "lead"), run=_delete_lead, destructive=True),
        make_tool(name="get_experiments", description="List startup experiments.",
                  params=GetExperimentsParams, run=_get_experiments, read_only=True),
        make_tool(name="create_experiment", description="Record a new startup experiment (hypothesis, action, metric).",
                  params=CreateExperimentParams, run=_create_experiment),
        make_tool(name="update_experiment", description="Update an experiment: status, result, conclusion, next action.",
                  params=_with_id(ExperimentUpdate, "experiment_id", "experiment"), run=_update_experiment),
        make_tool(name="update_startup", description="Change the startup's name, description, current objective or status.",
                  params=UpdateStartupParams, run=_update_startup),
    ]
