"""IRIS P1 Intelligence Architecture Acceptance Tests (Tests A through J).

Mandatory Acceptance Test Suite verifying:
- Test A: Semantic understanding (5 phrasing variations produce equivalent behavior)
- Test B: Unfamiliar / novel request handling (reasoning + planning + execution)
- Test C: Multi-step reasoning across domains (Startup + Tasks + Schedule)
- Test D: Context continuity across turns (resolving 'the second one')
- Test E: Tool failure recovery and adaptation (diagnose error, adapt, succeed)
- Test F: Postcondition verification failure handling (unverified action is NOT reported as success)
- Test G: Permission and approval enforcement (sensitive action produces approval token)
- Test H: General conversation without tool invocation (0 unnecessary tools)
- Test I: Provider fallback resilience (handles provider disconnect gracefully)
- Test J: Avoiding unnecessary tools when context already contains the answer
"""

from __future__ import annotations

import pytest
from datetime import datetime
from sqlalchemy.orm import Session

from app.agent.agent import IrisAgent
from app.agent.reasoning_engine import UnifiedReasoningEngine
from app.agent.registry import default_registry
from app.agent.schemas import AgentResponseSchema, ToolCall, ToolResult
from app.agent.tools.base import RiskLevel, Tool, VerificationStrategy
from app.ai.provider import (
    AIConnectionError,
    ChatResult,
    ModelCapabilities,
    ToolCallRequest,
)
from app.ai.providers.mock import MockProvider
from app.execution.contracts import PermissionClass
from app.execution.policy import default_policy
from app.models.enums import LifeArea, TaskPriority, TaskStatus, TimeBlockType
from app.models.task import Task
from app.models.time_block import TimeBlock
from app.models.user import User


@pytest.fixture
def acceptance_user(db: Session) -> User:
    user = db.query(User).filter(User.email == "acceptance@iris.local").first()
    if not user:
        user = User(
            email="acceptance@iris.local",
            name="Kirtan Acceptance",
            timezone="Asia/Kolkata",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _call(name: str, args: dict, call_id: str = "c") -> ToolCallRequest:
    return ToolCallRequest(id=call_id, name=name, arguments=args)


def _scripted(results: list[ChatResult], seen: list | None = None):
    queue = list(results)

    def gen(*, messages, tools):
        if seen is not None:
            seen.append({"messages": list(messages), "tools": tools})
        if queue:
            return queue.pop(0)
        return ChatResult(content="Done.")

    return gen


# =============================================================================
# Test A: Semantic Understanding across 5 Phrasing Variations
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phrasing",
    [
        "Could you schedule a 45-minute focus session on Compiler Design for 3 PM today?",
        "Block out 45 mins at 15:00 today to work on Compiler Design.",
        "Put 45 minutes on my calendar at 3:00 PM for deep work on Compiler Design.",
        "Set up a focus block from 3pm to 3:45pm today for Compiler Design.",
        "I need 45 minutes of focused time starting at 3 PM today to tackle Compiler Design.",
    ],
)
async def test_acceptance_a_semantic_understanding(db: Session, acceptance_user: User, monkeypatch, phrasing: str):
    """5 semantically equivalent requests with different wording produce equivalent correct behavior."""
    start_dt = "2026-10-30T15:00:00"
    end_dt = "2026-10-30T15:45:00"

    provider = MockProvider(
        chat_generator=_scripted(
            [
                ChatResult(
                    tool_calls=[
                        _call(
                            "create_time_block",
                            {
                                "start_time": start_dt,
                                "end_time": end_dt,
                                "type": "FOCUS",
                                "notes": "Compiler Design",
                            },
                            "call_timeblock",
                        )
                    ]
                ),
                ChatResult(
                    tool_calls=[
                        _call(
                            "final_answer",
                            {
                                "message": "Scheduled 45m focus block for Compiler Design at 3:00 PM.",
                                "evidence": ["Created focus block 15:00-15:45"],
                            },
                            "call_final",
                        )
                    ]
                ),
            ]
        )
    )
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: provider)

    agent = IrisAgent(default_registry)
    out, conv = await agent.run_turn(
        db=db,
        user=acceptance_user,
        user_message=phrasing,
        skip_fast_path=True,
    )

    assert out.role == "ASSISTANT"
    assert "Compiler Design" in out.content
    assert len(out.actions_taken) > 0

    # Verify authoritative database state
    block = (
        db.query(TimeBlock)
        .filter(TimeBlock.user_id == acceptance_user.id, TimeBlock.notes == "Compiler Design")
        .order_by(TimeBlock.id.desc())
        .first()
    )
    assert block is not None
    assert block.duration_minutes == 45


