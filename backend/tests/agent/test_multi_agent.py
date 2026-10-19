"""Tests for IRIS Multi-Agent Architecture and Supervisor Orchestration."""

import pytest
from sqlalchemy.orm import Session

from app.agent.agent import IrisAgent
from app.agent.agents.bubba import BubbaAgent, get_bubba_agent
from app.agent.agents.operator import OperatorAgent, get_operator_agent
from app.agent.agents.planner import PlannerAgent, get_planner_agent
from app.agent.agents.scribe import ScribeAgent, get_scribe_agent
from app.agent.registry import default_registry
from app.agent.schemas import AgentResponseSchema
from app.agent.supervisor import IrisSupervisor, get_iris_supervisor
from app.ai.providers.mock import MockProvider
from app.intelligence.context import build_decision_context
from app.models.enums import TaskPriority, TaskStatus
from app.models.habit import Habit
from app.models.task import Task
from app.models.user import User


@pytest.fixture
def multi_user(db: Session) -> User:
    user = db.query(User).filter(User.email == "multi_agent_test@iris.local").first()
    if not user:
        user = User(
            email="multi_agent_test@iris.local",
            name="Orchestrator Test User",
            timezone="Asia/Kolkata",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def test_subagent_tool_scoping():
    """Verify each sub-agent has its isolated tools and correct identity."""
    operator = get_operator_agent("mock:mock-operator")
    planner = get_planner_agent("mock:mock-planner")
    scribe = get_scribe_agent("mock:mock-scribe")
    bubba = get_bubba_agent("mock:mock-bubba")

    assert operator.name == "Operator"
    assert "run_laptop_terminal_command" in [t.name for t in operator.registry.list_tools()]
    assert "start_autonomous_coding" in [t.name for t in operator.registry.list_tools()]
    assert "get_schedule" not in [t.name for t in operator.registry.list_tools()]

    assert planner.name == "Planner"
    assert "create_time_block" in [t.name for t in planner.registry.list_tools()]
    assert "create_task" in [t.name for t in planner.registry.list_tools()]
    assert "read_laptop_file" not in [t.name for t in planner.registry.list_tools()]

    assert scribe.name == "Scribe"
    assert "create_diary_entry" in [t.name for t in scribe.registry.list_tools()]
    assert "log_transaction" in [t.name for t in scribe.registry.list_tools()]
    assert "check_routine" in [t.name for t in scribe.registry.list_tools()]

    assert bubba.name == "BUBBA"
    assert "list_unread_emails" in [t.name for t in bubba.registry.list_tools()]
    assert "search_google_drive" in [t.name for t in bubba.registry.list_tools()]
    assert "run_laptop_terminal_command" not in [t.name for t in bubba.registry.list_tools()]


def test_supervisor_route_intent():
    """Verify intent router classifies requests to appropriate worker domains."""
    supervisor = get_iris_supervisor()

    # Operator routes
    assert "operator" in supervisor.route_intent("run command pytest in backend")
    assert "operator" in supervisor.route_intent("open terminal in Desktop")
    assert "operator" in supervisor.route_intent("read file main.py")
    assert "operator" in supervisor.route_intent("start autonomous coding for user auth")

    # Planner routes
    assert "planner" in supervisor.route_intent("plan my day with 2 deep work time blocks")
    assert "planner" in supervisor.route_intent("reschedule my afternoon calendar")
    assert "planner" in supervisor.route_intent("create goal for Q4 revenue")

    # Scribe routes
    assert "scribe" in supervisor.route_intent("save this note in my diary: AI continuity")
    assert "scribe" in supervisor.route_intent("record my bench press workout 80kg 3 sets")
    assert "scribe" in supervisor.route_intent("log expense 150 for lunch")

    # BUBBA routes
    assert "bubba" in supervisor.route_intent("check my unread emails from client")
    assert "bubba" in supervisor.route_intent("search google drive for startup pitch")
    assert "bubba" in supervisor.route_intent("draft email to Alex about project status")

    # General / chit-chat (Handled by Orchestrator directly)
    assert len(supervisor.route_intent("How does gravity work?")) == 0
    assert len(supervisor.route_intent("Tell me a creative story")) == 0


@pytest.mark.asyncio
async def test_fast_path_what_is_my_task(db: Session, multi_user: User):
    """Verify fast path answers 'what is my task' deterministically with 0 LLM calls."""
    # Ensure a task exists
    task = Task(
        user_id=multi_user.id,
        title="Deploy Orchestrator to Production",
        area="STARTUP",
        priority=TaskPriority.HIGH.value,
        status=TaskStatus.TODO.value,
        estimated_duration=45,
    )
    db.add(task)
    db.commit()

    agent = IrisAgent(default_registry)
    out, _ = await agent.run_turn(
        db=db,
        user=multi_user,
        user_message="What's my task?",
    )

    assert out.role == "ASSISTANT"
    assert out.source == "DETERMINISTIC"
    assert "Deploy Orchestrator to Production" in out.content
    assert out.recommended_action is not None
    assert out.recommended_action["title"] == "Deploy Orchestrator to Production"


@pytest.mark.asyncio
async def test_fast_path_task_done(db: Session, multi_user: User):
    """Verify fast path marks task done and gives next recommendation immediately."""
    task = (
        db.query(Task)
        .filter(Task.user_id == multi_user.id, Task.status == TaskStatus.TODO.value)
        .first()
    )
    if not task:
        task = Task(
            user_id=multi_user.id,
            title="Deploy Orchestrator to Production",
            area="STARTUP",
            priority=TaskPriority.HIGH.value,
            status=TaskStatus.TODO.value,
            estimated_duration=45,
        )
        db.add(task)
        db.commit()
    assert task is not None

    agent = IrisAgent(default_registry)
    out, _ = await agent.run_turn(
        db=db,
        user=multi_user,
        user_message="task done",
    )

    assert out.role == "ASSISTANT"
    assert out.source == "DETERMINISTIC"
    assert "complete" in out.content.lower()

    # Verify task status was updated in DB
    db.refresh(task)
    assert task.status == TaskStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_fast_path_gym_done(db: Session, multi_user: User):
    """Verify fast path records gym/workout completion immediately."""
    # Add gym routine
    habit = db.query(Habit).filter(Habit.user_id == multi_user.id, Habit.name == "Gym").first()
    if not habit:
        habit = Habit(
            user_id=multi_user.id,
            name="Gym",
            days_of_week="mon,tue,wed,thu,fri",
            active=True,
        )
        db.add(habit)
        db.commit()

    agent = IrisAgent(default_registry)
    out, _ = await agent.run_turn(
        db=db,
        user=multi_user,
        user_message="Gym done",
    )

    assert out.role == "ASSISTANT"
    assert out.source == "DETERMINISTIC"
    assert "gym" in out.content.lower() or "workout" in out.content.lower()


@pytest.mark.asyncio
async def test_fast_path_time_query(db: Session, multi_user: User):
    """Verify fast path responds with current local time."""
    agent = IrisAgent(default_registry)
    out, _ = await agent.run_turn(
        db=db,
        user=multi_user,
        user_message="What time is it?",
    )

    assert out.role == "ASSISTANT"
    assert out.source == "DETERMINISTIC"
    assert "Asia/Kolkata" in out.content or "It is currently" in out.content


@pytest.mark.asyncio
async def test_subagent_execution_report(db: Session, multi_user: User, monkeypatch):
    """Verify subagent executes via harness and returns structured SubAgentReport."""
    operator = get_operator_agent("mock:mock-operator")

    mock_resp = AgentResponseSchema(
        thought="Executed directory listing.",
        actions=[],
        message="Found 5 files in workspace: main.py, config.py, test.py",
        actions_summary=["Listed files"],
        evidence=["Files: 5 items"],
    )
    mock_provider = MockProvider(default_response_generator=lambda **kw: mock_resp)
    operator.provider = mock_provider
    operator.harness._max_steps = 2

    report = await operator.execute(
        db=db,
        user=multi_user,
        instruction="list files in workspace",
        context={"workspace": "C:\\kirtan\\IRIS"},
    )

    assert report.agent_name == "Operator"
    assert report.success is True
    assert "Found 5 files" in report.summary


@pytest.mark.asyncio
async def test_supervisor_route_intent_async():
    """Verify route_intent_async handles deterministic triggers and chitchat properly."""
    supervisor = get_iris_supervisor()

    # Fast deterministic route
    res = await supervisor.route_intent_async("lock laptop")
    assert "operator" in res

    res2 = await supervisor.route_intent_async("check my unread emails")
    assert "bubba" in res2

    # Fast chitchat short-circuit
    res_chitchat = await supervisor.route_intent_async("hi")
    assert res_chitchat == []

    res_thanks = await supervisor.route_intent_async("thank you")
    assert res_thanks == []


@pytest.mark.asyncio
async def test_supervisor_single_token_jev_mapping(monkeypatch):
    """Verify single-token Jev classification maps tokens A-E accurately."""
    from unittest.mock import AsyncMock, MagicMock
    import httpx

    supervisor = get_iris_supervisor()

    test_cases = [
        ("A", ["operator"]),
        ("B", ["planner"]),
        ("C", ["scribe"]),
        ("D", ["bubba"]),
        ("E", []),
        ("[A]", ["operator"]),
        ("B.", ["planner"]),
    ]

    for letter, expected in test_cases:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": letter}}]}

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_resp

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: mock_client)
        monkeypatch.setattr("app.core.config.settings.nvidia_api_key", "test-nvidia-key")
        monkeypatch.setattr("app.core.config.settings.groq_api_key", "test-groq-key")

        res = await supervisor.route_intent_async("ambiguous query with no obvious keywords here")
        assert res == expected


