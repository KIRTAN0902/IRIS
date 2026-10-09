"""Routine (habit) endpoints: list with today's status and streaks, tick off, manage."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.habit import HabitCheck, HabitCreate, HabitOut, HabitUpdate
from app.services import habit_service

router = APIRouter(prefix="/habits", tags=["habits"])


@router.get("", response_model=list[HabitOut])
def list_habits(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return habit_service.list_habits(db, user)


@router.post("", response_model=HabitOut, status_code=status.HTTP_201_CREATED)
def create_habit(data: HabitCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return habit_service.create(db, user, data)


@router.patch("/{habit_id}", response_model=HabitOut)
def update_habit(habit_id: int, data: HabitUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return habit_service.update(db, user, habit_id, data)


@router.post("/{habit_id}/check", response_model=HabitOut)
def check_habit(habit_id: int, data: HabitCheck | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = data or HabitCheck()
    return habit_service.check(db, user, habit_id, done=data.done, day=data.day)


@router.delete("/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_habit(habit_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    habit_service.delete(db, user, habit_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