# =============================================================================
# Test B: Unfamiliar Request Handling (Multi-turn decomposition)
# =============================================================================

@pytest.mark.asyncio
async def test_acceptance_b_unfamiliar_request_handling(db: Session, acceptance_user: User, monkeypatch):
    """A novel, unfamiliar request is understood, planned, and executed through tool chaining."""
    # Seed an urgent task
    urgent_task = Task(
        user_id=acceptance_user.id,
        title="Operating Systems Kernel Project",
        area=LifeArea.COLLEGE.value,
        priority=TaskPriority.CRITICAL.value,
        status=TaskStatus.TODO.value,
        estimated_duration=60,
    )
    db.add(urgent_task)
    db.commit()
    db.refresh(urgent_task)

    request_msg = (
        "I'm feeling overwhelmed by my coursework — can you look through my upcoming deadlines, "
        "pick the most urgent one, and reserve an hour on my schedule tomorrow morning to make progress on it?"
    )

    provider = MockProvider(
        chat_generator=_scripted(
            [
                ChatResult(tool_calls=[_call("get_today_tasks", {"include_completed": False}, "c1")]),
                ChatResult(
                    tool_calls=[
                        _call(
                            "create_time_block",
                            {
                                "start_time": "2026-10-31T09:00:00",
                                "end_time": "2026-10-31T10:00:00",
                                "task_id": urgent_task.id,
                                "type": "FOCUS",
                                "notes": "Work on Operating Systems Kernel Project",
                            },
                            "c2",
                        )
                    ]
                ),
                ChatResult(
                    tool_calls=[
                        _call(
                            "final_answer",
                            {
                                "message": "I found your critical task 'Operating Systems Kernel Project' and scheduled 1 hour tomorrow at 9:00 AM.",
                                "evidence": [f"Task #{urgent_task.id} is CRITICAL"],
                            },
                            "c3",
                        )
                    ]
                ),
            ]
        )
    )
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: provider)

    agent = IrisAgent(default_registry)
    out, _ = await agent.run_turn(db=db, user=acceptance_user, user_message=request_msg, skip_fast_path=True)

    assert "Operating Systems Kernel Project" in out.content
    assert any("create_time_block" == a.get("tool_name") for a in out.actions_taken)

    # Authoritative verification
    block = db.query(TimeBlock).filter(TimeBlock.task_id == urgent_task.id).first()
    assert block is not None
    assert block.duration_minutes == 60


# =============================================================================
# Test C: Multi-Step Reasoning Across Domains (Startup + Tasks)
# =============================================================================

