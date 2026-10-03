"""Situational awareness (contextual memory) and personal model (external memory)."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from sqlalchemy.orm import Session

from app.agent.agent import IrisAgent
from app.agent.registry import default_registry
from app.agent.schemas import AgentResponseSchema
from app.ai.providers.mock import MockProvider
from app.intelligence.briefing import build_briefing
from app.intelligence.personal_model import build_personal_model, render_personal_model
from app.intelligence.situation import build_situation, render_situation
from app.models.ai_conversation import AIConversation, AIMessage
from app.models.focus_session import FocusSession
from app.models.recurring_schedule import RecurringSchedule
from app.models.user import User
from app.services.memory_service import memory_service
from app.utils.datetime import from_local, localize_date_boundaries, to_local, utcnow
from tests.conftest import make_task


@pytest.fixture
def user(db: Session, user_id: int) -> User:
    return db.get(User, user_id)


def _later_today(user: User) -> datetime:
    """A UTC time strictly between now and the end of the user's local day."""
    now = utcnow()
    end = localize_date_boundaries(to_local(now, user.timezone).date(), user.timezone)[1]
    return now + (end - now) / 2


def _seed_tasks(db: Session, user: User) -> dict[str, int]:
    now = utcnow()
    ids = {
        "overdue": make_task(db, user.id, title="Overdue report", deadline=now - timedelta(days=2)),
        "today": make_task(
            db, user.id, title="Compiler assignment", area="COLLEGE", deadline=_later_today(user)
        ),
        "week": make_task(db, user.id, title="Pitch deck", deadline=now + timedelta(days=3)),
        "doing": make_task(db, user.id, title="Landing page", status="IN_PROGRESS"),
        "blocked": make_task(db, user.id, title="Stripe setup", status="BLOCKED"),
        "done": make_task(
            db, user.id, title="Customer call notes", status="COMPLETED", completed_at=now
        ),
    }
    return {k: v.id for k, v in ids.items()}


def _seed_history(db: Session, user: User) -> None:
    """Ten evening completions that ran 50% over estimate, plus focus sessions."""
    today = to_local(utcnow(), user.timezone).date()
    for i in range(1, 11):
        local = datetime.combine(today - timedelta(days=i), time(21, 15))
        make_task(
            db,
            user.id,
            title=f"Past task {i}",
            status="COMPLETED",
            completed_at=from_local(local, user.timezone),
            estimated_duration=30,
            actual_duration=45,
        )
    for i in range(1, 5):
        start = from_local(datetime.combine(today - timedelta(days=i), time(21, 0)), user.timezone)
        db.add(
            FocusSession(
                user_id=user.id,
                started_at=start,
                ended_at=start + timedelta(minutes=50),
                planned_duration=50,
                actual_duration=50,
                status="COMPLETED",
            )
        )
    db.commit()


# --- Contextual memory ------------------------------------------------------------


def test_situation_categorises_pending_priority_and_done(db, user):
    ids = _seed_tasks(db, user)
    s = build_situation(db, user)
    t = s["tasks"]

    assert [x["id"] for x in t["overdue"]] == [ids["overdue"]]
    assert [x["id"] for x in t["due_today"]] == [ids["today"]]
    assert [x["id"] for x in t["due_this_week"]] == [ids["week"]]
    assert [x["id"] for x in t["in_progress"]] == [ids["doing"]]
    assert [x["id"] for x in t["blocked"]] == [ids["blocked"]]
    assert t["open_count"] == 5
    assert t["top_priorities"], "deterministic ranking should be included"
    assert [d["title"] for d in s["done"]["today"]] == ["Customer call notes"]
    assert t["overdue"][0]["due"].startswith("overdue by")

    text = render_situation(s)
    for title in ("Overdue report", "Compiler assignment", "Landing page", "Customer call notes"):
        assert title in text
    assert "OVERDUE" in text and "Priority ranking" in text


def test_situation_reports_changes_since_last_conversation(db, user):
    since = utcnow() - timedelta(hours=5)
    make_task(
        db, user.id, title="Old task", status="COMPLETED", completed_at=since - timedelta(hours=1)
    )
    make_task(db, user.id, title="Fresh win", status="COMPLETED", completed_at=utcnow())
    make_task(db, user.id, title="Slipped", deadline=utcnow() - timedelta(hours=1))

    changes = build_situation(db, user, since=since)["since_last_conversation"]

    assert changes["completed"] == ["Fresh win"]
    assert "Slipped" in changes["became_overdue"]
    assert "Slipped" in changes["created"]


def test_today_schedule_includes_routine_for_today(db, user):
    weekday = to_local(utcnow(), user.timezone).strftime("%a")
    db.add(
        RecurringSchedule(
            user_id=user.id,
            name="Internship",
            type="WORK",
            days_of_week=weekday,
            start_time="11:00",
            end_time="20:00",
            is_hard_constraint=True,
            status="ACTIVE",
        )
    )
    db.commit()
    schedule = build_situation(db, user)["today_schedule"]
    assert any(i["title"] == "Internship" and i["hard"] for i in schedule)


