from datetime import UTC, datetime, timedelta


def test_catalog_state_and_context_use_existing_iris_services(client):
    catalog = client.get("/api/ui-orchestrator/catalog")
    assert catalog.status_code == 200
    assert {w["id"] for w in catalog.json()["widgets"]} == {
        "priorities",
        "schedule",
        "routines",
        "coworkers",
        "progress",
    }
    state = client.get("/api/ui-orchestrator/state")
    assert state.status_code == 200 and state.json()["version"] == 1
    assert len(state.json()["layouts"]["android"]) == 5
    context = client.get("/api/ui-orchestrator/context")
    assert context.status_code == 200
    assert "active_coworker_tasks" in context.json()


def test_temporary_widget_lifecycle_requires_future_expiry(client):
    state = client.get("/api/ui-orchestrator/state").json()
    widgets = state["layouts"]["android"]
    widgets[0].update(
        {
            "lifecycle": "temporary",
            "expires_at": (datetime.now(UTC) + timedelta(hours=6)).isoformat(),
        }
    )
    good = client.put(
        "/api/ui-orchestrator/layouts/android",
        json={"expected_version": state["version"], "widgets": widgets},
    )
    assert good.status_code == 200
    assert good.json()["widgets"][0]["lifecycle"] == "temporary"
    state = client.get("/api/ui-orchestrator/state").json()
    expired = state["layouts"]["android"]
    expired[0]["expires_at"] = "2020-01-01T00:00:00+00:00"
    assert (
        client.put(
            "/api/ui-orchestrator/layouts/android",
            json={"expected_version": state["version"], "widgets": expired},
        ).status_code
        == 422
    )


def test_layout_persistence_validation_locks_and_optimistic_version(client):
    state = client.get("/api/ui-orchestrator/state").json()
    widgets = state["layouts"]["desktop"]
    widgets[0]["locked"] = True
    locked = client.put(
        "/api/ui-orchestrator/layouts/desktop", json={"expected_version": 1, "widgets": widgets}
    )
    assert locked.status_code == 200
    changed = [dict(item) for item in locked.json()["widgets"]]
    changed[0]["visible"] = False
    assert (
        client.put(
            "/api/ui-orchestrator/layouts/desktop", json={"expected_version": 2, "widgets": changed}
        ).status_code
        == 409
    )
    reordered = list(locked.json()["widgets"])
    reordered[0], reordered[1] = reordered[1], reordered[0]
    assert (
        client.put(
            "/api/ui-orchestrator/layouts/desktop",
            json={"expected_version": 2, "widgets": reordered},
        ).status_code
        == 409
    )
    assert (
        client.put(
            "/api/ui-orchestrator/layouts/desktop", json={"expected_version": 1, "widgets": widgets}
        ).status_code
        == 409
    )
    duplicate = widgets + [dict(widgets[0])]
    assert (
        client.put(
            "/api/ui-orchestrator/layouts/android",
            json={"expected_version": 2, "widgets": duplicate},
        ).status_code
        == 422
    )


def test_proposal_requires_approval_and_rollback_restores_prior_layout(client):
    state = client.get("/api/ui-orchestrator/state").json()
    widgets = state["layouts"]["android"]
    widgets[0]["visible"] = False
    proposal = client.post(
        "/api/ui-orchestrator/proposals",
        json={
            "platform": "android",
            "title": "Simplify",
            "reason": "Less on screen",
            "widgets": widgets,
        },
    )
    assert proposal.status_code == 201
    assert (
        client.get("/api/ui-orchestrator/state").json()["layouts"]["android"][0]["visible"] is True
    )
    denied = client.post(
        f"/api/ui-orchestrator/proposals/{proposal.json()['id']}/decision",
        json={"decision": "reject"},
    )
    assert denied.status_code == 200 and denied.json()["proposal"]["status"] == "rejected"
    next_state = client.get("/api/ui-orchestrator/state").json()
    saved = client.put(
        "/api/ui-orchestrator/layouts/android",
        json={"expected_version": next_state["version"], "widgets": widgets},
    )
    assert saved.status_code == 200 and saved.json()["widgets"][0]["visible"] is False
    restored = client.post("/api/ui-orchestrator/rollback")
    assert (
        restored.status_code == 200 and restored.json()["layouts"]["android"][0]["visible"] is True
    )


def test_approved_proposal_is_applied_and_preference_changes_are_versioned(client):
    state = client.get("/api/ui-orchestrator/state").json()
    widgets = state["layouts"]["desktop"]
    widgets[-1]["visible"] = False
    proposal = client.post(
        "/api/ui-orchestrator/proposals",
        json={"platform": "desktop", "title": "Quiet the dashboard", "widgets": widgets},
    ).json()
    decision = client.post(
        f"/api/ui-orchestrator/proposals/{proposal['id']}/decision", json={"decision": "approve"}
    )
    assert decision.status_code == 200 and decision.json()["proposal"]["status"] == "approved"
    state = client.get("/api/ui-orchestrator/state").json()
    assert state["layouts"]["desktop"][-1]["visible"] is False
    preference = client.put(
        "/api/ui-orchestrator/preferences",
        json={
            "expected_version": state["version"],
            "density": "compact",
            "interaction_learning": True,
            "theme": "dark",
        },
    )
    assert preference.status_code == 200
    assert preference.json()["preferences"]["interaction_learning"] is True
    assert preference.json()["preferences"]["theme"] == "dark"
    assert preference.json()["version"] == state["version"] + 1
    layout = client.get("/api/ui-orchestrator/state").json()["layouts"]["desktop"]
    layout[0], layout[1] = layout[1], layout[0]
    assert (
        client.put(
            "/api/ui-orchestrator/layouts/desktop",
            json={"expected_version": preference.json()["version"], "widgets": layout},
        ).status_code
        == 200
    )
    learned = client.get("/api/ui-orchestrator/state").json()["preferences"][
        "learned_layout_orders"
    ]
    assert learned[-1]["order"] == [item["id"] for item in layout if item["visible"]]


def test_shared_theme_preference_is_validated_and_persisted(client):
    state = client.get("/api/ui-orchestrator/state").json()
    assert state["preferences"]["theme"] == "light"
    saved = client.put(
        "/api/ui-orchestrator/preferences",
        json={"expected_version": state["version"], "theme": "system"},
    )
    assert saved.status_code == 200
    assert saved.json()["preferences"]["theme"] == "system"
    assert client.put(
        "/api/ui-orchestrator/preferences",
        json={"expected_version": saved.json()["version"], "theme": "ultraviolet"},
    ).status_code == 422


def test_capacitor_local_origin_can_call_the_backend(client):
    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://localhost",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://localhost"
