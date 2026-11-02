"""Tests for Milestone H: Remote Workspace Management, Remote Companion, and Git Safety."""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.models.remote_workspace import RemoteWorkspace
from app.models.user import User
from remote_companion.main import (
    PROTECTED_BRANCHES,
    app as companion_app,
    redact_secrets,
    run_git_safe,
)


@pytest.fixture
def companion_client():
    return TestClient(companion_app)


@pytest.fixture
def test_user(db):
    u = db.query(User).filter_by(id=1).first()
    if not u:
        u = User(id=1, email="testuser@iris.dev", name="Test User")
        db.add(u)
        db.commit()
    return u


def test_secret_redaction():
    """Ensure tokens, PATs, and credentials are completely redacted."""
    raw = (
        "Fatal: clone failed for https://x-access-token:ghp_1234567890abcdef1234567890abcdef@github.com/org/repo\n"
        "Config auth: Bearer my-super-secret-companion-token-123456"
    )
    scrubbed = redact_secrets(raw)
    assert "ghp_1234567890abcdef1234567890abcdef" not in scrubbed
    assert "my-super-secret-companion-token-123456" not in scrubbed
    assert "https://x-access-token:***@github.com" in scrubbed
    assert "Bearer ***" in scrubbed


def test_companion_health_endpoint(companion_client):
    """Verify companion health probe reports git and Antigravity."""
    resp = companion_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "git" in data
    assert "antigravity" in data


def test_companion_auth_enforcement(companion_client):
    """Verify unauthorized requests are rejected."""
    resp = companion_client.post("/api/workspaces/provision", json={"workspace_id": "ws-1", "repo_url": "https://github.com/test/repo"})
    assert resp.status_code == 401


