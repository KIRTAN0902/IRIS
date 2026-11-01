from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ExecutionProviderUnavailableError
from app.core.execution_provider import get_execution_provider, require_execution


@pytest.mark.parametrize("kind", ["coworker", "coding_agent", "mesh_files"])
def test_serverless_runtime_does_not_claim_local_execution(monkeypatch, kind):
    monkeypatch.setenv("VERCEL", "1")

    status = get_execution_provider().status(kind)

    assert status.available is False
    assert status.provider == "unavailable"
    assert "persistent" in (status.reason or "").lower()


def test_require_execution_raises_actionable_provider_error(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")

    with pytest.raises(ExecutionProviderUnavailableError) as caught:
        require_execution("coworker")

    assert caught.value.code == "EXECUTION_PROVIDER_UNAVAILABLE"


def test_local_persistent_host_keeps_existing_execution_provider(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.delenv("SERVERLESS", raising=False)

    assert get_execution_provider().status("coworker").available is True


def test_vercel_lifespan_skips_process_local_startup(monkeypatch, db):
    monkeypatch.setenv("VERCEL", "1")

    from app.core import database
    from app.main import app

    def forbidden_database_session():
        raise AssertionError("Vercel lifespan must not perform startup database recovery")

    monkeypatch.setattr(database, "SessionLocal", forbidden_database_session)
    with TestClient(app) as client:
        response = client.get("/health")
        rejected = client.get("/api/tasks")

    assert response.status_code == 200
    assert response.json()["database"] == "unconfigured_or_unreachable"
    assert rejected.status_code == 503
    assert rejected.json()["error"]["code"] == "DATABASE_CONFIGURATION_REQUIRED"


def test_development_cors_allows_known_origin_and_rejects_arbitrary_origin(client):
    allowed = client.get("/health", headers={"Origin": "http://localhost:5173"})
    denied = client.get("/health", headers={"Origin": "https://untrusted.example"})

    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert denied.headers.get("access-control-allow-origin") is None


def test_serverless_coworker_auto_run_is_rejected_before_task_creation(client, db, monkeypatch):
    from app.core import database
    from app.models.coworker import CoworkerTask

    coworker = client.post("/api/coworkers", json={
        "name": "Deployment Worker",
        "role": "Researcher",
        "allowed_capabilities": ["search_memory"],
    })
    assert coworker.status_code == 201

    monkeypatch.setenv("VERCEL", "1")
    # Simulate the required persistent Postgres availability while preserving
    # this test's isolated SQLite engine.
    monkeypatch.setattr(database, "is_persistent_database_configured", lambda: True)
    before = db.query(CoworkerTask).count()
    response = client.post(f"/api/coworkers/{coworker.json()['id']}/tasks", json={
        "instruction": "Run a bounded deployment test",
        "required_capabilities": [],
        "run": True,
    })

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EXECUTION_PROVIDER_UNAVAILABLE"
    assert db.query(CoworkerTask).count() == before


def test_serverless_agy_process_controls_are_unavailable(client, monkeypatch):
    from app.core import database

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(database, "is_persistent_database_configured", lambda: True)
    response = client.get("/api/agy/sessions")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EXECUTION_PROVIDER_UNAVAILABLE"


def test_serverless_coding_session_does_not_reclassify_host_task(client, monkeypatch):
    from app.core import database

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(database, "is_persistent_database_configured", lambda: True)
    response = client.get("/api/coding/execution/tasks/not-local/session")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EXECUTION_PROVIDER_UNAVAILABLE"
