from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings


@pytest.fixture()
def api(db: Session, monkeypatch, tmp_path):
    """Test client with the background worker disabled for deterministic tests."""
    monkeypatch.setattr(settings, "knowledge_worker_enabled", False)
    from app.knowledge import markdown_sync as markdown_module
    from app.knowledge.storage import LocalVaultStorage

    monkeypatch.setattr(
        markdown_module.markdown_sync,
        "_storage",
        LocalVaultStorage(root=tmp_path / "vault"),
    )
    from app.main import app

    with TestClient(app) as client:
        yield client


def _create_node(api, name: str = "IRIS", node_type: str = "project"):
    response = api.post(
        "/api/knowledge/nodes", json={"name": name, "node_type": node_type}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_health_and_overview(api):
    health = api.get("/api/knowledge/health")
    assert health.status_code == 200
    assert health.json()["state"] == "healthy"

    overview = api.get("/api/knowledge/overview")
    assert overview.status_code == 200
    body = overview.json()
    assert "recent_nodes" in body
    assert "totals" in body


def test_node_claim_lifecycle_and_search(api):
    node = _create_node(api)
    assert node["canonical_name"] == "IRIS"

    claim_response = api.post(
        "/api/knowledge/claims",
        json={
            "node_id": node["id"],
            "text": "IRIS uses FastAPI for its backend.",
            "claim_type": "fact",
            "verification_status": "user_stated",
            "category": "projects",
        },
    )
    assert claim_response.status_code == 201, claim_response.text
    claim = claim_response.json()
    assert claim["node_id"] == node["id"]

    listed = api.get("/api/knowledge/claims", params={"node_id": node["id"]})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [claim["id"]]

    detail = api.get(f"/api/knowledge/claims/{claim['id']}")
    assert detail.status_code == 200
    assert detail.json()["claim_text"].startswith("IRIS uses FastAPI")

    search = api.post(
        "/api/knowledge/search", json={"query": "FastAPI backend", "limit": 5}
    )
    assert search.status_code == 200
    body = search.json()
    assert body["count"] >= 1
    assert body["results"][0]["claim_id"] == claim["id"]

    updated = api.patch(
        f"/api/knowledge/claims/{claim['id']}",
        json={"verification_status": "verified", "confidence": 0.95},
    )
    assert updated.status_code == 200
    assert updated.json()["verification_status"] == "verified"

    archived = api.post(f"/api/knowledge/claims/{claim['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None

    current = api.get("/api/knowledge/claims", params={"node_id": node["id"]})
    assert current.status_code == 200
    assert current.json() == []


def test_node_graph_and_history(api):
    first = _create_node(api, "IRIS", "project")
    second = _create_node(api, "FastAPI", "technology")
    api.post(
        "/api/knowledge/claims",
        json={"node_id": first["id"], "text": "IRIS uses FastAPI."},
    )
    # Relationships are created through the service layer in normal flow; the
    # graph endpoint must still return the node itself for an isolated node.
    graph = api.get(f"/api/knowledge/nodes/{first['id']}/graph")
    assert graph.status_code == 200
    assert [node["id"] for node in graph.json()["nodes"]] == [first["id"]]

    history = api.get("/api/knowledge/history")
    assert history.status_code == 200
    assert isinstance(history.json(), list)

    missing = api.get("/api/knowledge/nodes/does-not-exist")
    assert missing.status_code == 404
    assert second["id"]


def test_capture_and_jobs(api):
    captured = api.post(
        "/api/knowledge/capture",
        json={
            "text": "I decided that IRIS will use PostgreSQL as its primary database.",
            "source_type": "decision",
            "process_now": True,
        },
    )
    assert captured.status_code == 202, captured.text
    body = captured.json()
    assert body["source_id"]
    assert body["job_id"]

    jobs = api.get("/api/knowledge/jobs")
    assert jobs.status_code == 200
    assert "by_status" in jobs.json()
    assert any(job["id"] == body["job_id"] for job in jobs.json()["recent"])

    drained = api.post("/api/knowledge/jobs/drain", json={"limit": 5})
    assert drained.status_code == 200
    assert "processed" in drained.json()


def test_permissions_api(api):
    node = _create_node(api, "Family notes", "person")
    granted = api.post(
        "/api/knowledge/permissions",
        json={
            "principal_type": "coworker",
            "principal_id": "developer",
            "access_level": "personal",
            "knowledge_type": "node",
            "knowledge_id": node["id"],
        },
    )
    assert granted.status_code == 201, granted.text
    assert granted.json()["knowledge_id"] == node["id"]

    listed = api.get("/api/knowledge/permissions")
    assert listed.status_code == 200
    assert any(item["id"] == granted.json()["id"] for item in listed.json())


def test_markdown_note_api(api):
    created = api.post(
        "/api/knowledge/notes",
        json={"title": "Reading list", "content": "Atomic Habits", "category": "learning"},
    )
    assert created.status_code == 201, created.text
    note = created.json()
    assert note["storage_path"].startswith("06-Learning/")

    detail = api.get(f"/api/knowledge/notes/{note['id']}")
    assert detail.status_code == 200
    assert "Atomic Habits" in detail.json()["content"]

    updated = api.patch(
        f"/api/knowledge/notes/{note['id']}",
        json={
            "content": detail.json()["content"] + "\nDeep Work\n",
            "expected_hash": detail.json()["content_hash"],
        },
    )
    assert updated.status_code == 200

    stale = api.patch(
        f"/api/knowledge/notes/{note['id']}",
        json={
            "content": "stale overwrite",
            "expected_hash": detail.json()["content_hash"],
        },
    )
    assert stale.status_code == 409

    deleted = api.delete(f"/api/knowledge/notes/{note['id']}")
    assert deleted.status_code == 204


def test_memory_migration_endpoint_is_non_destructive(api, db: Session, user_id: int):
    from app.models.ai_memory import AIMemory

    memory = AIMemory(
        user_id=user_id,
        category="FACT",
        key="primary_database",
        content="The primary database is PostgreSQL.",
        importance=0.8,
        confidence=0.9,
        source="USER_EXPLICIT",
        is_active=True,
    )
    db.add(memory)
    db.commit()

    dry = api.post("/api/knowledge/migrate-memory", json={"dry_run": True})
    assert dry.status_code == 200
    assert dry.json()["would_migrate"] == 1

    real = api.post("/api/knowledge/migrate-memory", json={"dry_run": False})
    assert real.status_code == 200
    assert real.json()["migrated"] == 1

    db.refresh(memory)
    assert memory.content == "The primary database is PostgreSQL."
    assert memory.is_active is True


def test_relationships_and_graph_api(api):
    node1 = _create_node(api, name="IRIS Core", node_type="project")
    node2 = _create_node(api, name="PostgreSQL", node_type="technology")

    # Create relationship
    rel_res = api.post(
        "/api/knowledge/relationships",
        json={
            "source_node_id": node1["id"],
            "target_node_id": node2["id"],
            "relationship_type": "USES",
            "confidence": 0.95,
        },
    )
    assert rel_res.status_code == 201
    rel = rel_res.json()
    assert rel["relationship_type"] == "USES"

    # List relationships
    list_res = api.get("/api/knowledge/relationships", params={"relationship_type": "USES"})
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # Global / progressive graph query
    graph_res = api.get("/api/knowledge/graph")
    assert graph_res.status_code == 200
    graph_data = graph_res.json()
    assert len(graph_data["nodes"]) >= 2
    assert len(graph_data["relationships"]) >= 1

    # Delete relationship
    del_res = api.delete(f"/api/knowledge/relationships/{rel['id']}")
    assert del_res.status_code == 204


def test_export_and_import_api(api):
    _create_node(api, name="Obsidian Export Project", node_type="project")

    # Export
    export_res = api.get("/api/knowledge/export")
    assert export_res.status_code == 200
    export_data = export_res.json()
    assert "nodes" in export_data
    assert "counts" in export_data
    assert export_data["counts"]["nodes"] >= 1

    # Import
    import_res = api.post(
        "/api/knowledge/import",
        json={
            "path": "02-Projects/test-import.md",
            "content": "---\nid: test_import\ntitle: Test Import\ntype: project\n---\n# Test Import\n\n- **Fact** (verified): Test import assertion.\n",
        },
    )
    assert import_res.status_code == 200
    assert import_res.json()["note_id"] is not None
    assert import_res.json()["changed"] is True