def test_companion_workspace_lifecycle_and_git_safety(companion_client, tmp_path: Path, monkeypatch):
    """Test provisioning, checkpointing patch, restoring, committing, and protected branch push rejection."""
    import remote_companion.main as cm
    monkeypatch.setattr(cm, "WORKSPACES_ROOT", tmp_path / "workspaces")
    auth_header = {"Authorization": "Bearer dev-secret-token"}

    # 1. Setup a real local bare git repo to act as remote origin
    remote_origin = tmp_path / "origin.git"
    remote_origin.mkdir()
    subprocess_run = cm.subprocess.run
    subprocess_run(["git", "init", "--bare", "-b", "main", str(remote_origin)], check=True)

    # Push initial commit to bare repo via seed
    seed = tmp_path / "seed"
    seed.mkdir()
    subprocess_run(["git", "init", "-b", "main", str(seed)], check=True)
    subprocess_run(["git", "config", "user.name", "Tester"], cwd=seed, check=True)
    subprocess_run(["git", "config", "user.email", "test@iris.dev"], cwd=seed, check=True)
    (seed / "README.md").write_text("# Project\nInitial content\n", encoding="utf-8")
    subprocess_run(["git", "add", "."], cwd=seed, check=True)
    subprocess_run(["git", "commit", "-m", "Initial commit"], cwd=seed, check=True)
    subprocess_run(["git", "remote", "add", "origin", str(remote_origin)], cwd=seed, check=True)
    subprocess_run(["git", "push", "origin", "main"], cwd=seed, check=True)

    # 2. Provision workspace in companion
    ws_id = "test-ws-milestone-h"
    prov_resp = companion_client.post(
        "/api/workspaces/provision",
        headers=auth_header,
        json={"workspace_id": ws_id, "repo_url": str(remote_origin), "branch": "main"},
    )
    assert prov_resp.status_code == 200
    prov_data = prov_resp.json()
    assert prov_data["workspace_id"] == ws_id
    assert prov_data["base_commit_sha"] is not None

    ws_dir = tmp_path / "workspaces" / ws_id
    assert ws_dir.is_dir()
    assert (ws_dir / "README.md").exists()

    # 3. Simulate code change by agent
    new_code = ws_dir / "app.py"
    new_code.write_text("print('hello remote')", encoding="utf-8")

    # 4. Capture diff
    diff_resp = companion_client.get(f"/api/workspaces/{ws_id}/diff", headers=auth_header)
    assert diff_resp.status_code == 200
    diff_data = diff_resp.json()
    assert diff_data["total_files"] == 1
    assert diff_data["changed_files"][0]["path"] == "app.py"

    # 5. Checkpoint uncommitted patch
    cp_resp = companion_client.post(f"/api/workspaces/{ws_id}/checkpoint", headers=auth_header)
    assert cp_resp.status_code == 200
    cp_data = cp_resp.json()
    assert cp_data["has_uncommitted_changes"] is True
    patch_str = cp_data["patch"]
    assert "app.py" in patch_str

    # 6. Discard local changes and restore from patch
    new_code.unlink()
    assert not new_code.exists()

    rest_resp = companion_client.post(
        f"/api/workspaces/{ws_id}/restore",
        headers=auth_header,
        json={"branch": "main", "patch": patch_str},
    )
    assert rest_resp.status_code == 200
    assert new_code.exists()
    assert "hello remote" in new_code.read_text(encoding="utf-8")

    # 7. Commit changes on task branch
    task_branch = "iris/task/h001-feature"
    subprocess_run(["git", "checkout", "-b", task_branch], cwd=ws_dir, check=True)

    commit_resp = companion_client.post(
        f"/api/workspaces/{ws_id}/commit",
        headers=auth_header,
        json={"message": "feat: add app.py", "author_name": "Antigravity Coworker", "author_email": "coworker@iris.dev"},
    )
    assert commit_resp.status_code == 200
    commit_data = commit_resp.json()
    assert commit_data["committed"] is True
    assert commit_data["commit_sha"] is not None

    # 8. Git Safety Rule: Protected branch push MUST be rejected with 403
    push_prot_resp = companion_client.post(
        f"/api/workspaces/{ws_id}/push",
        headers=auth_header,
        json={"branch": "main", "github_pat": "fake-token"},
    )
    assert push_prot_resp.status_code == 403
    assert "protected branch" in push_prot_resp.json()["detail"]

    # 9. Push to task branch succeeds
    push_task_resp = companion_client.post(
        f"/api/workspaces/{ws_id}/push",
        headers=auth_header,
        json={"branch": task_branch, "github_pat": "fake-token"},
    )
    assert push_task_resp.status_code == 200
    assert push_task_resp.json()["pushed"] is True


def test_iris_remote_workspace_model_persistence(test_user, db):
    """Verify RemoteWorkspace database persistence and relationships."""
    ws = RemoteWorkspace(
        id="ws-uuid-999",
        user_id=test_user.id,
        name="Test Cloud Workspace",
        repo_url="https://github.com/org/sample-repo",
        branch="main",
        task_branch="iris/task/abc-feat",
        status="idle",
        storage_type="git_backed",
        engine_name="antigravity",
    )
    db.add(ws)
    db.commit()

    saved = db.query(RemoteWorkspace).filter_by(id="ws-uuid-999").first()
    assert saved is not None
    assert saved.name == "Test Cloud Workspace"
    assert saved.branch == "main"
    assert saved.storage_type == "git_backed"


def test_iris_workspaces_api_routes(client, test_user):
    """Test /api/workspaces listing and creation."""
    # List workspaces
    resp = client.get("/api/workspaces")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # Create workspace
    create_resp = client.post(
        "/api/workspaces",
        json={
            "name": "Cloud Test Workspace",
            "repo_url": "https://github.com/KIRTAN0902/IRIS.git",
            "branch": "main",
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["id"] is not None
    assert created["repo_url"] == "https://github.com/KIRTAN0902/IRIS.git"
    assert created["status"] in ("idle", "provisioning")

    # Get single workspace
    get_resp = client.get(f"/api/workspaces/{created['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["workspace"]["id"] == created["id"]
