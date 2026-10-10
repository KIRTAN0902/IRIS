"""Tests for autonomous coding API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_coding_api_endpoints(client: TestClient):
    # 1. Launch coding task
    res = client.post(
        "/api/coding/tasks",
        json={
            "instruction": "Fix linting errors and run pytest",
            "workspace": "iris",
        },
    )
    assert res.status_code == 202
    data = res.json()
    task_id = data["task_id"]
    assert task_id is not None
    assert data["status"] in ("QUEUED", "RUNNING")

    # 2. Get task by ID
    res = client.get(f"/api/coding/tasks/{task_id}")
    assert res.status_code == 200
    assert res.json()["task_id"] == task_id

    # 3. List tasks
    res = client.get("/api/coding/tasks")
    assert res.status_code == 200
    assert any(t["task_id"] == task_id for t in res.json())
