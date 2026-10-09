"""Workout plans: save (as pasted from Notion), today's view, gym edits, ticks, IRIS tools, situation."""

from __future__ import annotations

import pytest

from app.agent.registry import default_registry as registry
from app.models.user import User
from app.services import workout_service as ws
from app.services.habit_service import today_for

CST = {
    "name": "CST",
    "focus": "Chest, Shoulders, Triceps",
    "days_of_week": "sun",
    "duration": "75-85 min",
    "exercises": [
        {"name": "Flat Barbell Bench Press", "sets_reps": "4x5-8", "time": "—", "muscles": "Chest, Triceps, Front Delts", "weight": "7.5x2"},
        {"name": "Incline Dumbbell Press", "sets_reps": "3x8-12", "muscles": "Upper Chest, Shoulders", "weight": "7.5x2"},
        {"name": "Barbell Shoulder Press", "sets_reps": "3x8-10", "muscles": "Shoulders, Triceps", "weight": "15"},
        {"name": "Face pulls", "sets_reps": "3x15", "muscles": "Rear delt, traps", "weight": "20"},
        {"name": "Reverse fly", "sets_reps": "2-3x20", "muscles": "Rear delts"},
        {"name": "Dumbbell Lateral Raises", "sets_reps": "3x12-15", "muscles": "Side Delts", "weight": "5x2"},
        {"name": "Skull Crushers", "sets_reps": "3x10-12", "muscles": "Triceps", "weight": ""},
    ],
}


@pytest.fixture
def user(db, user_id) -> User:
    return db.get(User, user_id)


def _today(user) -> str:
    return today_for(user).strftime("%a")


def test_save_plan_as_written(client):
    r = client.post("/api/workouts", json=CST)
    assert r.status_code == 201, r.text
    w = r.json()
    assert (w["name"], w["days_of_week"], w["duration"]) == ("CST", "Sun", "75-85 min")
    names = [e["name"] for e in w["exercises"]]
    assert names[0] == "Flat Barbell Bench Press" and len(names) == 7
    bench = w["exercises"][0]
    assert (bench["sets_reps"], bench["weight"], bench["time"]) == ("4x5-8", "7.5x2", None)  # "—" means empty
    assert w["exercises"][4]["sets_reps"] == "2-3x20"
    assert w["exercises"][6]["weight"] is None


def test_today_ticks_and_gym_edits(client, user):
    w = client.post("/api/workouts", json={**CST, "days_of_week": _today(user)}).json()
    assert w["is_today"] is True and w["done_count"] == 0
    bench, incline = w["exercises"][0]["id"], w["exercises"][1]["id"]

    w = client.post(f"/api/workouts/{w['id']}/exercises/{bench}/check", json={}).json()
    assert w["done_count"] == 1 and w["exercises"][0]["done_today"] is True and w["last_done_on"]
    w = client.post(f"/api/workouts/{w['id']}/exercises/{bench}/check", json={}).json()  # idempotent
    assert w["done_count"] == 1
    w = client.post(f"/api/workouts/{w['id']}/exercises/{bench}/check", json={"done": False}).json()
    assert w["done_count"] == 0

    w = client.patch(f"/api/workouts/{w['id']}/exercises/{incline}", json={"weight": "10x2"}).json()
    assert w["exercises"][1]["weight"] == "10x2" and w["exercises"][1]["name"] == "Incline Dumbbell Press"

    # Replacing the exercise list keeps the plan, drops old exercises.
    w = client.patch(f"/api/workouts/{w['id']}", json={"exercises": [{"name": "Dips", "sets_reps": "3x10"}]}).json()
    assert [e["name"] for e in w["exercises"]] == ["Dips"]
    assert client.post(f"/api/workouts/{w['id']}/exercises/{bench}/check", json={}).status_code == 404


def test_week_order_and_delete(client):
    client.post("/api/workouts", json={"name": "Legs", "days_of_week": "Wed"})
    client.post("/api/workouts", json={"name": "CST", "days_of_week": "Sun"})
    client.post("/api/workouts", json={"name": "Back", "days_of_week": "Mon,Thu"})
    lst = client.get("/api/workouts").json()
    assert [w["name"] for w in lst] == ["Back", "Legs", "CST"]
    assert client.delete(f"/api/workouts/{lst[0]['id']}").status_code == 204
    assert len(client.get("/api/workouts").json()) == 2


@pytest.mark.parametrize("bad", [{"name": ""}, {"days_of_week": "Someday"}, {"exercises": [{"name": ""}]}])
def test_validation(client, bad):
    assert client.post("/api/workouts", json={**CST, **bad}).status_code == 422


async def test_iris_reads_updates_and_ticks(db, user):
    res = await registry.execute("save_workout", db, user, {**CST, "days_of_week": _today(user)})
    assert res.success, res.error
    assert "Saved workout" in res.summary and "7 exercises" in res.summary

    res = await registry.execute("update_exercise", db, user, {"workout": "cst", "exercise": "bench press", "weight": "10x2"})
    assert res.success, res.error
    assert res.data["exercises"][0]["weight"] == "10x2"

    res = await registry.execute("check_exercises", db, user, {"exercises": ["bench", "face pulls", "planks"]})
    assert res.success, res.error
    assert res.summary == "CST: 2/7 done; not found: planks"

    res = await registry.execute("get_workouts", db, user, {"today_only": True})
    assert res.success and res.data[0]["done_count"] == 2


def test_situation_mentions_todays_workout(db, user):
    from app.intelligence.situation import build_situation, render_situation
    from app.schemas.workout import WorkoutIn

    assert build_situation(db, user)["workout"] is None
    ws.create(db, user, WorkoutIn(**{**CST, "days_of_week": _today(user)}))
    text = render_situation(build_situation(db, user))
    assert "WORKOUT TODAY:" in text and "CST (Chest, Shoulders, Triceps): 0/7 exercises done" in text
