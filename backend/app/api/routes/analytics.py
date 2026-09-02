"""Analytics endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.analytics import (
    ProductivityAnalytics,
    StartupAnalytics,
    StartupTrends,
    TimeAnalytics,
)
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/time", response_model=TimeAnalytics, summary="Hours per life area")
def time_analytics(
    period: str = Query("today", description="today|week|month|custom"),
    start: datetime | None = Query(None, description="Required when period=custom"),
    end: datetime | None = Query(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return analytics_service.time_analytics(
        db, user.id, period=period, tz_name=user.timezone, start=start, end=end
    )


@router.get("/productivity", response_model=ProductivityAnalytics)
def productivity_analytics(
    period: str = Query("week", description="today|week|month|custom"),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return analytics_service.productivity_analytics(
        db, user.id, period=period, tz_name=user.timezone, start=start, end=end
    )


@router.get("/startup", response_model=StartupAnalytics)
def startup_analytics(
    startup_id: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return analytics_service.startup_analytics(db, user.id, startup_id)


@router.get("/startup/trends", response_model=StartupTrends)
def startup_trends(
    weeks: int = Query(8, ge=1, le=26),
    startup_id: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return analytics_service.startup_trends(db, user.id, weeks=weeks, startup_id=startup_id)


@router.get("/priorities", summary="Deterministically ranked open tasks")
def ranked_tasks(
    available_minutes: int | None = Query(None, ge=1, le=24 * 60),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from app.services.context_builder import build_recommendation_context

    context = build_recommendation_context(db, user, available_minutes=available_minutes)
    return _rank(context)[:limit]


def _rank(context: dict):
    from app.schemas.task import RankedTask, TaskOut, TaskPriorityBreakdown

    out = []
    for item in context["ranked_tasks"]:
        out.append(
            RankedTask(
                task=TaskOut.model_validate(item["task"]),
                score=item["priority_score"],
                breakdown=TaskPriorityBreakdown(**item["breakdown"]),
            ).model_dump(mode="json")
        )
    return out
