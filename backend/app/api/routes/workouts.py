"""Workout plan endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.workout import ExerciseCheck, ExerciseUpdate, WorkoutIn, WorkoutOut, WorkoutPatch
from app.services import workout_service as ws

router = APIRouter(prefix="/workouts", tags=["workouts"])


@router.get("", response_model=list[WorkoutOut])
def list_workouts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """All plans in week order, with today's ticks."""
    return ws.list_workouts(db, user)


@router.post("", response_model=WorkoutOut, status_code=status.HTTP_201_CREATED)
def create_workout(data: WorkoutIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return ws.create(db, user, data)


@router.patch("/{workout_id}", response_model=WorkoutOut)
def update_workout(workout_id: int, data: WorkoutPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return ws.update(db, user, workout_id, data)


@router.delete("/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workout(workout_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ws.delete(db, user, workout_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{workout_id}/exercises/{exercise_id}", response_model=WorkoutOut)
def update_exercise(
    workout_id: int,
    exercise_id: int,
    data: ExerciseUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Quick edits at the gym, e.g. a new weight."""
    return ws.update_exercise(db, user, workout_id, exercise_id, data)


@router.post("/{workout_id}/exercises/{exercise_id}/check", response_model=WorkoutOut)
def check_exercise(
    workout_id: int,
    exercise_id: int,
    data: ExerciseCheck | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    data = data or ExerciseCheck()
    return ws.check(db, user, workout_id, exercise_id, done=data.done, day=data.day)
