"""Startup module endpoints: startup, leads, outreach, experiments."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.experiment import ExperimentCreate, ExperimentOut, ExperimentUpdate
from app.schemas.goal import GoalCreate, GoalOut, GoalTreeNode, GoalUpdate
from app.schemas.lead import LeadCreate, LeadOut, LeadUpdate
from app.schemas.outreach import OutreachActivityCreate, OutreachActivityOut, OutreachActivityUpdate
from app.schemas.startup import (
    StartupCreate,
    StartupGoalCreate,
    StartupGoalUpdate,
    StartupOut,
    StartupUpdate,
)
from app.services import goal_service, startup_service

router = APIRouter(tags=["startup"])


# --- Startup -------------------------------------------------------------------


@router.get("/startup", response_model=list[StartupOut])
def get_startup(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return [StartupOut.model_validate(s) for s in startup_service.list_startups(db, user.id)]


@router.post("/startup", response_model=StartupOut, status_code=status.HTTP_201_CREATED)
def create_startup(
    data: StartupCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return StartupOut.model_validate(startup_service.create_startup(db, user.id, data.model_dump()))


@router.patch("/startup/{startup_id}", response_model=StartupOut)
def update_startup(
    startup_id: int,
    data: StartupUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    updates = data.model_dump(exclude_unset=True)
    return StartupOut.model_validate(
        startup_service.update_startup(db, user.id, startup_id, updates)
    )


# --- Startup goals (reuse hierarchical Goal model with area=STARTUP) -----------


@router.post("/startup/goals", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
def create_startup_goal(
    data: StartupGoalCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    goal_data = data.model_dump()
    goal_data["area"] = "STARTUP"
    goal = goal_service.create_goal(db, user.id, GoalCreate(**goal_data))
    return GoalOut.model_validate(goal)


@router.get("/startup/goals", response_model=list[GoalTreeNode])
def list_startup_goals(
    tree: bool = Query(True, description="Return as parent/child tree"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    goals = goal_service.list_goals(db, user.id, area="STARTUP")
    if tree:
        return goal_service.build_tree(goals)
    return [GoalOut.model_validate(g) for g in goals]


@router.patch("/startup/goals/{goal_id}", response_model=GoalOut)
def update_startup_goal(
    goal_id: int,
    data: StartupGoalUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from app.services.goal_service import get_goal

    existing = get_goal(db, user.id, goal_id)
    if existing.area != "STARTUP":
        from app.core.errors import NotFoundError

        raise NotFoundError("Not a startup goal.", code="GOAL_NOT_FOUND")
    updated = goal_service.update_goal(
        db, user.id, goal_id, GoalUpdate(**data.model_dump(exclude_unset=True))
    )
    return GoalOut.model_validate(updated)


# --- Leads ----------------------------------------------------------------------


@router.get("/leads", response_model=list[LeadOut])
def list_leads(
    startup_id: int | None = None,
    lead_status: str | None = Query(None, alias="status"),
    follow_up_due: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    leads, _total = startup_service.list_leads(
        db,
        user.id,
        startup_id=startup_id,
        status=lead_status,
        follow_up_due=follow_up_due,
        limit=limit,
        offset=offset,
    )
    return [LeadOut.model_validate(lead) for lead in leads]


@router.post("/leads", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(
    data: LeadCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return LeadOut.model_validate(startup_service.create_lead(db, user.id, data.model_dump()))


@router.get("/leads/{lead_id}", response_model=LeadOut)
def get_lead(
    lead_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return LeadOut.model_validate(startup_service.get_lead(db, user.id, lead_id))


@router.patch("/leads/{lead_id}", response_model=LeadOut)
def update_lead(
    lead_id: int,
    data: LeadUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return LeadOut.model_validate(
        startup_service.update_lead(db, user.id, lead_id, data.model_dump(exclude_unset=True))
    )


@router.delete("/leads/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead(
    lead_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    startup_service.delete_lead(db, user.id, lead_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Outreach ---------------------------------------------------------------


@router.post("/outreach", response_model=OutreachActivityOut, status_code=status.HTTP_201_CREATED)
def log_outreach(
    data: OutreachActivityCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    activity = startup_service.log_outreach(
        db,
        user.id,
        data.model_dump(),
        update_lead_status=data.update_lead_status,
    )
    return OutreachActivityOut.model_validate(activity)


@router.get("/outreach", response_model=list[OutreachActivityOut])
def list_outreach(
    startup_id: int | None = None,
    lead_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from app.models.outreach import OutreachActivity
    from app.models.startup import Startup

    q = (
        db.query(OutreachActivity)
        .join(Startup, OutreachActivity.startup_id == Startup.id)
        .filter(Startup.user_id == user.id)
    )
    if startup_id:
        q = q.filter(OutreachActivity.startup_id == startup_id)
    if lead_id:
        q = q.filter(OutreachActivity.lead_id == lead_id)
    rows = q.order_by(OutreachActivity.timestamp.desc()).offset(offset).limit(limit).all()
    return [OutreachActivityOut.model_validate(a) for a in rows]


@router.patch("/outreach/{activity_id}", response_model=OutreachActivityOut)
def update_outreach(
    activity_id: int,
    data: OutreachActivityUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return OutreachActivityOut.model_validate(
        startup_service.update_outreach(
            db, user.id, activity_id, data.model_dump(exclude_unset=True)
        )
    )


# --- Experiments ------------------------------------------------------------


@router.get("/experiments", response_model=list[ExperimentOut])
def list_experiments(
    startup_id: int | None = None,
    experiment_status: str | None = Query(None, alias="status"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = startup_service.list_experiments(
        db, user.id, startup_id=startup_id, status=experiment_status
    )
    return [ExperimentOut.model_validate(e) for e in rows]


@router.post("/experiments", response_model=ExperimentOut, status_code=status.HTTP_201_CREATED)
def create_experiment(
    data: ExperimentCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return ExperimentOut.model_validate(
        startup_service.create_experiment(db, user.id, data.model_dump())
    )


@router.patch("/experiments/{experiment_id}", response_model=ExperimentOut)
def update_experiment(
    experiment_id: int,
    data: ExperimentUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return ExperimentOut.model_validate(
        startup_service.update_experiment(
            db, user.id, experiment_id, data.model_dump(exclude_unset=True)
        )
    )
