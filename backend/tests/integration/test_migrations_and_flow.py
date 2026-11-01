"""Integration tests: migrations apply cleanly and a full user flow works."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_migrations_apply_to_fresh_database(tmp_path):
    """`alembic upgrade head` must build the full schema from scratch (spec §7)."""
    db_path = tmp_path / "migration-test.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr

    engine = create_engine(db_url)
    tables = set(inspect(engine).get_table_names())

    expected = {
        "users",
        "tasks",
        "projects",
        "goals",
        "time_blocks",
        "calendar_events",
        "focus_sessions",
        "daily_reviews",
        "startups",
        "leads",
        "outreach_activities",
        "experiments",
        "metrics",
        "ai_conversations",
        "ai_messages",
        "ai_recommendations",
        "recurring_schedules",
        "signals",
        "ai_memories",
        "alembic_version",

    }
    missing = expected - tables
    assert not missing, f"Migration output missing tables: {missing}"


def test_full_progress_flow(client, db, user_id):
    """Goal -> task -> complete -> analytics reflect real progress (spec §48)."""
    goal = client.post(
        "/api/goals",
        json={
            "name": "Contact 100 prospects",
            "area": "STARTUP",
            "target_value": 100,
            "current_value": 40,
            "unit": "prospects",
            "status": "ACTIVE",
        },
    ).json()
    task = client.post(
        "/api/tasks",
        json={
            "title": "Contact 20 prospects today",
            "area": "STARTUP",
            "goal_id": goal["id"],
            "estimated_duration": 60,
        },
    ).json()

    # Priority engine links it to the active goal.
    ranked = client.get("/api/analytics/priorities").json()
    entry = next(x for x in ranked if x["task"]["id"] == task["id"])
    assert entry["breakdown"]["goal_alignment_score"] >= 8.0

    done = client.post(f"/api/tasks/{task['id']}/complete", json={"actual_duration": 55})
    assert done.json()["status"] == "COMPLETED"

    week = client.get("/api/analytics/productivity", params={"period": "week"}).json()
    assert week["tasks_completed"] == 1
    assert week["actual_minutes"] == 55


def test_error_envelope_never_exposes_stack(client):
    r = client.get("/api/tasks/424242", headers={"X-Request-ID": "milestone-e-check-17"})
    body = r.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "TASK_NOT_FOUND"
    assert body["error"]["category"] == "not_found"
    assert body["error"]["retryable"] is False
    assert body["error"]["correlation_id"] == "milestone-e-check-17"
    assert r.headers["X-Request-ID"] == "milestone-e-check-17"
    assert "Traceback" not in r.text


def test_validation_error_has_correlation_metadata(client):
    response = client.post("/api/chat/conversations", params={"title": "x" * 256})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["category"] == "validation"
    assert error["retryable"] is False
    assert error["correlation_id"] == response.headers["X-Request-ID"]


def test_http_5xx_error_detail_is_not_returned_to_client():
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    from app.core.errors import register_exception_handlers

    isolated_app = FastAPI()
    register_exception_handlers(isolated_app)

    @isolated_app.get("/provider-error")
    def provider_error():
        raise HTTPException(503, detail="secret=private-token provider response body")

    with TestClient(isolated_app) as test_client:
        response = test_client.get("/provider-error")
    assert response.status_code == 503
    assert "private-token" not in response.text
    assert "provider response body" not in response.text
    assert response.json()["error"]["category"] == "service_unavailable"
    assert response.json()["error"]["retryable"] is True
