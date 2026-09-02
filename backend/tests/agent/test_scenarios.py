"""Phase 4 Scenario Test Suite: 7 realistic conversational IRIS interactions."""

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.agent.agent import IrisAgent
from app.agent.registry import default_registry
from app.agent.schemas import AgentResponseSchema, ToolCall
from app.ai.providers.mock import MockProvider
from app.models.enums import LifeArea, TaskPriority, TaskStatus
from app.models.task import Task
from app.models.time_block import TimeBlock
from app.models.user import User
from app.utils.datetime import utcnow


@pytest.fixture
def scenario_user(db: Session) -> User:
    user = db.query(User).filter(User.email == "scenario_founder@iris.local").first()
    if not user:
        user = User(
            email="scenario_founder@iris.local",
            name="Kirtan Scenario Founder",
            timezone="Asia/Kolkata",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_scenario_1_mixed_task_completion(db: Session, scenario_user: User, monkeypatch):
    """Scenario 1: 'I finished my internship task. What should I do now?'"""
    task_internship = Task(
        user_id=scenario_user.id,
        title="Review backend PR for internship",
        area=LifeArea.INTERNSHIP.value,
        priority=TaskPriority.HIGH.value,
        status=TaskStatus.TODO.value,
        estimated_duration=45,
    )
    task_startup = Task(
        user_id=scenario_user.id,
        title="Founder customer outreach batch",
        area=LifeArea.STARTUP.value,
        priority=TaskPriority.CRITICAL.value,
        status=TaskStatus.TODO.value,
        estimated_duration=60,
    )
    db.add_all([task_internship, task_startup])
    db.commit()
    db.refresh(task_internship)
    db.refresh(task_startup)

    mock_resp = AgentResponseSchema(
        thought="User completed their task; recommend startup outreach next.",
        actions=[
            ToolCall(
                tool_name="complete_task",
                parameters={"task_id": task_internship.id, "actual_duration": 45},
            )
        ],
        message=(
            "Marked your internship PR task as complete. "
            "Your top focus now is 'Founder customer outreach batch'."
        ),
        actions_summary=[f"Completed #{task_internship.id}"],
        evidence=["Internship work completed", "Customer validation is bottleneck"],
        recommended_action={
            "task_id": task_startup.id,
            "title": task_startup.title,
            "duration_minutes": 60,
        },
    )
    mock_provider = MockProvider(default_response_generator=lambda **kw: mock_resp)
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: mock_provider)

    agent = IrisAgent(default_registry)
    out, _ = await agent.run_turn(
        db, scenario_user, "I finished my internship task. What should I do now?"
    )

    assert out.role == "ASSISTANT"
    assert len(out.actions_taken) == 1
    assert out.actions_taken[0]["tool_name"] == "complete_task"
    assert out.actions_taken[0]["success"] is True

    db.refresh(task_internship)
    assert task_internship.status == TaskStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_scenario_2_add_compiler_design_deadline(
    db: Session, scenario_user: User, monkeypatch
):
    """Scenario 2: 'Add Compiler Design assignment due tomorrow.'"""
    tomorrow = (utcnow() + timedelta(days=1)).replace(hour=18, minute=0, second=0)
    mock_resp = AgentResponseSchema(
        thought="User requests adding an urgent College task with deadline.",
        actions=[
            ToolCall(
                tool_name="create_task",
                parameters={
                    "title": "Compiler Design Assignment",
                    "area": "COLLEGE",
                    "priority": "HIGH",
                    "deadline": tomorrow.isoformat(),
                    "estimated_duration": 90,
                },
            )
        ],
        message="Added 'Compiler Design Assignment' (due tomorrow at 6:00 PM, 90m estimate).",
        actions_summary=["Added 'Compiler Design Assignment'"],
        evidence=["Deadline registered: tomorrow 6:00 PM"],
    )
    mock_provider = MockProvider(default_response_generator=lambda **kw: mock_resp)
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: mock_provider)

    agent = IrisAgent(default_registry)
    out, _ = await agent.run_turn(db, scenario_user, "Add Compiler Design assignment due tomorrow.")

    assert out.actions_taken[0]["success"] is True
    created = (
        db.query(Task)
        .filter(Task.title == "Compiler Design Assignment", Task.user_id == scenario_user.id)
        .first()
    )
    assert created is not None
    assert created.area == "COLLEGE"


@pytest.mark.asyncio
async def test_scenario_3_time_window_query(db: Session, scenario_user: User, monkeypatch):
    """Scenario 3: 'I have 45 minutes. What should I work on?'"""
    mock_resp = AgentResponseSchema(
        thought="User asks for recommendation fitting 45m window.",
        actions=[],
        message="In 45 minutes, tackle 'Write user documentation for v1' — it fits your budget.",
        actions_summary=[],
        evidence=["Available window: 45m", "Estimated task duration: 40m"],
        recommended_action={
            "task_id": 99,
            "title": "Write user documentation for v1",
            "duration_minutes": 40,
        },
    )
    mock_provider = MockProvider(default_response_generator=lambda **kw: mock_resp)
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: mock_provider)

    agent = IrisAgent(default_registry)
    out, _ = await agent.run_turn(db, scenario_user, "I have 45 minutes. What should I work on?")

    assert "45 minutes" in out.content or "documentation" in out.content
    assert out.recommended_action is not None