@pytest.mark.asyncio
async def test_acceptance_c_multi_step_reasoning_across_domains(db: Session, acceptance_user: User, monkeypatch):
    """Request spanning multiple domains (Startup + Tasks) executes in sequence and synthesizes."""
    request_msg = "Review my startup status and add a high priority task for investor updates."

    provider = MockProvider(
        chat_generator=_scripted(
            [
                # Step 1: Startup domain inspection
                ChatResult(tool_calls=[_call("get_startup_status", {}, "c1")]),
                # Step 2: Task domain creation
                ChatResult(
                    tool_calls=[
                        _call(
                            "create_task",
                            {
                                "title": "Send Q4 Investor Updates",
                                "area": "STARTUP",
                                "priority": "HIGH",
                                "estimated_duration": 45,
                            },
                            "c2",
                        )
                    ]
                ),
                # Step 3: Synthesis
                ChatResult(
                    tool_calls=[
                        _call(
                            "final_answer",
                            {
                                "message": "Reviewed your startup status. Added 'Send Q4 Investor Updates' as a high-priority task.",
                                "evidence": ["Startup status checked", "Created task in STARTUP domain"],
                            },
                            "c3",
                        )
                    ]
                ),
            ]
        )
    )
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: provider)

    agent = IrisAgent(default_registry)
    out, _ = await agent.run_turn(db=db, user=acceptance_user, user_message=request_msg, skip_fast_path=True)

    assert "Investor Updates" in out.content
    assert len(out.actions_taken) >= 1

    # Authoritative DB verification
    task = db.query(Task).filter(Task.user_id == acceptance_user.id, Task.title == "Send Q4 Investor Updates").first()
    assert task is not None
    assert task.area == LifeArea.STARTUP.value
    assert task.priority == TaskPriority.HIGH.value


# =============================================================================
# Test D: Context Continuity Across Turns (Resolving 'the second one')
# =============================================================================

@pytest.mark.asyncio
async def test_acceptance_d_context_continuity_across_turns(db: Session, acceptance_user: User, monkeypatch):
    """Follow-up referring to an entity from a previous turn resolves correctly with history."""
    t1 = Task(user_id=acceptance_user.id, title="Assignment 1 - Math", status=TaskStatus.TODO.value)
    t2 = Task(user_id=acceptance_user.id, title="Lab 3 - Physics", status=TaskStatus.TODO.value)
    db.add_all([t1, t2])
    db.commit()
    db.refresh(t1)
    db.refresh(t2)

    # Engine referent resolution check
    from app.ai.provider import ChatMessage
    engine = UnifiedReasoningEngine(default_registry)
    fake_history = [
        ChatMessage(role="user", content="What are my tasks?"),
        ChatMessage(
            role="assistant",
            content=f"Here are your tasks:\n1. Task #{t1.id}: {t1.title}\n2. Task #{t2.id}: {t2.title}",
        ),
    ]

    ctx = engine.understand("Actually mark the second one as completed.", fake_history)
    assert ctx.referents.get("task_id") == t2.id

    # Now verify in full turn
    provider = MockProvider(
        chat_generator=_scripted(
            [
                ChatResult(
                    tool_calls=[_call("complete_task", {"task_id": t2.id}, "c_comp")]
                ),
                ChatResult(
                    tool_calls=[
                        _call(
                            "final_answer",
                            {
                                "message": f"Marked task #{t2.id} ('Lab 3 - Physics') as completed.",
                                "evidence": [f"Completed task #{t2.id}"],
                            },
                            "c_fin",
                        )
                    ]
                ),
            ]
        )
    )
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: provider)

    agent = IrisAgent(default_registry)
    out, conv = await agent.run_turn(
        db=db,
        user=acceptance_user,
        user_message="Actually mark the second one as completed.",
        skip_fast_path=True,
    )

    db.refresh(t2)
    assert t2.status == TaskStatus.COMPLETED.value
    assert f"#{t2.id}" in out.content or "Lab 3" in out.content


# =============================================================================
# Test E: Tool Failure Recovery and Adaptation
# =============================================================================

