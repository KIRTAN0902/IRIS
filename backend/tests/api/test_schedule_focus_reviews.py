"""Schedule, focus session, daily review + users API tests."""

from __future__ import annotations

from datetime import date, timedelta

from app.utils.datetime import utcnow


def _slot(hours_ahead: float, minutes: int):
    start = (utcnow() + timedelta(hours=hours_ahead)).replace(minute=0, second=0, microsecond=0)
    return start.isoformat(), (start + timedelta(minutes=minutes)).isoformat()


def test_time_block_overlap_conflict(client):
    s, e = _slot(1, 60)
    first = client.post("/api/time-blocks", json={"start_time": s, "end_time": e})
    assert first.status_code == 201

    conflict = client.post("/api/time-blocks", json={"start_time": s, "end_time": e})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "TIME_BLOCK_OVERLAP"

    # allow_overlap escapes the guard.
    ok = client.post(
        "/api/time-blocks", json={"start_time": s, "end_time": e, "allow_overlap": True}
    )
    assert ok.status_code == 201


def test_availability_subtracts_block(client):
    s, e = _slot(2, 30)
    client.post("/api/time-blocks", json={"start_time": s, "end_time": e})
    window_start = utcnow().isoformat()
    window_end = (utcnow() + timedelta(hours=4)).isoformat()
    r = client.get(
        "/api/availability",
        params={"window_start": window_start, "window_end": window_end},
    )
    assert r.status_code == 200
    body = r.json()
    assert 0 < body["total_free_minutes"] < 240
    assert len(body["busy_intervals"]) == 1


def test_calendar_event_crud(client):
    s, e = _slot(5, 45)
    r = client.post(
        "/api/calendar-events",
        json={"title": "Internship standup", "start_time": s, "end_time": e},
    )
    assert r.status_code == 201
    listed = client.get("/api/calendar-events").json()
    assert any(ev["title"] == "Internship standup" for ev in listed)


def test_focus_session_flow(client):
    task = client.post("/api/tasks", json={"title": "Build feature", "area": "INTERNSHIP"}).json()

    started = client.post("/api/focus/start", json={"task_id": task["id"], "planned_duration": 50})
    assert started.status_code == 201
    session = started.json()
    assert session["status"] == "RUNNING"

    completed = client.post(f"/api/focus/{session['id']}/complete")
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "COMPLETED"
    assert body["ended_at"] is not None
    assert body["actual_duration"] >= 0

    # Actual duration feeds back into the task (planned vs actual learning).
    after = client.get(f"/api/tasks/{task['id']}").json()
    assert after["actual_duration"] == body["actual_duration"]

    # Double completion conflicts.
    again = client.post(f"/api/focus/{session['id']}/complete")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "FOCUS_ALREADY_FINISHED"


def test_daily_review_upsert_rules(client):
    day = str(date.today())
    payload = {"date": day, "productivity_rating": 4, "notes": "solid day"}

    created = client.post("/api/reviews", json=payload)
    assert created.status_code == 201
    review = created.json()
    assert review["date"] == day

    dup = client.post("/api/reviews", json=payload)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "REVIEW_EXISTS"

    patched = client.patch(f"/api/reviews/{day}", json={"blockers": "none"})
    assert patched.json()["blockers"] == "none"

    got = client.get(f"/api/reviews/{day}")
    assert got.status_code == 200


def test_users_me_roundtrip(client):
    me = client.get("/api/users/me")
    assert me.status_code == 200
    assert "@" in me.json()["email"]

    up = client.patch("/api/users/me", json={"timezone": "Asia/Kolkata", "name": "K"})
    assert up.status_code == 200
    assert up.json()["name"] == "K"
