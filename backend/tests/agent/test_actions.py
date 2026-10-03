"""Action tools: the agent can change everything the app's UI can."""

from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import Session

from app.agent.registry import default_registry as registry
from app.models.focus_session import FocusSession
from app.models.goal import Goal
from app.models.lead import Lead
from app.models.project import Project
from app.models.recurring_schedule import RecurringSchedule
from app.models.startup import Startup
from app.models.task import Task
from app.models.user import User
from tests.conftest import make_task


@pytest.fixture
def user(db: Session, user_id: int) -> User:
    return db.get(User, user_id)


async def run(db, user, tool, **params):
    return await registry.execute(tool, db, user, params)


def test_every_tool_exports_a_portable_schema():
    for d in registry.list_tool_definitions():
        dumped = json.dumps(d.parameters)
        assert "$ref" not in dumped and "$defs" not in dumped, d.name
        assert d.parameters["type"] == "object" and d.description, d.name


@pytest.mark.asyncio
async def test_projects_crud(db, user):
    res = await run(db, user, "create_project", name="Launch NEXUS beta", area="STARTUP")
    assert res.success, res.error
    pid = res.data["id"]

    res = await run(db, user, "update_project", project_id=pid, status="ACTIVE")
    assert res.success and res.data["status"] == "ACTIVE"

    res = await run(db, user, "get_projects", area="STARTUP")
    assert [p["name"] for p in res.data] == ["Launch NEXUS beta"]

    res = await run(db, user, "delete_project", project_id=pid)
    assert res.success and db.get(Project, pid) is None


@pytest.mark.asyncio
async def test_bulk_update_tasks_applies_one_patch_to_many(db, user):
    ids = [make_task(db, user.id, title=f"T{i}", area="COLLEGE").id for i in range(3)]

    res = await run(db, user, "update_tasks", task_ids=[*ids, 424242], priority="HIGH", area="STARTUP")

    assert res.success
    assert [d["task_id"] for d in res.data["done"]] == ids
    assert [f["task_id"] for f in res.data["failed"]] == [424242]
    for i in ids:
        t = db.get(Task, i)
        db.refresh(t)
        assert (t.priority, t.area) == ("HIGH", "STARTUP")


@pytest.mark.asyncio
async def test_bulk_update_rejects_invalid_values(db, user):
    tid = make_task(db, user.id, title="x").id
    res = await run(db, user, "update_tasks", task_ids=[tid], priority="URGENT-ISH")
    assert not res.success and "Invalid parameters" in res.error


@pytest.mark.asyncio
async def test_update_profile_merges_and_removes_facts(db, user):
    user.facts = {"wake_time": "06:00", "college": "LJ University", "old": "x"}
    db.commit()

    res = await run(
        db, user, "update_profile",
        facts={"wake_time": "06:30", "gym": "07:00-08:00"}, remove_keys=["old"],
    )

    assert res.success, res.error
    db.refresh(user)
    assert user.facts == {"wake_time": "06:30", "college": "LJ University", "gym": "07:00-08:00"}
    assert "wake_time" in res.summary


@pytest.mark.asyncio
async def test_update_profile_validates_timezone(db, user):
    res = await run(db, user, "update_profile", timezone="Mars/Olympus")
    assert not res.success


@pytest.mark.asyncio
async def test_focus_start_and_finish(db, user):
    tid = make_task(db, user.id, title="Deep work").id
    res = await run(db, user, "start_focus", task_id=tid, planned_duration=50)
    assert res.success, res.error

    again = await run(db, user, "start_focus")
    assert not again.success  # one running session at a time, same rule as the app

    res = await run(db, user, "finish_focus", status="PARTIAL")
    assert res.success, res.error
    assert db.query(FocusSession).one().status == "PARTIAL"


@pytest.mark.asyncio
async def test_daily_review_saves_then_updates(db, user):
    res = await run(db, user, "save_daily_review", productivity_rating=3, blockers="Meetings")
    assert res.success, res.error
    assert res.summary.startswith("Saved")
    res = await run(db, user, "save_daily_review", productivity_rating=4)
    assert res.success and res.summary.startswith("Updated")
    assert res.data["productivity_rating"] == 4 and res.data["blockers"] == "Meetings"


