"""Goal engine -- evaluates goals, hierarchy, progress, and bottlenecks.

Distinguishes long-term vision, 90-day objectives, and near-term bottlenecks
across College, Internship, Startup, and Personal areas.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import GoalStatus, LifeArea
from app.models.goal import Goal


def analyze_goals(db: Session, user_id: int) -> dict[str, Any]:
    """Extract and analyze structured goals, bottlenecks, and strategic focus."""
    goals = (
        db.query(Goal)
        .filter(Goal.user_id == user_id)
        .filter(Goal.status.in_([GoalStatus.ACTIVE.value, GoalStatus.BEHIND.value]))
        .order_by(Goal.created_at.desc())
        .all()
    )

    startup_goals = []
    college_goals = []
    internship_goals = []
    personal_goals = []

    bottlenecks = []

    for g in goals:
        g_data = {
            "id": g.id,
            "name": g.name,
            "area": g.area,
            "description": g.description,
            "target": g.target_value,
            "current": g.current_value,
            "unit": g.unit,
            "progress_fraction": round(g.progress_fraction, 3),
            "status": g.status,
            "deadline": g.deadline.isoformat() if g.deadline else None,
        }
        if g.status == GoalStatus.BEHIND.value:
            bottlenecks.append(
                {
                    "goal_id": g.id,
                    "area": g.area,
                    "name": g.name,
                    "target": g.target_value,
                    "current": g.current_value,
                    "unit": g.unit,
                    "reason": f"Behind target ({g.current_value}/{g.target_value} {g.unit or ''})",
                }
            )

        if g.area == LifeArea.STARTUP.value:
            startup_goals.append(g_data)
        elif g.area == LifeArea.COLLEGE.value:
            college_goals.append(g_data)
        elif g.area == LifeArea.INTERNSHIP.value:
            internship_goals.append(g_data)
        else:
            personal_goals.append(g_data)

    return {
        "all_active_goals": [
            {
                "id": g.id,
                "name": g.name,
                "area": g.area,
                "progress_fraction": round(g.progress_fraction, 3),
                "status": g.status,
            }
            for g in goals
        ],
        "startup_goals": startup_goals,
        "college_goals": college_goals,
        "internship_goals": internship_goals,
        "personal_goals": personal_goals,
        "identified_bottlenecks": bottlenecks,
    }