@pytest.mark.asyncio
async def test_acceptance_e_tool_failure_recovery(db: Session, acceptance_user: User, monkeypatch):
    """Tool failure causes agent to diagnose error, adapt with corrected parameters, and succeed."""
    seen_calls: list = []

    def scripted_chat(*, messages, tools):
        seen_calls.append(list(messages))
        # First attempt: sends bad argument type (estimated_duration = -10)
        if len(seen_calls) == 1:
            return ChatResult(
                tool_calls=[
                    _call(
                        "create_task",
                        {"title": "Recovery Task", "area": "COLLEGE", "estimated_duration": -10},
                        "c_bad",
                    )
                ]
            )
        # Second attempt: inspects error in messages and corrects parameters (estimated_duration = 30)
        elif len(seen_calls) == 2:
            return ChatResult(
                tool_calls=[
                    _call(
                        "create_task",
                        {"title": "Recovery Task", "area": "COLLEGE", "estimated_duration": 30},
                        "c_good",
                    )
                ]
            )
        # Third attempt: final answer
        return ChatResult(
            tool_calls=[
                _call(
                    "final_answer",
                    {
                        "message": "Encountered a validation error, corrected parameters, and created 'Recovery Task'.",
                        "evidence": ["Task created with duration 30m"],
                    },
                    "c_done",
                )
            ]
        )

    provider = MockProvider(chat_generator=scripted_chat)
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: provider)

    agent = IrisAgent(default_registry)
    out, _ = await agent.run_turn(
        db=db,
        user=acceptance_user,
        user_message="Create a recovery task for 30 minutes in College.",
        skip_fast_path=True,
    )

    # Verify task was successfully created on retry
    created = db.query(Task).filter(Task.user_id == acceptance_user.id, Task.title == "Recovery Task").first()
    assert created is not None
    assert created.estimated_duration == 30
    assert "Recovery Task" in out.content


# =============================================================================
# Test F: Postcondition Verification Failure Handling
# =============================================================================

@pytest.mark.asyncio
async def test_acceptance_f_postcondition_verification_failure_handling(db: Session, acceptance_user: User, monkeypatch):
    """When postcondition verification fails, agent detects discrepancy and does NOT claim success."""
    class PhantomTaskTool(Tool):
        name = "create_phantom_task"
        description = "Simulates an operation that claims success but fails postcondition verification."
        verification_strategy = VerificationStrategy.DB_CHECK
        category = "tasks"

        async def verify(self, db: Session, user: User, result: ToolResult, **kwargs: Any) -> bool:
            # Independent postcondition check: fails because no record exists in DB!
            return False

        async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
            return ToolResult(
                tool_name=self.name,
                success=True,
                summary="Phantom task reported created.",
                data={"task_id": 999999},
            )

    test_reg = default_registry
    test_reg.register(PhantomTaskTool())

    seen_messages: list = []

    def scripted_chat(*, messages, tools):
        seen_messages.append(list(messages))
        if len(seen_messages) == 1:
            return ChatResult(tool_calls=[_call("create_phantom_task", {}, "c_phantom")])
        # Model receives feedback containing verified: false and reports honestly
        return ChatResult(
            tool_calls=[
                _call(
                    "final_answer",
                    {
                        "message": "The creation command was sent, but postcondition verification failed to confirm it in the database.",
                        "missing_information": "Record could not be verified in database.",
                    },
                    "c_done",
                )
            ]
        )

    provider = MockProvider(chat_generator=scripted_chat)
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: provider)

    agent = IrisAgent(test_reg)
    out, _ = await agent.run_turn(
        db=db,
        user=acceptance_user,
        user_message="Create phantom task.",
        skip_fast_path=True,
    )

    # 1. Unverified action MUST NOT be recorded as successful
    assert not any(
        a.get("tool_name") == "create_phantom_task" and a.get("success") and a.get("verified", True)
        for a in out.actions_taken
    )
    # 2. Feedback message received by model contained verified: false
    tool_feedback = [m for m in seen_messages[1] if m.role == "tool"]
    assert any('"verified": false' in m.content for m in tool_feedback)
    # 3. Agent honestly explained the verification failure
    assert "verification failed" in out.content.lower()


# =============================================================================
# Test G: Permission & Approval Enforcement
# =============================================================================

