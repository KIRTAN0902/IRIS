"""Startup module API tests: startup, leads, outreach, experiments, analytics."""

from __future__ import annotations


def _make_startup(client) -> int:
    r = client.post(
        "/api/startup",
        json={"name": "IRIS Labs", "description": "AI planning", "status": "LAUNCHED"},
    )
    assert r.status_code == 201
    return r.json()["id"]


def _make_lead(client, startup_id: int, name: str = "Prospect One") -> dict:
    r = client.post(
        "/api/leads",
        json={
            "startup_id": startup_id,
            "name": name,
            "company": "Acme",
            "role": "CTO",
            "email": f"{name.lower().replace(' ', '.')}@acme.dev",
            "source": "LINKEDIN",
        },
    )
    assert r.status_code == 201
    return r.json()


def test_startup_crud_and_current_objective(client):
    sid = _make_startup(client)
    listed = client.get("/api/startup").json()
    assert any(s["id"] == sid for s in listed)

    up = client.patch(f"/api/startup/{sid}", json={"current_objective": "Outreach / Distribution"})
    assert up.status_code == 200
    assert up.json()["current_objective"] == "Outreach / Distribution"


def test_lead_crud_and_filters(client):
    sid = _make_startup(client)
    lead = _make_lead(client, sid)

    got = client.get(f"/api/leads/{lead['id']}")
    assert got.status_code == 200

    up = client.patch(f"/api/leads/{lead['id']}", json={"status": "CONTACTED"})
    assert up.json()["status"] == "CONTACTED"

    filtered = client.get("/api/leads", params={"status": "CONTACTED"}).json()
    assert [lead_item["id"] for lead_item in filtered] == [lead["id"]]

    deleted = client.delete(f"/api/leads/{lead['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/leads/{lead['id']}").status_code == 404


def test_lead_validation_bad_email(client):
    sid = _make_startup(client)
    r = client.post(
        "/api/leads",
        json={"startup_id": sid, "name": "X", "email": "not-an-email"},
    )
    assert r.status_code == 422


def test_logging_outreach_updates_lead_status_and_metrics(client):
    sid = _make_startup(client)
    lead = _make_lead(client, sid)

    r = client.post(
        "/api/outreach",
        json={"lead_id": lead["id"], "startup_id": sid, "type": "EMAIL", "result": "SENT"},
    )
    assert r.status_code == 201
    activity = r.json()

    after = client.get(f"/api/leads/{lead['id']}").json()
    assert after["last_contacted"] is not None

    # Reply logged via a second activity.
    client.post(
        "/api/outreach",
        json={"lead_id": lead["id"], "startup_id": sid, "type": "EMAIL", "result": "REPLIED"},
    )

    history = client.get("/api/outreach", params={"lead_id": lead["id"]}).json()
    assert len(history) == 2
    assert history[0]["result"] == "REPLIED"  # newest first

    metrics = client.get("/api/analytics/startup").json()
    assert metrics["outreach"]["total"] == 2
    assert metrics["outreach"]["replies"] == 1

    patch = client.patch(f"/api/outreach/{activity['id']}", json={"notes": "follow up Fri"})
    assert patch.json()["notes"] == "follow up Fri"


def test_outreach_lead_mismatch_rejected(client):
    sid = _make_startup(client)
    other = _make_startup(client)
    lead = _make_lead(client, sid)
    r = client.post(
        "/api/outreach",
        json={"lead_id": lead["id"], "startup_id": other, "type": "CALL", "result": "SENT"},
    )
    assert r.status_code == 404


def test_experiment_lifecycle(client):
    sid = _make_startup(client)
    exp = client.post(
        "/api/experiments",
        json={
            "startup_id": sid,
            "name": "Cold email vs LinkedIn",
            "hypothesis": "Email replies > LinkedIn replies",
            "action": "Send 20 of each",
            "metric": "reply_rate",
            "target": "5%",
            "status": "RUNNING",
        },
    )
    assert exp.status_code == 201
    experiment = exp.json()

    done = client.patch(
        f"/api/experiments/{experiment['id']}",
        json={
            "status": "COMPLETED",
            "result": "Email 10% vs LinkedIn 3%",
            "conclusion": "Email wins",
            "next_action": "Double email volume",
        },
    )
    assert done.json()["status"] == "COMPLETED"

    running = client.get("/api/experiments", params={"status": "RUNNING"}).json()
    assert running == []
