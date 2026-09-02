"""API tests for Intelligence Signals, Attention, Decision History, and Feedback (Phase 3)."""

from __future__ import annotations

from app.models.ai_recommendation import AIRecommendation
from app.models.enums import DecisionFeedbackStatus, LifeArea
from tests.conftest import hours_from_now, make_task


def test_get_signals_api(client, db, user_id):
    """GET /api/intelligence/signals returns dynamic and stored signals."""
    make_task(
        db,
        user_id,
        title="Critical bug in pipeline",
        area=LifeArea.INTERNSHIP.value,
        deadline=hours_from_now(2),
    )

    r = client.get("/api/intelligence/signals")
    assert r.status_code == 200
    signals = r.json()
    assert isinstance(signals, list)
    assert len(signals) >= 1
    assert any(
        "pipeline" in s["title"].lower() or "deadline" in s["title"].lower() for s in signals
    )

    # Filter by domain
    r_domain = client.get("/api/intelligence/signals?domain=TASKS")
    assert r_domain.status_code == 200
    assert all(s["domain"] == "TASKS" for s in r_domain.json())


def test_get_attention_api(client, db, user_id):
    """GET /api/intelligence/attention returns ranked attention items."""
    make_task(
        db,
        user_id,
        title="Compiler Project Submission",
        area=LifeArea.COLLEGE.value,
        deadline=hours_from_now(1),
    )

    r = client.get("/api/intelligence/attention")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) >= 1
    assert "score" in items[0]
    assert "suggested_action" in items[0]
    assert items[0]["score"] >= items[-1]["score"]


def test_decision_history_and_feedback_api(client, db, user_id):
    """Trigger decision, retrieve history, and record user feedback."""
    make_task(
        db,
        user_id,
        title="Founder outreach batch 1",
        area=LifeArea.STARTUP.value,
        priority="HIGH",
    )

    # 1. Trigger recommendation
    r_rec = client.post("/api/intelligence/recommend?available_minutes=60&use_ai=false")
    assert r_rec.status_code == 200
    rec_body = r_rec.json()
    assert rec_body["title"] == "Founder outreach batch 1"

    # Manually create audit recommendation to test feedback loop
    audit = AIRecommendation(
        user_id=user_id,
        title="Founder outreach batch 1",
        recommendation_type="TASK",
        decision_type="SHOULD_DO",
        source="DETERMINISTIC",
        reason="Startup focus",
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)

    # 2. Get history
    r_hist = client.get("/api/intelligence/decisions")
    assert r_hist.status_code == 200
    history = r_hist.json()
    assert len(history) >= 1
    assert history[0]["id"] == audit.id

    # 3. Post feedback
    fb_payload = {
        "recommendation_id": audit.id,
        "feedback": DecisionFeedbackStatus.ACCEPTED.value,
        "notes": "Completed outreach to 10 founders.",
    }
    r_fb = client.post("/api/intelligence/feedback", json=fb_payload)
    assert r_fb.status_code == 200
    fb_res = r_fb.json()
    assert fb_res["feedback"] == DecisionFeedbackStatus.ACCEPTED.value
    assert fb_res["feedback_notes"] == "Completed outreach to 10 founders."

    # 4. Invalid feedback rejected
    r_bad = client.post(
        "/api/intelligence/feedback",
        json={"recommendation_id": audit.id, "feedback": "INVALID_STATUS"},
    )
    assert r_bad.status_code == 422


def test_today_api_includes_phase_3_context(client, db, user_id):
    """GET /api/intelligence/today includes attention, domain signals, and decisions."""
    make_task(
        db,
        user_id,
        title="Outreach to Ahmedabad founders",
        area=LifeArea.STARTUP.value,
        deadline=hours_from_now(3),
    )

    r = client.get("/api/intelligence/today")
    assert r.status_code == 200
    body = r.json()

    assert "attention_items" in body
    assert "domain_signals" in body
    assert "recent_decisions" in body
    assert "evidence" in body["current_recommendation"]
