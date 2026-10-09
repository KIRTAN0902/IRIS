"""Workout plans: CRUD, today's workout, exercise tick-offs (shared by API, IRIS and situation)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.user import User
from app.models.workout import Workout, WorkoutExercise, WorkoutLog
from app.schemas.workout import ExerciseIn, ExerciseOut, ExerciseUpdate, WorkoutIn, WorkoutOut, WorkoutPatch
from app.services.habit_service import today_for

_DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _get(db: Session, user: User, workout_id: int) -> Workout:
    w = db.query(Workout).filter(Workout.id == workout_id, Workout.user_id == user.id).first()
    if w is None:
        raise NotFoundError("Workout not found.")
    return w


def find(db: Session, user: User, name: str) -> Workout | None:
    needle = name.strip().lower()
    workouts = db.query(Workout).filter(Workout.user_id == user.id).all()
    for test in (
        lambda w: w.name.lower() == needle,
        lambda w: w.name.lower().startswith(needle),
        lambda w: needle in f"{w.name} {w.focus or ''}".lower(),
    ):
        hit = [w for w in workouts if test(w)]
        if hit:
            return hit[0]
    return None


def to_out(db: Session, w: Workout, today: date) -> WorkoutOut:
    done_today = {
        r[0]
        for r in db.query(WorkoutLog.exercise_id).filter(WorkoutLog.workout_id == w.id, WorkoutLog.day == today).all()
    }
    last = db.query(func.max(WorkoutLog.day)).filter(WorkoutLog.workout_id == w.id).scalar()
    exercises = [
        ExerciseOut(
            id=e.id,
            position=e.position,
            name=e.name,
            sets_reps=e.sets_reps,
            time=e.time,
            muscles=e.muscles,
            weight=e.weight,
            notes=e.notes,
            done_today=e.id in done_today,
        )
        for e in w.exercises
    ]
    return WorkoutOut(
        id=w.id,
        name=w.name,
        focus=w.focus,
        days_of_week=w.days_of_week or "",
        duration=w.duration,
        notes=w.notes,
        is_today=today.strftime("%a") in w.days,
        exercises=exercises,
        done_count=sum(e.done_today for e in exercises),
        last_done_on=last,
    )


def _week_key(w: Workout) -> tuple:
    first = min((_DAY_ORDER.index(d) for d in w.days if d in _DAY_ORDER), default=7)
    return (first, w.id)


def list_workouts(db: Session, user: User) -> list[WorkoutOut]:
    today = today_for(user)
    workouts = sorted(db.query(Workout).filter(Workout.user_id == user.id).all(), key=_week_key)
    return [to_out(db, w, today) for w in workouts]


def todays(db: Session, user: User) -> list[WorkoutOut]:
    return [w for w in list_workouts(db, user) if w.is_today]


def _set_exercises(w: Workout, exercises: list[ExerciseIn]) -> None:
    w.exercises.clear()
    for i, e in enumerate(exercises):
        w.exercises.append(WorkoutExercise(position=i, **e.model_dump()))


def create(db: Session, user: User, data: WorkoutIn) -> WorkoutOut:
    w = Workout(user_id=user.id, **data.model_dump(exclude={"exercises"}))
    _set_exercises(w, data.exercises)
    db.add(w)
    db.commit()
    db.refresh(w)
    return to_out(db, w, today_for(user))


def update(db: Session, user: User, workout_id: int, data: WorkoutPatch) -> WorkoutOut:
    w = _get(db, user, workout_id)
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if key == "exercises":
            continue
        if value is None and key in {"name", "days_of_week"}:
            continue
        setattr(w, key, value)
    if data.exercises is not None:
        _set_exercises(w, data.exercises)
    db.commit()
    db.refresh(w)
    return to_out(db, w, today_for(user))


def delete(db: Session, user: User, workout_id: int) -> None:
    db.delete(_get(db, user, workout_id))
    db.commit()


def _exercise(db: Session, user: User, workout_id: int, exercise_id: int) -> tuple[Workout, WorkoutExercise]:
    w = _get(db, user, workout_id)
    e = next((x for x in w.exercises if x.id == exercise_id), None)
    if e is None:
        raise NotFoundError("Exercise not found in this workout.")
    return w, e


def update_exercise(db: Session, user: User, workout_id: int, exercise_id: int, data: ExerciseUpdate) -> WorkoutOut:
    w, e = _exercise(db, user, workout_id, exercise_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        if key == "name" and not value:
            continue
        setattr(e, key, value)
    db.commit()
    db.refresh(w)
    return to_out(db, w, today_for(user))


def check(db: Session, user: User, workout_id: int, exercise_id: int, *, done: bool = True, day: date | None = None) -> WorkoutOut:
    w, e = _exercise(db, user, workout_id, exercise_id)
    day = day or today_for(user)
    existing = db.query(WorkoutLog).filter(WorkoutLog.exercise_id == e.id, WorkoutLog.day == day).first()
    if done and existing is None:
        db.add(WorkoutLog(user_id=user.id, workout_id=w.id, exercise_id=e.id, day=day))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    elif not done and existing is not None:
        db.delete(existing)
        db.commit()
    return to_out(db, w, today_for(user))


def find_exercise(w: WorkoutOut, name: str) -> ExerciseOut | None:
    needle = name.strip().lower()
    for test in (lambda e: e.name.lower() == needle, lambda e: needle in e.name.lower()):
        hit = [e for e in w.exercises if test(e)]
        if hit:
            return hit[0]
    return None


def situation_brief(db: Session, user: User) -> list[dict] | None:
    plans = todays(db, user)
    if not plans:
        return None
    return [
        {"id": w.id, "name": w.name, "focus": w.focus, "done": w.done_count, "total": len(w.exercises)}
        for w in plans
    ]


def render_brief(brief: list[dict] | None) -> list[str]:
    if not brief:
        return []
    lines = ["\nWORKOUT TODAY:"]
    for w in brief:
        focus = f" ({w['focus']})" if w["focus"] else ""
        lines.append(f"- #{w['id']} {w['name']}{focus}: {w['done']}/{w['total']} exercises done (get_workouts for details)")
    return lines
