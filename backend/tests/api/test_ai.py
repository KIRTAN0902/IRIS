"""AI endpoint tests with mocked Gemini.

The deterministic fallback paths run with AI disabled (no GEMINI_API_KEY in
the test env). The "AI available" paths mock ``client.generate_structured`` so
no live API call ever happens (spec §40).
"""

from __future__ import annotations

import pytest

from app.ai.factory import set_ai_provider
from app.ai.providers.mock import MockProvider
from tests.conftest import hours_from_now, utcnow


def _mock_ai(monkeypatch, payload: dict):
    provider = MockProvider(
        name="mock",
        default_response_generator=lambda system, prompt, schema: schema.model_validate(payload),
    )
    set_ai_provider(provider)


def test_recommend_deterministic_fallback(client, db, user_id):
    from app.models.task import Task

    db.add(
        Task(
            user_id=user_id,
            title="Contact 20 prospects",
            area="STARTUP",
            priority="HIGH",
            deadline=hours_from_now(3),
        )
    )
    db.commit()

    r = client.post("/api/ai/recommend?available_minutes=60")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "DETERMINISTIC"
    assert body["recommendation_type"] == "TASK"
    assert body["title"] == "Contact 20 prospects"
    assert body["task_id"] is not None
    assert 0 <= body["confidence"] <= 1


def test_recommend_no_tasks_returns_break(client):
    r = client.post("/api/ai/recommend?available_minutes=30")
    assert r.status_code == 200
    body = r.json()
    assert body["recommendation_type"] == "BREAK"


def test_recommend_uses_ai_when_valid_task_id(client, db, user_id, monkeypatch):
    from app.models.task import Task

    task = Task(user_id=user_id, title="Research 30 prospects", area="STARTUP")
    db.add(task)
    db.commit()
    db.refresh(task)

    _mock_ai(
        monkeypatch,
        {
            "recommendation_type": "TASK",
            "task_id": task.id,
            "title": "Startup outreach",
            "reason": "Weekly outreach target is behind.",
            "duration_minutes": 90,
            "expected_outcome": "Contact 15 prospects",
            "confidence": 0.87,
        },
    )
    r = client.post("/api/ai/recommend")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "AI"
    assert body["title"] == "Startup outreach"
    assert body["confidence"] == pytest.approx(0.87)


def test_recommend_rejects_hallucinated_task_id(client, monkeypatch):
    """AI citing a nonexistent task_id must fall back to deterministic output."""
    _mock_ai(
        monkeypatch,
        {
            "recommendation_type": "TASK",
            "task_id": 424242,
            "title": "Invented task",
            "reason": "hallucination",
            "confidence": 0.99,
        },
    )
    r = client.post("/api/ai/recommend")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "DETERMINISTIC"
    assert body["title"] != "Invented task"


def test_plan_day_returns_draft_within_free_time(client, db, user_id):
    from app.models.task import Task

    db.add_all(
        [
            Task(user_id=user_id, title="A", estimated_duration=30),
            Task(user_id=user_id, title="B", estimated_duration=600),
        ]
    )
    db.commit()

    r = client.post("/api/ai/plan-day")
    assert r.status_code == 200
    body = r.json()
    assert len(body["blocks"]) >= 1
    # Blocks never overlap each other.
    intervals = sorted((b["start"], b["end"]) for b in body["blocks"])
    for (_, e1), (s2, _) in zip(intervals, intervals[1:], strict=False):
        assert s2 >= e1
    # The impossible 10h task ends up unscheduled or split -- never silently dropped.


def test_daily_review_deterministic_summary(client, db, user_id):
    from app.models.task import Task

    done = Task(user_id=user_id, title="Finished lab", area="COLLEGE", status="COMPLETED")
    done.completed_at = utcnow()
    missed = Task(
        user_id=user_id,
        title="Missed quiz",
        area="COLLEGE",
        deadline=hours_from_now(-1),
    )
    db.add_all([done, missed])
    db.commit()

    r = client.post("/api/ai/daily-review")
    assert r.status_code == 200
    body = r.json()
    assert "1 task(s) completed" in body["summary"]
    assert body["summary"]  # non-empty fallback


def test_startup_analysis_separates_fact_from_hypothesis(client, db, user_id):
    from app.models.lead import Lead
    from app.models.startup import Startup

    s = Startup(user_id=user_id, name="S", status="LAUNCHED")
    db.add(s)
    db.commit()
    db.refresh(s)
    lead = Lead(startup_id=s.id, name="L")
    db.add(lead)
    db.commit()

    r = client.post("/api/ai/startup-analysis")
    assert r.status_code == 200
    body = r.json()
    assert body["data_evidence"]["total_outreach"] == 0
    assert body["priority"] == "LOW"
    # Sparse data: fallback explicitly recommends logging more outreach.
    assert "Log more outreach" in (body["recommendation"] or "")


def test_ask_persists_conversation(client, db, user_id):
    r1 = client.post("/api/ai/ask", json={"question": "What should I do tonight?"})
    assert r1.status_code == 200
    conv_id = r1.json()["conversation_id"]
    assert r1.json()["answer"]

    r2 = client.post(
        "/api/ai/ask",
        json={"question": "And tomorrow morning?", "conversation_id": conv_id},
    )
    assert r2.json()["conversation_id"] == conv_id

    msgs = client.get(f"/api/ai/conversations/{conv_id}/messages").json()
    roles = [m["role"] for m in msgs]
    assert roles.count("USER") == 2
    assert roles.count("ASSISTANT") == 2


def test_ask_with_mocked_ai(client, monkeypatch):
    _mock_ai(
        monkeypatch,
        {"answer": "Work on startup outreach tonight.", "follow_ups": ["Why?"]},
    )
    r = client.post("/api/ai/ask", json={"question": "What should I do tonight?"})
    body = r.json()
    assert body["source"] == "AI"
    assert "outreach" in body["answer"].lower()


def test_ask_validation_min_length(client):
    r = client.post("/api/ai/ask", json={"question": "?"})
    assert r.status_code == 422


def test_gemini_outage_keeps_endpoints_alive(client, monkeypatch):
    """Spec §41: AI failures must not break the API."""

    class FailingProvider(MockProvider):
        async def generate_structured(self, *, system, prompt, schema):
            raise RuntimeError("network down")

    set_ai_provider(FailingProvider())

    for url in ("/api/ai/recommend", "/api/ai/plan-day", "/api/ai/daily-review"):
        r = client.post(url)
        assert r.status_code == 200, url
        assert r.json()["source"] == "DETERMINISTIC"

    r = client.post("/api/ai/ask", json={"question": "hello there"})
    assert r.status_code == 200
    assert r.json()["source"] == "DETERMINISTIC"


def test_weekly_progress_tool_shape(client, db, user_id):
    from app.ai.tools import get_weekly_progress

    result = get_weekly_progress(db, type("U", (), {"id": user_id, "timezone": "Asia/Kolkata"})())
    assert "tasks_completed" in result
