"""Deterministic Antigravity fast-paths and per-agent context slicing."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from app.agent.agent import default_agent
from app.agent.supervisor import get_iris_supervisor
from app.models.finance import FinanceTransaction
from app.models.coding_project import CodingProject
from app.models.user import User
from app.models.time_block import TimeBlock
from app.services.agy_bridge import AgySession, agy_manager
from app.services.memory_service import memory_service
from app.utils.datetime import utcnow


def _register_coding_workspace(db, user_id, directory, name="Workspace", alias=None, active=True):
    row=CodingProject(user_id=user_id,name=name,directory=str(directory),aliases=[alias or name.casefold()],
        read_access=True,write_access=True,command_access=True,is_active=active)
    db.add(row);db.commit();return row


def test_native_slash_runs_without_spawning_antigravity(db, user_id, monkeypatch, tmp_path):
    session = AgySession(key="iris", directory=str(tmp_path), alias="iris")
    session.state = "IDLE"
    session.buffer.append("models: gemini-3.1-pro")
    _register_coding_workspace(db,user_id,tmp_path,"IRIS","iris")

    monkeypatch.setattr(agy_manager, "spawn_or_attach", lambda *args, **kwargs: session)
    monkeypatch.setattr(
        agy_manager,
        "send_raw_input",
        lambda key, command: {"session": session.to_dict(), "recent_output": session.recent()},
    )

    user = db.get(User, user_id)
    response, actions = get_iris_supervisor().try_fast_path(db, user, {}, "/models")

    assert response is not None
    assert response.fast_path is True
    assert "/models" in response.message
    assert "gemini-3.1-pro" in response.message
    assert actions[0]["tool_name"] == "agy_run_slash_command"
    assert actions[0]["fast_path"] is True


def test_agy_prompt_fast_path_requires_reviewed_task(db, user_id, monkeypatch, tmp_path):
    session = AgySession(key="iris", directory=str(tmp_path), alias="iris")
    session.state = "IDLE"
    _register_coding_workspace(db,user_id,tmp_path,"IRIS","iris")
    sent: list[tuple[str, str]] = []

    monkeypatch.setattr(agy_manager, "spawn_or_attach", lambda *args, **kwargs: session)
    monkeypatch.setattr(
        agy_manager,
        "send_prompt",
        lambda key, prompt: sent.append((key, prompt)) or {"session": session.to_dict()},
    )

    user = db.get(User, user_id)
    response, _ = get_iris_supervisor().try_fast_path(
        db, user, {}, "agy fix the failing auth test"
    )

    assert response is not None
    assert response.fast_path is True
    assert sent == []
    assert "reviewed brief" in response.message.lower()


def test_expense_fast_path_writes_transaction(db, user_id):
    user = db.get(User, user_id)
    response, actions = get_iris_supervisor().try_fast_path(
        db, user, {}, "spent 250 on coffee"
    )

    assert response is not None
    assert response.fast_path is True
    assert "250" in response.message
    txn = (
        db.query(FinanceTransaction)
        .filter(FinanceTransaction.user_id == user.id)
        .order_by(FinanceTransaction.id.desc())
        .first()
    )
    assert txn is not None
    assert float(txn.amount) == 250
    assert actions[0]["tool_name"] == "log_expense"
    assert actions[0]["fast_path"] is True


def test_reflow_schedule_fast_path_moves_future_blocks(db, user_id):
    user = db.get(User, user_id)
    start = utcnow() + timedelta(hours=3)
    block = TimeBlock(
        user_id=user.id,
        start_time=start,
        end_time=start + timedelta(minutes=60),
    )
    db.add(block)
    db.commit()

    response, actions = get_iris_supervisor().try_fast_path(
        db, user, {}, "reflow schedule by 30"
    )

    assert response is not None
    assert response.fast_path is True
    db.refresh(block)
    assert block.start_time == start + timedelta(minutes=30)
    assert actions[0]["data"]["minutes"] == 30
    assert actions[0]["fast_path"] is True


def test_operator_context_is_sliced(db, user_id):
    user = db.get(User, user_id)
    context = get_iris_supervisor().slice_context_for_domain(db, user, "operator", {})

    assert "agy_sessions" in context
    assert "recent_coding_sessions" in context
    assert "open_tasks" not in context


def test_bare_attach_workspace_fast_path(db, user_id, monkeypatch, tmp_path):
    attached = []

    paths={}
    for alias in ("notebook","iris","marketory","nexus"):
        workspace=tmp_path/alias;workspace.mkdir()
        _register_coding_workspace(db,user_id,workspace,alias.capitalize(),alias,active=False)
        paths[alias]=workspace

    def fake_spawn_or_attach(directory=None, key=None, **kwargs):
        target = directory or paths["iris"]
        alias = Path(target).name.lower()
        session = AgySession(
            key=alias,
            directory=str(target),
            alias=alias,
        )
        session.state = "IDLE"
        attached.append((alias, session.directory))
        return session

    monkeypatch.setattr(agy_manager, "spawn_or_attach", fake_spawn_or_attach)

    user = db.get(User, user_id)
    supervisor = get_iris_supervisor()

    test_commands = [
        ("attach notebook", "notebook"),
        ("switch iris", "iris"),
        ("cd marketory", "marketory"),
        ("attach nexus", "nexus"),
        ("switch to notebook", "notebook"),
    ]

    for cmd, expected_alias in test_commands:
        response, actions = supervisor.try_fast_path(db, user, {}, cmd)
        assert response is not None, f"Expected fast-path hit for '{cmd}'"
        assert response.fast_path is True
        assert len(actions) == 1
        assert actions[0]["tool_name"] == "agy_attach_directory"
        assert actions[0]["fast_path"] is True
        assert actions[0]["success"] is True
        assert expected_alias in response.message.lower()


@pytest.mark.asyncio
async def test_fast_path_skips_memory_extraction(db, user_id, monkeypatch, tmp_path):
    session = AgySession(key="notebook", directory=str(tmp_path), alias="notebook")
    session.state = "IDLE"
    _register_coding_workspace(db,user_id,tmp_path,"Notebook","notebook")
    monkeypatch.setattr(agy_manager, "spawn_or_attach", lambda *args, **kwargs: session)

    calls = []

    async def fake_extract(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(memory_service, "extract_and_store_from_conversation", fake_extract)

    user = db.get(User, user_id)

    # 1. Turn with defer_memory=False: fast-path must still skip memory extraction entirely
    msg_out, conv = await default_agent.run_turn(
        db=db,
        user=user,
        user_message="attach notebook",
        defer_memory=False,
    )

    assert msg_out.fast_path is True
    assert msg_out.memories_updated == []
    assert len(calls) == 0, "Fast-path must consume 0 tokens and skip synchronous memory extraction"

    # 2. Deferred call to remember_turn: must immediately return [] without invoking LLM
    remembered = await default_agent.remember_turn(db, user, msg_out.id)
    assert remembered == []
    assert len(calls) == 0, "Fast-path must skip deferred memory extraction"
