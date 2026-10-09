"""Agent harness: multi-step tool loops, self-correction, safety rails, degradation."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.agent.agent import IrisAgent
from app.agent.registry import default_registry
from app.agent.schemas import AgentResponseSchema, ToolCall
from app.ai.provider import AISchemaValidationError, ChatResult, ToolCallRequest
from app.ai.providers.mock import MockProvider
from app.models.task import Task
from app.models.user import User


@pytest.fixture
def harness_user(db: Session) -> User:
    user = db.query(User).filter(User.email == "harness@iris.local").first()
    if not user:
        user = User(email="harness@iris.local", name="Harness User", timezone="Asia/Kolkata")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _scripted(results: list[ChatResult], seen: list | None = None):
    queue = list(results)

    def gen(*, messages, tools):
        if seen is not None:
            seen.append({"messages": list(messages), "tools": tools})
        return queue.pop(0)

    return gen


def _call(name: str, args: dict, call_id: str = "c") -> ToolCallRequest:
    return ToolCallRequest(id=call_id, name=name, arguments=args)


def _use(monkeypatch, provider):
    monkeypatch.setattr("app.agent.agent.get_ai_provider", lambda: provider)


@pytest.mark.asyncio
async def test_native_loop_reads_then_acts_then_answers(db, harness_user, monkeypatch):
    seen: list = []
    provider = MockProvider(
        chat_generator=_scripted(
            [
                ChatResult(tool_calls=[_call("get_tasks", {"limit": 5}, "c1")]),
                ChatResult(
                    tool_calls=[
                        _call("create_task", {"title": "Harness Lab", "area": "COLLEGE"}, "c2")
                    ]
                ),
                ChatResult(
                    tool_calls=[
                        _call(
                            "final_answer",
                            {
                                "message": "Added 'Harness Lab' to College.",
                                "evidence": ["No duplicate task existed"],
                            },
                            "c3",
                        )
                    ]
                ),
            ],
            seen,
        )
    )
    _use(monkeypatch, provider)

    out, _ = await IrisAgent(default_registry).run_turn(db, harness_user, "Add Harness Lab")

    assert out.source == "AI"
    assert out.content == "Added 'Harness Lab' to College."
    assert out.evidence == ["No duplicate task existed"]
    assert [a["tool_name"] for a in out.actions_taken] == ["get_tasks", "create_task"]
    # The model saw the get_tasks result before deciding to create.
    second_call_roles = [m.role for m in seen[1]["messages"]]
    assert second_call_roles[-2:] == ["assistant", "tool"]
    assert db.query(Task).filter(Task.title == "Harness Lab").count() == 1


@pytest.mark.asyncio
async def test_native_loop_feeds_errors_back_for_self_correction(db, harness_user, monkeypatch):
    seen: list = []
    provider = MockProvider(
        chat_generator=_scripted(
            [
                ChatResult(tool_calls=[_call("create_task", {"area": "COLLEGE"}, "bad")]),
                ChatResult(
                    tool_calls=[_call("create_task", {"title": "Fixed", "area": "COLLEGE"}, "ok")]
                ),
                ChatResult(content="Created 'Fixed'."),
            ],
            seen,
        )
    )
    _use(monkeypatch, provider)

    out, _ = await IrisAgent(default_registry).run_turn(db, harness_user, "add a task")

    tool_feedback = seen[1]["messages"][-1]
    assert tool_feedback.role == "tool"
    assert "Invalid parameters" in tool_feedback.content
    assert [a["success"] for a in out.actions_taken] == [False, True]
    assert out.content == "Created 'Fixed'."


@pytest.mark.asyncio
async def test_identical_state_change_never_runs_twice(db, harness_user, monkeypatch):
    args = {"title": "Only Once", "area": "PERSONAL"}
    provider = MockProvider(
        chat_generator=_scripted(
            [
                ChatResult(tool_calls=[_call("create_task", args, "a")]),
                ChatResult(tool_calls=[_call("create_task", args, "b")]),
                ChatResult(content="Done."),
            ]
        )
    )
    _use(monkeypatch, provider)

    out, _ = await IrisAgent(default_registry).run_turn(db, harness_user, "add Only Once")

    assert len(out.actions_taken) == 1
    assert db.query(Task).filter(Task.title == "Only Once").count() == 1


@pytest.mark.asyncio
async def test_step_limit_forces_a_final_answer(db, harness_user, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ai_agent_max_steps", 2)
    monkeypatch.setattr("app.core.config.settings.ai_agent_max_steps_hard", 2)
    seen: list = []
    provider = MockProvider(
        chat_generator=_scripted(
            [
                ChatResult(tool_calls=[_call("get_tasks", {}, "c1")]),
                ChatResult(content="Here is what I found."),
            ],
            seen,
        )
    )
    _use(monkeypatch, provider)

    out, _ = await IrisAgent(default_registry).run_turn(db, harness_user, "look around")

    assert seen[1]["tools"] is None  # last step offers no tools
    assert out.content == "Here is what I found."


@pytest.mark.asyncio
async def test_native_failure_degrades_to_structured_json(db, harness_user, monkeypatch):
    def broken_chat(**_):
        raise AISchemaValidationError("garbled tool call")

    provider = MockProvider(
        chat_generator=broken_chat,
        default_response_generator=lambda **_: AgentResponseSchema(message="Structured reply."),
    )
    _use(monkeypatch, provider)

    out, _ = await IrisAgent(default_registry).run_turn(db, harness_user, "hello")

    assert out.source == "AI"
    assert out.content == "Structured reply."


@pytest.mark.asyncio
async def test_structured_loop_continues_after_read_tools(db, harness_user, monkeypatch):
    prompts: list[str] = []
    responses = [
        AgentResponseSchema(
            actions=[ToolCall(tool_name="get_tasks", parameters={"limit": 3})],
            continue_after_actions=True,
            message="Checking your tasks...",
        ),
        AgentResponseSchema(message="You have no urgent tasks."),
    ]

    def gen(*, system, prompt, schema):
        prompts.append(prompt)
        return responses.pop(0)

    _use(monkeypatch, MockProvider(default_response_generator=gen))

    out, _ = await IrisAgent(default_registry).run_turn(db, harness_user, "what's urgent?")

    assert len(prompts) == 2
    assert "Tool results (step 1)" in prompts[1]
    assert out.content == "You have no urgent tasks."
    assert [a["tool_name"] for a in out.actions_taken] == ["get_tasks"]


@pytest.mark.asyncio
async def test_failure_after_actions_reports_what_was_done(db, harness_user, monkeypatch):
    calls = {"n": 0}

    def flaky(**_):
        calls["n"] += 1
        if calls["n"] == 1:
            return ChatResult(
                tool_calls=[_call("create_task", {"title": "Salvaged", "area": "STARTUP"})]
            )
        raise AISchemaValidationError("model went off the rails")

    _use(monkeypatch, MockProvider(chat_generator=flaky))

    out, _ = await IrisAgent(default_registry).run_turn(db, harness_user, "add Salvaged")

    assert out.source == "AI"
    assert out.content.startswith("Done:")
    assert db.query(Task).filter(Task.title == "Salvaged").count() == 1


# --- Bulk actions & progress-based step budget --------------------------------------


@pytest.mark.asyncio
async def test_bulk_delete_removes_many_tasks_in_one_call(db, harness_user):
    ids = [
        Task(user_id=harness_user.id, title=f"Bulk {i}", area="STARTUP", priority="LOW", status="TODO")
        for i in range(5)
    ]
    db.add_all(ids)
    db.commit()
    task_ids = [t.id for t in ids]

    res = await default_registry.execute(
        "delete_tasks", db, harness_user, {"task_ids": [*task_ids, 999_999]}
    )

    assert res.success
    assert [d["task_id"] for d in res.data["done"]] == task_ids
    assert [f["task_id"] for f in res.data["failed"]] == [999_999]
    assert db.query(Task).filter(Task.title.like("Bulk %")).count() == 0
    assert res.summary.startswith("Deleted 5 tasks")


@pytest.mark.asyncio
async def test_bulk_complete_marks_many_done(db, harness_user):
    tasks = [
        Task(user_id=harness_user.id, title=f"Finish {i}", area="COLLEGE", priority="LOW", status="TODO")
        for i in range(3)
    ]
    db.add_all(tasks)
    db.commit()

    res = await default_registry.execute(
        "complete_tasks", db, harness_user, {"task_ids": [t.id for t in tasks]}
    )

    assert res.success and len(res.data["done"]) == 3
    for t in tasks:
        db.refresh(t)
        assert t.status == "COMPLETED"


@pytest.mark.asyncio
async def test_budget_extends_while_each_step_makes_progress(db, harness_user, monkeypatch):
    """One-item-per-reply models still finish: steps past the soft limit are allowed
    while every step does new, successful work."""
    monkeypatch.setattr("app.core.config.settings.ai_agent_max_steps", 2)
    monkeypatch.setattr("app.core.config.settings.ai_agent_max_steps_hard", 10)
    tasks = [
        Task(user_id=harness_user.id, title=f"Slow {i}", area="STARTUP", priority="LOW", status="TODO")
        for i in range(4)
    ]
    db.add_all(tasks)
    db.commit()
    seen: list = []
    script = [
        ChatResult(tool_calls=[_call("delete_task", {"task_id": t.id}, f"c{i}")])
        for i, t in enumerate(tasks)
    ] + [ChatResult(content="All 4 tasks deleted.")]
    _use(monkeypatch, MockProvider(chat_generator=_scripted(script, seen)))

    out, _ = await IrisAgent(default_registry).run_turn(db, harness_user, "delete all my tasks")

    assert out.content == "All 4 tasks deleted."
    assert all(s["tools"] is not None for s in seen)  # never cut off mid-job
    assert db.query(Task).filter(Task.title.like("Slow %")).count() == 0


@pytest.mark.asyncio
async def test_budget_stops_a_model_that_is_not_making_progress(db, harness_user, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ai_agent_max_steps", 3)
    monkeypatch.setattr("app.core.config.settings.ai_agent_max_steps_hard", 20)
    seen: list = []

    def looping(*, messages, tools):
        seen.append(tools)
        if tools is None:
            return ChatResult(content="Here is what I found.")
        return ChatResult(tool_calls=[_call("get_tasks", {"limit": 5}, f"c{len(seen)}")])

    _use(monkeypatch, MockProvider(chat_generator=looping))

    out, _ = await IrisAgent(default_registry).run_turn(db, harness_user, "look around")

    # Step 1 is new work; steps 2+ repeat it, so the soft budget (3) applies.
    assert len(seen) == 3 and seen[-1] is None
    assert out.content == "Here is what I found."


def test_prompt_tells_models_to_batch():
    from app.agent.harness import NATIVE_GUIDE

    assert "delete_tasks" in NATIVE_GUIDE and "Never handle one item per reply" in NATIVE_GUIDE


def _scripted_or_raise(results: list, seen: list | None = None):
    """Like _scripted, but an Exception in the list is raised (e.g. a timeout)."""
    queue = list(results)

    def gen(*, messages, tools):
        if seen is not None:
            seen.append({"messages": list(messages), "tools": tools})
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return gen


@pytest.mark.asyncio
async def test_stalled_model_recovers_a_reply_without_tools(db, harness_user, monkeypatch):
    from app.ai.provider import AIConnectionError

    seen: list = []
    provider = MockProvider(
        chat_generator=_scripted_or_raise(
            [
                ChatResult(tool_calls=[_call("get_tasks", {"limit": 5}, "c1")]),
                AIConnectionError("NVIDIA NIM request timed out after 45.0s"),
                ChatResult(content="Start Monday's assignment on Saturday: outline first, draft Sunday."),
            ],
            seen,
        )
    )
    _use(monkeypatch, provider)

    out, _ = await IrisAgent(default_registry).run_turn(db, harness_user, "Plan my assignment")

    assert out.content.startswith("Start Monday's assignment")
    assert seen[-1]["tools"] is None  # the recovery call is the lighter, tool-free one
    assert [m.role for m in seen[-1]["messages"]][-3:] == ["assistant", "tool", "user"]


@pytest.mark.asyncio
async def test_failed_recovery_after_lookups_says_so_honestly(db, harness_user, monkeypatch):
    from app.ai.provider import AIConnectionError

    provider = MockProvider(
        chat_generator=_scripted_or_raise(
            [
                ChatResult(tool_calls=[_call("get_tasks", {"limit": 5}, "c1")]),
                AIConnectionError("timed out"),
                AIConnectionError("timed out again"),
            ]
        )
    )
    _use(monkeypatch, provider)

    out, _ = await IrisAgent(default_registry).run_turn(db, harness_user, "Plan my assignment")

    assert "Done:" not in out.content  # a lookup isn't something IRIS "did"
    assert "stopped before it could answer" in out.content