@pytest.mark.asyncio
async def test_delete_goal_and_routine(db, user):
    goal = Goal(user_id=user.id, name="Old goal", area="PERSONAL")
    sched = RecurringSchedule(
        user_id=user.id, name="Gym", type="PERSONAL", days_of_week="Mon",
        start_time="07:00", end_time="08:00", is_hard_constraint=False, status="ACTIVE",
    )
    db.add_all([goal, sched])
    db.commit()

    assert (await run(db, user, "delete_goal", goal_id=goal.id)).success
    assert (await run(db, user, "delete_recurring_schedule", schedule_id=sched.id)).success
    assert db.query(Goal).count() == 0 and db.query(RecurringSchedule).count() == 0


@pytest.mark.asyncio
async def test_startup_crm(db, user):
    db.add(Startup(user_id=user.id, name="MARKETORY"))
    db.commit()

    res = await run(db, user, "create_lead", name="Priya Shah", company="GrowthLab", status="CONTACTED")
    assert res.success, res.error  # startup_id defaulted to the user's startup
    lead_id = res.data["id"]

    res = await run(db, user, "update_lead", lead_id=lead_id, status="MEETING")
    assert res.success and res.data["status"] == "MEETING"
    assert (await run(db, user, "get_leads", status="MEETING")).data[0]["name"] == "Priya Shah"

    res = await run(db, user, "create_experiment", name="LinkedIn DM test", hypothesis="DMs beat email")
    assert res.success, res.error
    res = await run(db, user, "update_experiment", experiment_id=res.data["id"], status="COMPLETED",
                    conclusion="DMs got 3x replies")
    assert res.success and res.data["conclusion"] == "DMs got 3x replies"

    res = await run(db, user, "update_startup", current_objective="10 design partners")
    assert res.success and res.data["current_objective"] == "10 design partners"

    assert (await run(db, user, "delete_lead", lead_id=lead_id)).success
    assert db.query(Lead).count() == 0


@pytest.mark.asyncio
async def test_destructive_tools_are_flagged(db, user):
    for name in ("delete_project", "delete_goal", "delete_recurring_schedule", "delete_lead", "delete_tasks"):
        assert registry.get(name).is_destructive, name
        assert "Destructive" in registry.get(name).to_tool_definition().description


# --- Profile facts the scheduler depends on -------------------------------------------


def test_time_facts_are_normalised_and_aliases_folded():
    from app.intelligence.profile_facts import normalize_facts, normalize_hhmm

    assert [normalize_hhmm(v) for v in ("6:30", "06:30", "6.30", "6:30 am", "11:30 PM", "7pm", "12am")] == [
        "06:30", "06:30", "06:30", "06:30", "23:30", "19:00", "00:00",
    ]
    # Legacy alias only -> canonical; both present -> canonical wins; junk dropped on read.
    assert normalize_facts({"wake": "6:00"}) == {"wake_time": "06:00"}
    assert normalize_facts({"wake": "06:00", "wake_time": "06:30"}) == {"wake_time": "06:30"}
    assert normalize_facts({"sleep": "whenever"}) == {}
    with pytest.raises(ValueError):
        normalize_facts({"sleep_time": "around midnight"}, strict=True)


def test_scheduler_honours_updated_times_under_either_key():
    from datetime import datetime

    from app.intelligence.constraint_engine import evaluate_constraints

    noon = datetime(2026, 10, 2, 12, 0)
    assert evaluate_constraints({"sleep": "22:15"}, noon).hard_sleep_time == "22:15"
    assert evaluate_constraints({"sleep": "23:00", "sleep_time": "23:30"}, noon).hard_sleep_time == "23:30"


@pytest.mark.asyncio
async def test_update_profile_writes_canonical_validated_times(db, user):
    user.facts = {"wake": "06:00", "sleep": "23:00", "college": "LJ"}
    db.commit()

    res = await run(db, user, "update_profile", facts={"wake": "6:30 am", "sleep_time": "11:30 pm"})

    assert res.success, res.error
    db.refresh(user)
    assert user.facts == {"wake_time": "06:30", "sleep_time": "23:30", "college": "LJ"}

    bad = await run(db, user, "update_profile", facts={"sleep_time": "late-ish"})
    assert not bad.success and "HH:MM" in bad.error
