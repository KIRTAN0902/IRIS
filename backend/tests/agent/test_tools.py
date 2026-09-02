"""Comprehensive tests for Agent Tools (read & write & safety)."""

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.agent.tools.goals import CreateGoalTool, GetGoalsTool, UpdateGoalTool
from app.agent.tools.intelligence import (
    GetAttentionItemsTool,
    GetDecisionRecommendationTool,
    GetTodayStateTool,
    RecordDecisionFeedbackTool,
)
from app.agent.tools.schedule import (
    CreateRecurringScheduleTool,
    CreateTimeBlockTool,
    DeleteTimeBlockTool,
    GetRecurringSchedulesTool,
    GetScheduleTool,
    UpdateTimeBlockTool,
)
from app.agent.tools.tasks import (
    CompleteTaskTool,
    CreateTaskTool,
    DeleteTaskTool,
    GetTasksTool,
    GetTaskTool,
    UpdateTaskTool,
)
from app.models.ai_recommendation import AIRecommendation
from app.models.enums import LifeArea, TaskPriority
from app.models.user import User
from app.utils.datetime import utcnow


@pytest.fixture
def test_user(db: Session) -> User:
    user = db.query(User).filter(User.email == "founder@iris.local").first()
    if not user:
        user = User(
            email="founder@iris.local",
            name="Kirtan Founder",
            timezone="Asia/Kolkata",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_task_tools_lifecycle(db: Session, test_user: User):
    create_tool = CreateTaskTool()
    get_tool = GetTaskTool()
    list_tool = GetTasksTool()
    update_tool = UpdateTaskTool()
    complete_tool = CompleteTaskTool()
    delete_tool = DeleteTaskTool()

    # 1. Create task
    res = await create_tool.execute(
        db,
        test_user,
        title="Agentic AI Assignment",
        area=LifeArea.COLLEGE.value,
        priority=TaskPriority.HIGH.value,
        estimated_duration=90,
    )
    assert res.success is True
    task_id = res.data["task_id"]

    # 2. Get task
    res_get = await get_tool.execute(db, test_user, task_id=task_id)
    assert res_get.success is True
    assert res_get.data["title"] == "Agentic AI Assignment"

    # 3. List tasks
    res_list = await list_tool.execute(db, test_user, area=LifeArea.COLLEGE.value)
    assert res_list.success is True
    assert any(t["id"] == task_id for t in res_list.data["tasks"])

    # 4. Update task
    res_up = await update_tool.execute(
        db, test_user, task_id=task_id, priority=TaskPriority.CRITICAL.value
    )
    assert res_up.success is True

    # 5. Complete task
    res_comp = await complete_tool.execute(db, test_user, task_id=task_id, actual_duration=75)
    assert res_comp.success is True

    # 6. Delete task
    res_del = await delete_tool.execute(db, test_user, task_id=task_id)
    assert res_del.success is True


@pytest.mark.asyncio
async def test_schedule_tools_lifecycle(db: Session, test_user: User):
    create_block = CreateTimeBlockTool()
    get_sched = GetScheduleTool()
    update_block = UpdateTimeBlockTool()
    del_block = DeleteTimeBlockTool()

    now = utcnow()
    start = now + timedelta(hours=1)
    end = start + timedelta(minutes=45)

    # 1. Create block
    res = await create_block.execute(
        db, test_user, start_time=start, end_time=end, notes="Focus on compiler"
    )
    assert res.success is True
    block_id = res.data["block_id"]

    # 2. Get schedule
    res_get = await get_sched.execute(db, test_user, start=now, end=now + timedelta(days=1))
    assert res_get.success is True
    assert any(b["id"] == block_id for b in res_get.data["time_blocks"])

    # 3. Update block
    res_up = await update_block.execute(db, test_user, block_id=block_id, notes="Updated notes")
    assert res_up.success is True

    # 4. Delete block
    res_del = await del_block.execute(db, test_user, block_id=block_id)
    assert res_del.success is True


@pytest.mark.asyncio
async def test_recurring_schedule_tools(db: Session, test_user: User):
    create_rec = CreateRecurringScheduleTool()
    get_rec = GetRecurringSchedulesTool()

    res = await create_rec.execute(
        db,
        test_user,
        name="Morning Yoga Routine",
        start_time="06:30",
        end_time="07:15",
        days_of_week="Mon,Wed,Fri",
        is_hard_constraint=True,
    )
    assert res.success is True

    res_list = await get_rec.execute(db, test_user)
    assert res_list.success is True
    assert any(r["name"] == "Morning Yoga Routine" for r in res_list.data["recurring_schedules"])


@pytest.mark.asyncio
async def test_goal_tools(db: Session, test_user: User):
    create_goal = CreateGoalTool()
    get_goals = GetGoalsTool()
    update_goal = UpdateGoalTool()

    res = await create_goal.execute(
        db,
        test_user,
        name="Close 5 Pilot Customers",
        area=LifeArea.STARTUP.value,
        target_value=5.0,
        current_value=0.0,
        unit="customers",
    )
    assert res.success is True
    goal_id = res.data["goal_id"]

    res_up = await update_goal.execute(db, test_user, goal_id=goal_id, current_value=2.0)
    assert res_up.success is True

    res_list = await get_goals.execute(db, test_user, area=LifeArea.STARTUP.value)
    assert res_list.success is True
    assert any(g["id"] == goal_id for g in res_list.data["goals"])


@pytest.mark.asyncio
async def test_intelligence_and_feedback_tools(db: Session, test_user: User):
    today_tool = GetTodayStateTool()
    attn_tool = GetAttentionItemsTool()
    rec_tool = GetDecisionRecommendationTool()
    fb_tool = RecordDecisionFeedbackTool()

    # 1. Today state
    res_today = await today_tool.execute(db, test_user)
    assert res_today.success is True
    assert "available_minutes" in res_today.data

    # 2. Attention items
    res_attn = await attn_tool.execute(db, test_user)
    assert res_attn.success is True

    # 3. Recommendation
    res_rec = await rec_tool.execute(db, test_user, available_minutes=60, use_ai=False)
    assert res_rec.success is True
    assert res_rec.data["decision_type"] is not None

    # 4. Feedback
    ai_rec = AIRecommendation(
        user_id=test_user.id,
        title="Test recommendation",
        decision_type="SHOULD_DO",
        source="DETERMINISTIC",
        confidence=0.85,
    )
    db.add(ai_rec)
    db.commit()
    db.refresh(ai_rec)

    res_fb = await fb_tool.execute(db, test_user, recommendation_id=ai_rec.id, feedback="ACCEPTED")
    assert res_fb.success is True


@pytest.mark.asyncio
async def test_tool_safety_and_validation(db: Session, test_user: User):
    get_task = GetTaskTool()

    # Non-existent task ID
    res_missing = await get_task.execute(db, test_user, task_id=999999)
    assert res_missing.success is False

    # Invalid parameter types
    create_task = CreateTaskTool()
    res_invalid = await create_task.execute(db, test_user, title="", area="INVALID_AREA")
    assert res_invalid.success is False


@pytest.mark.asyncio
async def test_newly_added_read_write_tools(db: Session, test_user: User):
    from app.agent.tools.intelligence import (
        GetCurrentRecommendationTool,
        GetCurrentStateTool,
        GetDecisionHistoryTool,
    )
    from app.agent.tools.schedule import UpdateRecurringScheduleTool
    from app.agent.tools.startup import GetOutreachStatusTool, GetStartupStatusTool, LogOutreachTool
    from app.models.lead import Lead
    from app.models.recurring_schedule import RecurringSchedule
    from app.models.startup import Startup

    # 1. GetCurrentState & GetCurrentRecommendation
    state_tool = GetCurrentStateTool()
    res_state = await state_tool.execute(db, test_user)
    assert res_state.success is True
    assert res_state.tool_name == "get_current_state"

    rec_tool = GetCurrentRecommendationTool()
    res_rec = await rec_tool.execute(db, test_user, available_minutes=45, use_ai=False)
    assert res_rec.success is True
    assert res_rec.tool_name == "get_current_recommendation"

    # 2. GetDecisionHistoryTool
    hist_tool = GetDecisionHistoryTool()
    res_hist = await hist_tool.execute(db, test_user, limit=5)
    assert res_hist.success is True
    assert "decisions" in res_hist.data

    # 3. Startup & Outreach Tools
    startup = Startup(user_id=test_user.id, name="Test Startup", status="LAUNCHED")
    db.add(startup)
    db.commit()
    db.refresh(startup)

    lead = Lead(startup_id=startup.id, name="Alice", company="Acme Corp", email="alice@acme.test")
    db.add(lead)
    db.commit()
    db.refresh(lead)

    log_tool = LogOutreachTool()
    res_log = await log_tool.execute(
        db, test_user, lead_id=lead.id, type="EMAIL", result="SENT", message="Demo pitch"
    )
    assert res_log.success is True

    outreach_tool = GetOutreachStatusTool()
    res_out = await outreach_tool.execute(db, test_user)
    assert res_out.success is True
    assert res_out.data["total_outreach"] >= 1

    status_tool = GetStartupStatusTool()
    res_stat = await status_tool.execute(db, test_user)
    assert res_stat.success is True
    assert res_stat.data["startup_name"] == "Test Startup"

    # 4. UpdateRecurringScheduleTool
    rec_sched = RecurringSchedule(
        user_id=test_user.id,
        name="Study Window",
        start_time="20:00",
        end_time="21:30",
        days_of_week="Mon,Tue,Wed",
        is_hard_constraint=False,
    )
    db.add(rec_sched)
    db.commit()
    db.refresh(rec_sched)

    up_sched_tool = UpdateRecurringScheduleTool()
    res_up_sched = await up_sched_tool.execute(
        db, test_user, schedule_id=rec_sched.id, end_time="22:00", name="Deep Study Window"
    )
    assert res_up_sched.success is True
    db.refresh(rec_sched)
    assert rec_sched.name == "Deep Study Window"
    assert rec_sched.end_time == "22:00"


@pytest.mark.asyncio
async def test_user_ownership_isolation(db: Session, test_user: User):
    """Verify User A cannot access or mutate User B's entities via tools."""
    other_user = User(
        email="other_founder@iris.local",
        name="Other Founder",
        timezone="UTC",
    )
    db.add(other_user)
    db.commit()
    db.refresh(other_user)

    # Create task belonging to other_user
    from app.models.goal import Goal
    from app.models.task import Task
    from app.models.time_block import TimeBlock

    other_task = Task(user_id=other_user.id, title="Secret Task", area="STARTUP")
    other_goal = Goal(user_id=other_user.id, name="Secret Goal", area="STARTUP")
    other_block = TimeBlock(
        user_id=other_user.id,
        start_time=utcnow(),
        end_time=utcnow() + timedelta(hours=1),
        type="FOCUS",
    )
    db.add_all([other_task, other_goal, other_block])
    db.commit()
    db.refresh(other_task)
    db.refresh(other_goal)
    db.refresh(other_block)

    # test_user attempts to retrieve/modify other_user's task
    get_task = GetTaskTool()
    res = await get_task.execute(db, test_user, task_id=other_task.id)
    assert res.success is False

    update_task = UpdateTaskTool()
    res = await update_task.execute(db, test_user, task_id=other_task.id, title="Hacked Title")
    assert res.success is False
    db.refresh(other_task)
    assert other_task.title == "Secret Task"

    # test_user attempts to update other_user's goal
    update_goal = UpdateGoalTool()
    res = await update_goal.execute(db, test_user, goal_id=other_goal.id, name="Hacked Goal")
    assert res.success is False

    # test_user attempts to delete other_user's time block
    del_block = DeleteTimeBlockTool()
    res = await del_block.execute(db, test_user, block_id=other_block.id)
    assert res.success is False