@pytest.mark.asyncio
async def test_scenario_4_move_schedule_block(db: Session, scenario_user: User, monkeypatch):
    """Scenario 4: 'Move my NEXUS outreach session to tomorrow evening.'"""
    now = utcnow()
    old_block = TimeBlock(
        user_id=scenario_user.id,
        start_time=now + timedelta(hours=2),
        end_time=now + timedelta(hours=3, minutes=30),
        notes="NEXUS outreach session",
        type="FOCUS",
        status="SCHEDULED",
    )
    db.add(old_block)
    db.commit()
    db.refresh(old_block)

    tomorrow_eve_start = (now + timedelta(days=1)).replace(hour=18, minute=0)
    tomorrow_eve_end = tomorrow_eve_start + timedelta(minutes=90)

    mock_resp = AgentResponseSchema(
        thought="User requests moving an existing focus session to tomorrow evening.",
        actions=[
            ToolCall(
                tool_name="update_time_block",
                parameters={
                    "block_id": old_block.id,
                    "start_time": tomorrow_eve_start.isoformat(),
                    "end_time": tomorrow_eve_end.isoformat(),
                },
            )
        ],
        message="Moved your NEXUS outreach session to tomorrow evening from 18:00 to 19:30.",
        actions_summary=["Updated time block #1"],
        evidence=["Scheduled tomorrow 18:00 - 19:30"],
    )
    mock_provider = MockProvider(default_response_generator=lambda **kw: mock_resp)
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: mock_provider)

    agent = IrisAgent(default_registry)
    out, _ = await agent.run_turn(
        db, scenario_user, "Move my NEXUS outreach session to tomorrow evening."
    )

    assert out.actions_taken[0]["success"] is True
    db.refresh(old_block)
    assert old_block.start_time.hour == 18


@pytest.mark.asyncio
async def test_scenario_5_falling_behind_query(db: Session, scenario_user: User, monkeypatch):
    """Scenario 5: 'What's currently falling behind?'"""
    mock_resp = AgentResponseSchema(
        thought="User asking what is falling behind.",
        actions=[],
        message="Your weekly outreach is behind (4/20), and ML lab is due in 18 hours.",
        actions_summary=[],
        evidence=["Outreach: 4/20 target", "ML Lab: due in 18h"],
    )
    mock_provider = MockProvider(default_response_generator=lambda **kw: mock_resp)
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: mock_provider)

    agent = IrisAgent(default_registry)
    out, _ = await agent.run_turn(db, scenario_user, "What's currently falling behind?")

    assert "behind" in out.content.lower() or "outreach" in out.content.lower()


@pytest.mark.asyncio
async def test_scenario_6_honest_limitation_gmail(db: Session, scenario_user: User, monkeypatch):
    """Scenario 6: 'What important emails do I need to answer?' (Honest limitation test)"""
    mock_resp = AgentResponseSchema(
        thought="User asking about emails; Gmail is not connected.",
        actions=[],
        message="I cannot read your emails because Gmail is not connected.",
        actions_summary=[],
        evidence=["Gmail integration: Disconnected"],
        missing_information="Gmail integration is not connected.",
    )
    mock_provider = MockProvider(default_response_generator=lambda **kw: mock_resp)
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: mock_provider)

    agent = IrisAgent(default_registry)
    out, _ = await agent.run_turn(db, scenario_user, "What important emails do I need to answer?")

    assert (
        "cannot" in out.content.lower()
        or "not connected" in out.content.lower()
        or "gmail" in out.content.lower()
    )


@pytest.mark.asyncio
async def test_scenario_7_finished_everything_no_fake_work(
    db: Session, scenario_user: User, monkeypatch
):
    """Scenario 7: 'I finished everything I needed to do today.' (No invented work)"""
    mock_resp = AgentResponseSchema(
        thought="User finished work; suggest rest instead of fake tasks.",
        actions=[],
        message="Great job clearing commitments today. Take time to recharge.",
        actions_summary=[],
        evidence=["0 urgent obligations remaining", "All today's tasks completed"],
    )
    mock_provider = MockProvider(default_response_generator=lambda **kw: mock_resp)
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: mock_provider)

    agent = IrisAgent(default_registry)
    out, _ = await agent.run_turn(db, scenario_user, "I finished everything I needed to do today.")

    assert (
        "great job" in out.content.lower()
        or "recharge" in out.content.lower()
        or "review" in out.content.lower()
    )
