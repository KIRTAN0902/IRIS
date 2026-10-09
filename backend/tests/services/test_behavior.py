"""Behaviour model: follow-through patterns from real-shaped history, and how IRIS adapts."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.intelligence.behavior import observe_behavior, render_behavior
from app.models.finance import FinanceTransaction
from app.models.habit import Habit, HabitLog
from app.models.task import Task
from app.models.user import User
from app.models.workout import Workout, WorkoutExercise, WorkoutLog
from app.utils.datetime import to_local, utcnow


@pytest.fixture
def user(db, user_id) -> User:
    u = db.get(User, user_id)
    u.timezone = "Asia/Kolkata"
    db.commit()
    return u


def _today(user):
    return to_local(utcnow(), user.timezone).date()


def test_new_user_is_still_learning(db, user):
    b = observe_behavior(db, user)
    assert b["confidence"] == "early" and b["consistency_score"] is None and b["adapt"] == []
    text = "\n".join(render_behavior(b))
    assert "Still learning" in text


def test_deadline_reliability_and_slipping_area(db, user):
    now = utcnow()
    for i in range(10):
        deadline = now - timedelta(days=i + 1)
        if i < 4:  # on time
            t = Task(user_id=user.id, title=f"t{i}", area="STARTUP", deadline=deadline, status="COMPLETED", completed_at=deadline - timedelta(hours=2))
        elif i < 7:  # late by ~2 days
            t = Task(user_id=user.id, title=f"t{i}", area="COLLEGE", deadline=deadline, status="COMPLETED", completed_at=deadline + timedelta(days=2))
        else:  # still open
            t = Task(user_id=user.id, title=f"t{i}", area="COLLEGE", deadline=deadline, status="TODO")
        db.add(t)
    db.commit()

    d = observe_behavior(db, user)["deadlines"]
    assert (d["on_time"], d["late"], d["missed"], d["on_time_pct"]) == (4, 3, 3, 40)
    assert d["slipping_area"] == "COLLEGE" and d["typical_delay"] == "2.0 days"
    b = observe_behavior(db, user)
    assert any("often miss deadlines (40% on time, especially college work)" in a["iris"] for a in b["adapt"])
    assert any("You finish 40% of tasks by their deadline" in a["you"] for a in b["adapt"])
    assert "Deadlines: 40% on time (4 on time, 3 late, 3 missed of 10)" in "\n".join(render_behavior(b))


def test_routine_consistency_weak_weekday_and_trend(db, user):
    today = _today(user)
    created = datetime.combine(today - timedelta(days=40), datetime.min.time())
    gym = Habit(user_id=user.id, name="Gym", days_of_week="Mon,Tue,Wed,Thu,Fri,Sat,Sun", created_at=created)
    db.add(gym)
    db.commit()
    for i in range(1, 29):
        day = today - timedelta(days=i)
        recent = i <= 14
        # Never on Mondays; otherwise every day recently, every other day before.
        if day.weekday() != 0 and (recent or i % 2 == 0):
            db.add(HabitLog(habit_id=gym.id, user_id=user.id, day=day))
    db.commit()

    r = observe_behavior(db, user)["routines"]
    assert r["enough"] and r["weakest_day"]["day"] == "Mon" and r["weakest_day"]["pct"] == 0
    assert r["trend"]["direction"] == "improving"
    adapt = " ".join(a["iris"] for a in observe_behavior(db, user)["adapt"])
    assert "Mon is their weakest routine day" in adapt


def test_workout_follow_through(db, user):
    today = _today(user)
    created = datetime.combine(today - timedelta(days=40), datetime.min.time())
    w = Workout(user_id=user.id, name="Full body", days_of_week="Mon,Tue,Wed,Thu,Fri,Sat,Sun", created_at=created)
    w.exercises = [WorkoutExercise(position=i, name=f"E{i}") for i in range(4)]
    db.add(w)
    db.commit()
    for i in range(1, 29):
        day = today - timedelta(days=i)
        n = 4 if i % 3 == 0 else 2 if i % 3 == 1 else 0  # full / partial / skipped
        for e in w.exercises[:n]:
            db.add(WorkoutLog(user_id=user.id, workout_id=w.id, exercise_id=e.id, day=day))
    db.commit()

    wk = observe_behavior(db, user)["workouts"]
    assert wk["samples"] == 28 and (wk["full"], wk["partial"], wk["skipped"]) == (9, 10, 9)
    assert any("Skips planned workouts" in a["iris"] for a in observe_behavior(db, user)["adapt"])


def test_spending_vs_last_month(db, user):
    today = _today(user)
    first = today.replace(day=1)
    prev = (first - timedelta(days=1)).replace(day=1)
    # Same days of the month as today has had, so "this month so far" and "last month at this point" line up.
    for i in range(5):
        day = min(i, today.day - 1)
        db.add(FinanceTransaction(user_id=user.id, kind="EXPENSE", amount=500, category="Food & Dining", account="UPI", occurred_on=first + timedelta(days=day)))
        db.add(FinanceTransaction(user_id=user.id, kind="EXPENSE", amount=200, category="Food & Dining", account="UPI", occurred_on=prev + timedelta(days=day)))
    db.add_all(
        FinanceTransaction(user_id=user.id, kind="EXPENSE", amount=50, category="Transport", account="UPI", occurred_on=prev + timedelta(days=20))
        for _ in range(4)
    )
    db.commit()

    m = observe_behavior(db, user)["money"]
    assert m["enough"] and m["top_category"] == "Food & Dining" and m["change_pct"] == 150
    assert any("Spending is running 150% above last month" in a["iris"] for a in observe_behavior(db, user)["adapt"])


def test_behavior_reaches_irises_prompt_and_api(client, db, user):
    from app.intelligence.personal_model import build_personal_model, render_personal_model

    text = render_personal_model(build_personal_model(db, user))
    assert "HOW THEY FOLLOW THROUGH" in text
    body = client.get("/api/assistant/behavior").json()
    assert set(body) >= {"deadlines", "routines", "workouts", "money", "engagement", "consistency_score", "confidence", "adapt"}
