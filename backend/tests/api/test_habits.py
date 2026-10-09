"""Routines: tick-offs, streak rules, API, IRIS's tools and situation."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.agent.registry import default_registry as registry
from app.models.habit import Habit
from app.models.user import User
from app.services import habit_service as hs


@pytest.fixture
def user(db, user_id) -> User:
    return db.get(User, user_id)


def _habit(days="Mon,Tue,Wed,Thu,Fri,Sat,Sun", created=date(2026, 9, 1)) -> Habit:
    return Habit(name="Gym", days_of_week=days, created_at=datetime.combine(created, datetime.min.time()))


THU = date(2026, 10, 8)  # a Thursday


def test_streak_counts_consecutive_done_days():
    done = {THU - timedelta(days=i) for i in range(5)}
    assert hs.streaks(_habit(), done, THU) == (5, 5)


def test_today_not_done_yet_does_not_break_streak():
    done = {THU - timedelta(days=i) for i in range(1, 4)}  # Mon..Wed, not today
    assert hs.streaks(_habit(), done, THU)[0] == 3


def test_missed_day_breaks_streak_but_best_remembers():
    done = {THU - timedelta(days=i) for i in (0, 1, 3, 4, 5, 6)}  # missed 2 days ago
    assert hs.streaks(_habit(), done, THU) == (2, 4)


def test_unscheduled_days_are_skipped():
    gym = _habit("Mon,Wed,Fri")
    # Fri 2 Oct, Mon 5, Wed 7 done; Thu 8 (today) isn't a gym day.
    done = {date(2026, 10, 2), date(2026, 10, 5), date(2026, 10, 7)}
    assert hs.streaks(gym, done, THU)[0] == 3


def test_routine_api_flow(client):
    r = client.post("/api/habits", json={"name": "Gym", "days_of_week": "mon, wed ,fri", "time": "18:5"})
    assert r.status_code == 201, r.text
    gym = r.json()
    assert gym["days_of_week"] == "Mon,Wed,Fri" and gym["time"] == "18:05"
    assert len(gym["last_7"]) == 7

    yoga = client.post("/api/habits", json={"name": "Yoga", "time": "06:00"}).json()
    assert yoga["scheduled_today"] is True and yoga["done_today"] is False

    checked = client.post(f"/api/habits/{yoga['id']}/check", json={}).json()
    assert checked["done_today"] is True and checked["streak"] == 1 and checked["last_7"][-1]["done"] is True
    again = client.post(f"/api/habits/{yoga['id']}/check", json={}).json()  # idempotent
    assert again["streak"] == 1
    undone = client.post(f"/api/habits/{yoga['id']}/check", json={"done": False}).json()
    assert undone["done_today"] is False and undone["streak"] == 0

    names = [h["name"] for h in client.get("/api/habits").json()]
    assert names == ["Yoga", "Gym"]  # sorted by time

    assert client.patch(f"/api/habits/{gym['id']}", json={"active": False}).json()["active"] is False
    assert client.delete(f"/api/habits/{gym['id']}").status_code == 204
    assert client.post(f"/api/habits/{gym['id']}/check", json={}).status_code == 404


@pytest.mark.parametrize("bad", [{"days_of_week": "Funday"}, {"days_of_week": ""}, {"time": "25:00"}, {"name": ""}])
def test_routine_validation(client, bad):
    assert client.post("/api/habits", json={"name": "Read", **bad}).status_code == 422


async def test_iris_ticks_off_routines_by_name(db, user):
    res = await registry.execute("create_routine", db, user, {"name": "Gym", "time": "18:30"})
    assert res.success, res.error
    res = await registry.execute("check_routine", db, user, {"name": "gym"})
    assert res.success and res.summary == "Gym done"
    res = await registry.execute("get_routines", db, user, {})
    assert res.summary == "1/1 routines done today"
    res = await registry.execute("check_routine", db, user, {"name": "swimming"})
    assert not res.success and "No routine called 'swimming'" in res.error


def test_situation_lists_todays_routines(db, user):
    from app.intelligence.situation import build_situation, render_situation
    from app.schemas.habit import HabitCreate

    assert build_situation(db, user)["routines"] is None
    yoga = hs.create(db, user, HabitCreate(name="Yoga", time="06:00"))
    hs.create(db, user, HabitCreate(name="Gym", time="18:30"))
    hs.check(db, user, yoga.id)
    text = render_situation(build_situation(db, user))
    assert "ROUTINES TODAY (1/2 done)" in text
    assert f"#{yoga.id} Yoga 06:00: done" in text and "Gym 18:30: not yet" in text


def test_routine_duration_and_description(client, db, user):
    from app.intelligence.situation import build_situation, render_situation

    r = client.post(
        "/api/habits",
        json={"name": "Yoga", "time": "06:00", "duration_min": 90, "description": "Surya namaskar x12, pranayama 10 min"},
    )
    assert r.status_code == 201, r.text
    yoga = r.json()
    assert yoga["duration_min"] == 90 and yoga["description"].startswith("Surya")
    yoga = client.patch(f"/api/habits/{yoga['id']}", json={"description": None}).json()
    assert yoga["description"] is None and yoga["duration_min"] == 90
    client.patch(f"/api/habits/{yoga['id']}", json={"description": "Sun salutations"})
    assert "Yoga 06:00 (90m): not yet - Sun salutations" in render_situation(build_situation(db, user))
    assert client.post("/api/habits", json={"name": "Nap", "duration_min": 0}).status_code == 422
