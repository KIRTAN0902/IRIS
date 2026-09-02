"""Integration tests: migrations apply cleanly and a full user flow works."""

from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_EXE = BACKEND_DIR / ".venv" / "Scripts" / "alembic.exe"


def test_migrations_apply_to_fresh_database(tmp_path):
    """`alembic upgrade head` must build the full schema from scratch (spec §7)."""
    db_path = tmp_path / "migration-test.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [str(ALEMBIC_EXE), "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()

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
    r = client.get("/api/tasks/424242")
    body = r.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}