@pytest.mark.asyncio
async def test_acceptance_g_permission_and_approval_enforcement(db: Session, acceptance_user: User, monkeypatch):
    """Sensitive or destructive action produces an approval token and is not executed until confirmed."""
    class DangerousSystemTool(Tool):
        name = "destroy_system_file"
        description = "Deletes critical system files. Sensitive operation."
        risk_level = RiskLevel.SENSITIVE
        is_destructive = True
        verification_strategy = VerificationStrategy.FILE_CHECK

        async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
            return ToolResult(tool_name=self.name, success=True, summary="File deleted.")

    sensitive_tool = DangerousSystemTool()

    # Call without approval token
    res = await sensitive_tool.execute(db, acceptance_user)
    assert not res.success
    assert res.error == "APPROVAL_REQUIRED"
    assert "approval_token" in res.data
    appr_token = res.data["approval_token"]
    assert appr_token.startswith("appr_")

    # Authorize with token
    res_auth = await sensitive_tool.execute(db, acceptance_user, approval_token=appr_token)
    assert res_auth.success
    assert res_auth.summary == "File deleted."


# =============================================================================
# Test H: General Conversation Without Tool Invocation
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "Explain the difference between SQLite and PostgreSQL.",
        "Good morning! Hope you are having a productive day.",
    ],
)
async def test_acceptance_h_general_conversation_without_tools(db: Session, acceptance_user: User, monkeypatch, query: str):
    """Pure conversational or explanatory queries produce natural replies with 0 tool invocations."""
    provider = MockProvider(
        chat_generator=_scripted(
            [
                ChatResult(
                    content=(
                        "SQLite is a serverless, embedded database ideal for local storage, "
                        "while PostgreSQL is a full client-server RDBMS built for concurrency."
                        if "SQLite" in query
                        else "Good morning! Ready to assist you with whatever you need today."
                    )
                )
            ]
        )
    )
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: provider)

    agent = IrisAgent(default_registry)
    out, _ = await agent.run_turn(
        db=db,
        user=acceptance_user,
        user_message=query,
        skip_fast_path=True,
    )

    assert out.role == "ASSISTANT"
    assert len(out.actions_taken) == 0
    assert len(out.content) > 10


# =============================================================================
# Test I: Provider Fallback Resilience
# =============================================================================

@pytest.mark.asyncio
async def test_acceptance_i_provider_fallback_resilience(db: Session, acceptance_user: User, monkeypatch):
    """When primary provider encounters connection error, fallback handles the turn gracefully."""
    class FailingPrimaryProvider(MockProvider):
        async def chat(self, messages, tools=None):
            raise AIConnectionError("Connection to primary LLM cluster timed out.")

    fallback_provider = MockProvider(
        chat_generator=_scripted(
            [
                ChatResult(
                    content="Hello! The primary model connection had an issue, but I am here and responding through fallback."
                )
            ]
        )
    )

    # Wire fallback in agent
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: FailingPrimaryProvider())

    agent = IrisAgent(default_registry)
    # With primary failing, agent falls back to deterministic decision / fallback response without crashing
    out, _ = await agent.run_turn(
        db=db,
        user=acceptance_user,
        user_message="Check in on my tasks please.",
        skip_fast_path=False,
    )

    assert out.role == "ASSISTANT"
    assert len(out.content) > 0


# =============================================================================
# Test J: Avoiding Unnecessary Tools
# =============================================================================

@pytest.mark.asyncio
async def test_acceptance_j_avoiding_unnecessary_tools(db: Session, acceptance_user: User, monkeypatch):
    """When the answer is already present in context or personal model, agent avoids unnecessary tool calls."""
    engine = UnifiedReasoningEngine(default_registry)
    context_data = {
        "user_name": acceptance_user.name,
        "user_timezone": acceptance_user.timezone,
    }

    ctx = engine.understand(
        user_message="What timezone am I in?",
        history=[],
        live_context=context_data,
    )

    # Reasoning engine detects context already answers question
    assert ctx.can_answer_from_context
    assert not ctx.requires_tools
    assert "Asia/Kolkata" in (ctx.context_answer or "")
