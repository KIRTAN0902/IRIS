"""Goal service -- hierarchical goals, progress, tree building."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.models.enums import GoalStatus
from app.models.goal import Goal
from app.schemas.goal import GoalCreate, GoalTreeNode, GoalUpdate

MAX_DEPTH = 6


def list_goals(
    db: Session, user_id: int, *, area: str | None = None, status: str | None = None
) -> list[Goal]:
    q = db.query(Goal).filter(Goal.user_id == user_id)
    if area:
        q = q.filter(Goal.area == area)
    if status:
        q = q.filter(Goal.status == status)
    return q.order_by(Goal.created_at.asc()).all()


def get_goal(db: Session, user_id: int, goal_id: int) -> Goal:
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user_id).first()
    if not goal:
        raise NotFoundError("Goal not found.", code="GOAL_NOT_FOUND")
    return goal


def _validate_parent(db: Session, user_id: int, parent_goal_id: int | None) -> None:
    if parent_goal_id is None:
        return
    parent = db.query(Goal).filter(Goal.id == parent_goal_id, Goal.user_id == user_id).first()
    if not parent:
        raise NotFoundError("Parent goal not found.", code="GOAL_NOT_FOUND")


def create_goal(db: Session, user_id: int, data: GoalCreate) -> Goal:
    _validate_parent(db, user_id, data.parent_goal_id)
    goal = Goal(user_id=user_id, **data.model_dump())
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def update_goal(db: Session, user_id: int, goal_id: int, data: GoalUpdate) -> Goal:
    goal = get_goal(db, user_id, goal_id)
    updates = data.model_dump(exclude_unset=True)

    new_parent = updates.get("parent_goal_id", goal.parent_goal_id)
    if new_parent == goal_id:
        raise ConflictError("A goal cannot be its own parent.", code="GOAL_CYCLE")
    _validate_parent(db, user_id, new_parent)
    if new_parent is not None:
        # Walk up the chain from the new parent to prevent cycles.
        cursor, depth = new_parent, 0
        while cursor is not None and depth <= MAX_DEPTH:
            if cursor == goal_id:
                raise ConflictError("Goal hierarchy cycle detected.", code="GOAL_CYCLE")
            parent_row: Goal | None = (
                db.query(Goal).filter(Goal.id == cursor, Goal.user_id == user_id).first()
            )
            cursor = parent_row.parent_goal_id if parent_row else None
            depth += 1
        if depth > MAX_DEPTH + 1:
            raise ConflictError("Goal hierarchy too deep.", code="GOAL_CYCLE")

    for key, value in updates.items():
        setattr(goal, key, value)

    # Auto-achieve when numeric target reached.
    if (
        goal.target_value is not None
        and goal.current_value >= goal.target_value
        and goal.status == GoalStatus.ACTIVE.value
    ):
        goal.status = GoalStatus.ACHIEVED.value

    db.commit()
    db.refresh(goal)
    return goal


def delete_goal(db: Session, user_id: int, goal_id: int) -> None:
    goal = get_goal(db, user_id, goal_id)
    if goal.children:
        raise ConflictError("Delete or re-parent child goals first.", code="GOAL_HAS_CHILDREN")
    db.delete(goal)
    db.commit()


def build_tree(goals: list[Goal]) -> list[GoalTreeNode]:
    by_parent: dict[int | None, list[Goal]] = {}
    for g in goals:
        by_parent.setdefault(g.parent_goal_id, []).append(g)

    def node(g: Goal, depth: int) -> GoalTreeNode:
        if depth > MAX_DEPTH:
            raise ValidationAppError("Goal nesting too deep.")
        return GoalTreeNode(
            **_goal_out_fields(g),
            children=[node(child, depth + 1) for child in by_parent.get(g.id, [])],
        )

    roots = by_parent.get(None, [])
    goal_ids = {g.id for g in goals}
    orphaned = [
        g for g in goals if g.parent_goal_id is not None and g.parent_goal_id not in goal_ids
    ]
    return [node(r, 0) for r in roots] + [node(o, 0) for o in orphaned]


def _goal_out_fields(g: Goal) -> dict:
    return {
        "id": g.id,
        "user_id": g.user_id,
        "name": g.name,
        "description": g.description,
        "parent_goal_id": g.parent_goal_id,
        "area": g.area,
        "deadline": g.deadline,
        "target_value": g.target_value,
        "current_value": g.current_value,
        "unit": g.unit,
        "status": g.status,
        "progress_fraction": g.progress_fraction,
        "created_at": g.created_at,
        "updated_at": g.updated_at,
    }


def active_goals(db: Session, user_id: int) -> list[Goal]:
    return (
        db.query(Goal)
        .filter(
            Goal.user_id == user_id,
            Goal.status.in_([GoalStatus.ACTIVE.value, GoalStatus.BEHIND.value]),
        )
        .order_by(Goal.deadline.asc().nulls_last())
        .all()
    )
