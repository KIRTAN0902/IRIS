"""Goal endpoints (hierarchical)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.goal import GoalCreate, GoalOut, GoalTreeNode, GoalUpdate
from app.services import goal_service

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("", response_model=list[GoalOut] | list[GoalTreeNode])
def list_goals(
    area: str | None = Query(None),
    goal_status: str | None = Query(None, alias="status"),
    tree: bool = Query(True, description="Return as parent/child tree"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    goals = goal_service.list_goals(db, user.id, area=area, status=goal_status)
    if tree:
        return goal_service.build_tree(goals)
    return [GoalOut.model_validate(g) for g in goals]


@router.post("", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
def create_goal(
    data: GoalCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return GoalOut.model_validate(goal_service.create_goal(db, user.id, data))


@router.get("/{goal_id}", response_model=GoalOut)
def get_goal(
    goal_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return GoalOut.model_validate(goal_service.get_goal(db, user.id, goal_id))


@router.patch("/{goal_id}", response_model=GoalOut)
def update_goal(
    goal_id: int,
    data: GoalUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return GoalOut.model_validate(goal_service.update_goal(db, user.id, goal_id, data))


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(
    goal_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    goal_service.delete_goal(db, user.id, goal_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
