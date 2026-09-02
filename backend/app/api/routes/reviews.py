"""Daily review endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.core.errors import ConflictError, NotFoundError
from app.models.daily_review import DailyReview
from app.models.user import User
from app.schemas.common import DailyReviewIn, DailyReviewOut, DailyReviewUpdate

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=DailyReviewOut, status_code=201)
def submit_review(
    data: DailyReviewIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(DailyReview)
        .filter(DailyReview.user_id == user.id, DailyReview.date == data.date)
        .first()
    )
    if existing:
        raise ConflictError("A review for this date already exists.", code="REVIEW_EXISTS")

    # Auto-count completed/missed tasks from real data.
    from app.models.task import Task
    from app.utils.datetime import localize_date_boundaries

    day_start, day_end = localize_date_boundaries(data.date, user.timezone)

    n_completed = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.completed_at >= day_start,
            Task.completed_at < day_end,
        )
        .count()
    )
    n_missed = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.deadline.is_not(None),
            Task.deadline >= day_start,
            Task.deadline < day_end,
            Task.status.in_(["TODO", "IN_PROGRESS"]),
        )
        .count()
    )

    review = DailyReview(
        user_id=user.id,
        date=data.date,
        blockers=data.blockers,
        productivity_rating=data.productivity_rating,
        notes=data.notes,
        completed_tasks=n_completed,
        incomplete_tasks=n_missed,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


@router.get("", response_model=list[DailyReviewOut])
def list_reviews(
    limit: int = Query(30, ge=1, le=120),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(DailyReview)
        .filter(DailyReview.user_id == user.id)
        .order_by(DailyReview.date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [DailyReviewOut.model_validate(r) for r in rows]


def _get_review(db: Session, user: User, day: date) -> DailyReview | None:
    return (
        db.query(DailyReview)
        .filter(DailyReview.user_id == user.id, DailyReview.date == day)
        .first()
    )


@router.get("/{day}", response_model=DailyReviewOut)
def get_review(
    day: date,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    review = _get_review(db, user, day)
    if not review:
        raise NotFoundError("No review for that date.", code="REVIEW_NOT_FOUND")
    return review


@router.patch("/{day}", response_model=DailyReviewOut)
def update_review(
    day: date,
    data: DailyReviewUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    review = _get_review(db, user, day)
    if not review:
        raise NotFoundError("No review for that date.", code="REVIEW_NOT_FOUND")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(review, key, value)
    db.commit()
    db.refresh(review)
    return review
