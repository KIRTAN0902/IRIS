"""Task CRUD + filter API tests."""

from __future__ import annotations

from datetime import timedelta

from app.utils.datetime import utcnow


def _create(client, **overrides):
    payload = {"title": "Write essay", "area": "COLLEGE", "priority": "HIGH"}
    payload.update(overrides)
    return client.post("/api/tasks", json=payload)


def test_create_and_get_task(client):
    r = _create(client)
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Write essay"
    assert body["status"] == "TODO"
    assert body["is_overdue"] is False

    got = client.get(f"/api/tasks/{body['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == body["id"]


def test_update_and_complete_task(client):
    task_id = _create(client).json()["id"]

    up = client.patch(f"/api/tasks/{task_id}", json={"priority": "CRITICAL"})
    assert up.status_code == 200
    assert up.json()["priority"] == "CRITICAL"

    done = client.post(f"/api/tasks/{task_id}/complete", json={"actual_duration": 45})
    assert done.status_code == 200
    body = done.json()
    assert body["status"] == "COMPLETED"
    assert body["completed_at"] is not None
    assert body["actual_duration"] == 45

    # Completing twice conflicts.
    again = client.post(f"/api/tasks/{task_id}/complete")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "TASK_ALREADY_COMPLETED"


def test_delete_task(client):
    task_id = _create(client).json()["id"]
    assert client.delete(f"/api/tasks/{task_id}").status_code == 204
    assert client.get(f"/api/tasks/{task_id}").status_code == 404


def test_filters_area_status_priority_deadline(client):
    _create(client, title="College A", area="COLLEGE")
    _create(
        client,
        title="Startup B",
        area="STARTUP",
        deadline=(utcnow() + timedelta(days=2)).isoformat(),
    )
    startup_open = client.get("/api/tasks", params={"area": "STARTUP"}).json()
    assert [t["title"] for t in startup_open] == ["Startup B"]

    soon = client.get(
        "/api/tasks",
        params={"deadline_before": (utcnow() + timedelta(days=3)).isoformat()},
    )
    titles = {t["title"] for t in soon.json()}
    assert "Startup B" in titles

    college = client.get("/api/tasks", params={"status": "TODO", "area": "COLLEGE"})
    assert all(t["area"] == "COLLEGE" for t in college.json())


def test_validation_error_uses_error_envelope(client):
    r = _create(client, title="")
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "message" in err


def test_missing_task_returns_typed_error(client):
    r = client.get("/api/tasks/99999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "TASK_NOT_FOUND"


def test_search_by_filters_combined(client):
    _create(client, title="ML exam prep", area="COLLEGE", priority="CRITICAL")
    _create(client, title="Gym", area="PERSONAL")
    r = client.get("/api/tasks", params={"area": "COLLEGE", "priority": "CRITICAL"})
    assert len(r.json()) == 1