# --- External memory (personal model) -------------------------------------------------


def test_personal_model_learns_work_patterns(db, user):
    _seed_history(db, user)
    observed = build_personal_model(db, user)["observed"]

    start = int(observed["peak_hours"]["window"][:2])
    assert 21 in {(start + k) % 24 for k in range(3)}
    assert observed["estimation"]["ratio"] == pytest.approx(1.5)
    assert "longer than estimated" in observed["estimation"]["verdict"]
    assert observed["focus"]["typical_minutes"] == 50
    assert observed["focus"]["completion_rate_pct"] == 100


def test_personal_model_needs_evidence_before_claiming_patterns(db, user):
    make_task(db, user.id, title="Lone task", status="COMPLETED", completed_at=utcnow())
    observed = build_personal_model(db, user)["observed"]
    assert set(observed) == {"lookback_days"}
    assert "not enough history" in render_personal_model(build_personal_model(db, user))


def test_personal_model_includes_stated_routine_and_work_style(db, user):
    memory_service.store_memory(
        db, user, "Wakes at 6:30, gym 7-8", category="ROUTINE", key="morning"
    )
    memory_service.store_memory(db, user, "Best focus in 90m blocks", category="WORK_STYLE")
    memory_service.store_memory(db, user, "Nexus targets dentists", category="PROJECT")

    pm = build_personal_model(db, user)
    stated = {m["content"] for m in pm["stated"]}
    assert stated == {"Wakes at 6:30, gym 7-8", "Best focus in 90m blocks"}
    text = render_personal_model(pm)
    assert "[ROUTINE] Wakes at 6:30" in text
    assert "[WORK_STYLE] Best focus" in text


def test_heuristics_capture_routine_and_work_style():
    extracted = memory_service._heuristic_extract(
        "I wake up at 6:30 am. I work best late at night after dinner."
    )
    by_key = {e["key"]: e for e in extracted}
    assert by_key["wake_time"]["category"] == "ROUTINE"
    assert by_key["peak_focus"]["category"] == "WORK_STYLE"


# --- The agent sees all of it ------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_prompt_carries_situation_and_personal_model(db, user, monkeypatch):
    _seed_tasks(db, user)
    memory_service.store_memory(db, user, "Gym every day at 7am", category="ROUTINE", key="gym")
    memory_service.store_memory(db, user, "Co-founder is Alex", category="PEOPLE", key="cofounder")
    systems: list[str] = []

    def gen(*, system, prompt, schema):
        systems.append(system)
        return AgentResponseSchema(message="On it.")

    monkeypatch.setattr(
        "app.agent.agent.get_ai_provider", lambda: MockProvider(default_response_generator=gen)
    )
    await IrisAgent(default_registry).run_turn(db, user, "What's on my plate? Ask Alex too.")

    system = systems[0]
    assert "RIGHT NOW" in system and "WHO " in system
    assert "Overdue report" in system and "Customer call notes" in system
    assert "[ROUTINE] Gym every day at 7am" in system
    memory_block = system.split("STORED USER MEMORY & CONTEXT", 1)[1]
    assert "Co-founder is Alex" in memory_block
    assert "Gym every day" not in memory_block  # no duplication with the profile


@pytest.mark.asyncio
async def test_completed_tasks_tool(db, user):
    _seed_tasks(db, user)
    res = await default_registry.execute("get_completed_tasks", db, user, {"days": 3})
    assert res.success and [t["title"] for t in res.data] == ["Customer call notes"]

    res = await default_registry.execute("get_situation", db, user, {})
    assert res.success and res.data["tasks"]["open_count"] == 5


def test_last_conversation_timestamp_drives_since_section(db, user):
    conv = AIConversation(user_id=user.id, title="t")
    db.add(conv)
    db.flush()
    db.add(AIMessage(conversation_id=conv.id, role="USER", content="hi"))
    db.commit()
    from app.intelligence.situation import last_user_message_at

    assert last_user_message_at(db, user.id) is not None


# --- Briefing & API --------------------------------------------------------------------------


def test_briefing_flags_risks_and_focus(db, user):
    _seed_tasks(db, user)
    _seed_history(db, user)
    b = build_briefing(build_situation(db, user), build_personal_model(db, user))
    kinds = {p["kind"] for p in b["points"]}
    assert {"risk", "deadline", "focus", "energy", "tip", "done"} <= kinds
    assert "Overdue report" in b["text"]
    assert b["source"] == "DETERMINISTIC"


def test_assistant_endpoints(client):
    sit = client.get("/api/assistant/situation")
    assert sit.status_code == 200 and "tasks" in sit.json()
    prof = client.get("/api/assistant/profile")
    assert prof.status_code == 200 and "observed" in prof.json()
    brief = client.get("/api/assistant/briefing?narrate=true")
    assert brief.status_code == 200
    assert brief.json()["source"] == "DETERMINISTIC"  # AI disabled in tests
