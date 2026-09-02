"""Goal + project API tests."""

from __future__ import annotations

import pytest


def test_goal_hierarchy_tree(client):
    top = client.post(
        "/api/goals",
        json={"name": "Build successful startup", "area": "STARTUP"},
    ).json()
    mid = client.post(
        "/api/goals",
        json={"name": "First 10 customers", "area": "STARTUP", "parent_goal_id": top["id"]},
    ).json()
    leaf = client.post(
        "/api/goals",
        json={
            "name": "Contact 100 prospects",
            "area": "STARTUP",
            "parent_goal_id": mid["id"],
            "target_value": 100,
            "current_value": 20,
            "unit": "prospects",
        },
    ).json()

    tree = client.get("/api/goals").json()
    assert len(tree) == 1  # single root
    root = tree[0]
    assert root["children"][0]["id"] == mid["id"]
    assert root["children"][0]["children"][0]["id"] == leaf["id"]
    assert leaf["progress_fraction"] == pytest.approx(0.2)


def test_goal_auto_achieves_when_target_reached(client):
    goal = client.post(
        "/api/goals",
        json={
            "name": "Send 100 outreach messages/week",
            "area": "STARTUP",
            "target_value": 100,
            "current_value": 90,
            "unit": "messages",
            "status": "ACTIVE",
        },
    ).json()
    updated = client.patch(f"/api/goals/{goal['id']}", json={"current_value": 100}).json()
    assert updated["status"] == "ACHIEVED"


def test_goal_cycle_rejected(client):
    a = client.post("/api/goals", json={"name": "A", "area": "STARTUP"}).json()
    b = client.post(
        "/api/goals", json={"name": "B", "area": "STARTUP", "parent_goal_id": a["id"]}
    ).json()
    # Making A's parent B would create a cycle.
    r = client.patch(f"/api/goals/{a['id']}", json={"parent_goal_id": b["id"]})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "GOAL_CYCLE"


def test_delete_goal_with_children_conflicts(client):
    top = client.post("/api/goals", json={"name": "Top", "area": "PERSONAL"}).json()
    client.post(
        "/api/goals", json={"name": "Child", "area": "PERSONAL", "parent_goal_id": top["id"]}
    )
    r = client.delete(f"/api/goals/{top['id']}")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "GOAL_HAS_CHILDREN"


def test_project_crud_with_tasks(client):
    p = client.post(
        "/api/projects",
        json={
            "name": "SPM Practical Submission",
            "area": "COLLEGE",
            "deadline": "2026-09-01T18:00:00",
        },
    )
    assert p.status_code == 201
    project = p.json()

    t = client.post(
        "/api/tasks",
        json={"title": "Practical 1", "area": "COLLEGE", "project_id": project["id"]},
    )
    assert t.status_code == 201

    got = client.get(f"/api/projects/{project['id']}")
    assert got.status_code == 200

    tasks = client.get("/api/tasks", params={"project_id": project["id"]}).json()
    assert [x["title"] for x in tasks] == ["Practical 1"]
