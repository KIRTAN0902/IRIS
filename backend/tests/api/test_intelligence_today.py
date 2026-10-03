"""Tests for Intelligence & Today API endpoints (Phase 1)."""

from __future__ import annotations

from app.models.enums import InformationProvenance, LifeArea, ScheduleBlockType
from app.models.recurring_schedule import RecurringSchedule
from tests.conftest import hours_from_now, make_goal, make_task


def test_get_today_state_empty_db(client):
    """GET /api/intelligence/today returns a valid today state even on a fresh DB."""
    r = client.get("/api/intelligence/today")
    assert r.status_code == 200
    body = r.json()
    assert "date" in body
    assert "current_time" in body
    assert "user_timezone" in body
    assert body["available_minutes_today"] > 0
    assert "current_window" in body
    assert isinstance(body["fixed_commitments"], list)
    assert isinstance(body["flexible_windows"], list)
    assert isinstance(body["urgent_obligations"], list)
    assert isinstance(body["tasks"], list)
    assert isinstance(body["goals"], list)
    assert "current_recommendation" in body


def test_get_today_state_with_tasks_and_goals(client, db, user_id):
    """GET /api/intelligence/today aggregates open tasks, active goals, and startup state."""
    from app.models.user import User

    from datetime import timedelta

    from app.utils.datetime import to_local, utcnow

    u = db.query(User).filter(User.id == user_id).first()
    if u:
        # Keep "now" well inside waking hours whatever time the suite runs.
        now_local = to_local(utcnow(), u.timezone)
        u.facts = {
            "wake": f"{now_local - timedelta(hours=3):%H:%M}",
            "sleep": f"{now_local + timedelta(hours=10):%H:%M}",
        }
        db.commit()

    goal = make_goal(
        db,
        user_id,
        name="30–50 meaningful conversations",
        target_value=40,
        current_value=10,
        unit="conversations",
    )
    make_task(
        db,
        user_id,
        title="Start founder-led outreach",
        area=LifeArea.STARTUP.value,
        goal_id=goal.id,
        priority="HIGH",
        deadline=hours_from_now(4),
    )

    r = client.get("/api/intelligence/today")
    assert r.status_code == 200
    body = r.json()

    assert len(body["urgent_obligations"]) >= 1
    assert body["urgent_obligations"][0]["title"] == "Start founder-led outreach"
    assert len(body["tasks"]) >= 1
    assert body["current_recommendation"] is not None
    assert body["current_recommendation"]["title"] == "Start founder-led outreach"


def test_recurring_schedules_crud(client, db, user_id):
    """Create, list, update, and delete weekly recurring schedules."""
    # 1. Create
    payload = {
        "name": "Morning Flexible Window",
        "type": ScheduleBlockType.FLEXIBLE.value,
        "days_of_week": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
        "start_time": "09:00",
        "end_time": "10:30",
        "is_hard_constraint": False,
        "status": "ACTIVE",
    }
    r = client.post("/api/intelligence/recurring-schedules", json=payload)
    assert r.status_code == 201
    created = r.json()
    assert created["name"] == "Morning Flexible Window"
    assert created["type"] == ScheduleBlockType.FLEXIBLE.value
    assert created["is_hard_constraint"] is False
    sched_id = created["id"]

    # 2. List
    r_list = client.get("/api/intelligence/recurring-schedules")
    assert r_list.status_code == 200
    items = r_list.json()
    assert any(s["id"] == sched_id for s in items)

    # 3. Update
    r_update = client.patch(
        f"/api/intelligence/recurring-schedules/{sched_id}",
        json={"end_time": "10:45", "name": "Extended Morning Window"},
    )
    assert r_update.status_code == 200
    assert r_update.json()["end_time"] == "10:45"
    assert r_update.json()["name"] == "Extended Morning Window"

    # 4. Delete
    r_del = client.delete(f"/api/intelligence/recurring-schedules/{sched_id}")
    assert r_del.status_code == 204

    # Verify deleted
    r_get_deleted = client.patch(
        f"/api/intelligence/recurring-schedules/{sched_id}",
        json={"name": "Ghost"},
    )
    assert r_get_deleted.status_code == 404


def test_recurring_schedules_distinguish_hard_vs_flexible(db, user_id):
    """Recurring schedules properly distinguish hard constraints from flexible windows."""
    sched_fixed = RecurringSchedule(
        user_id=user_id,
        name="Yoga",
        type=ScheduleBlockType.PERSONAL.value,
        days_of_week="Mon,Tue,Wed,Thu,Fri,Sat,Sun",
        start_time="06:00",
        end_time="07:30",
        is_hard_constraint=True,
    )
    sched_work = RecurringSchedule(
        user_id=user_id,
        name="Internship",
        type=ScheduleBlockType.WORK.value,
        days_of_week="Mon,Tue,Wed,Thu,Fri",
        start_time="11:00",
        end_time="20:00",
        is_hard_constraint=True,
    )
    sched_flex = RecurringSchedule(
        user_id=user_id,
        name="Morning Flexible Window",
        type=ScheduleBlockType.FLEXIBLE.value,
        days_of_week="Mon,Tue,Wed,Thu,Fri,Sat,Sun",
        start_time="09:00",
        end_time="10:30",
        is_hard_constraint=False,
    )
    db.add_all([sched_fixed, sched_work, sched_flex])
    db.commit()

    from datetime import datetime

    from app.intelligence.constraint_engine import evaluate_constraints

    schedules = [sched_fixed, sched_work, sched_flex]
    dt_flex = datetime(2026, 8, 31, 9, 30)  # Monday 09:30
    eval_flex = evaluate_constraints(None, dt_flex, recurring_schedules=schedules)
    assert eval_flex.is_in_hard_constraint is False
    assert eval_flex.is_in_flexible_window is True
    assert eval_flex.active_constraint_name == "Morning Flexible Window"

    dt_work = datetime(2026, 8, 31, 14, 0)  # Monday 14:00
    eval_work = evaluate_constraints(None, dt_work, recurring_schedules=schedules)
    assert eval_work.is_in_hard_constraint is True
    assert eval_work.active_constraint_name == "Internship"


def test_information_provenance_enums():
    """Verify InformationProvenance enum structure."""
    assert InformationProvenance.USER_PROVIDED.value == "USER_PROVIDED"
    assert InformationProvenance.SYSTEM_DERIVED.value == "SYSTEM_DERIVED"
    assert InformationProvenance.AI_INFERRED.value == "AI_INFERRED"
    assert InformationProvenance.UNKNOWN.value == "UNKNOWN"
