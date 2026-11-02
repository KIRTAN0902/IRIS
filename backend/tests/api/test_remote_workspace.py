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


def test_companion_readiness_probe(companion_client):
    """Verify companion readiness probe checks git and writable workspace root."""
    resp = companion_client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is True
    assert data["storage_writable"] is True
    assert data["git"] is True


def test_companion_production_secret_enforcement(companion_client, monkeypatch):
    """Verify that insecure secrets fail closed when running in production."""
    import remote_companion.main as cm

    monkeypatch.setattr(cm, "is_production_environment", lambda: True)
    monkeypatch.setattr(cm, "COMPANION_SECRET", "dev-secret-token")

    # In production with default secret, any authorized endpoint raises 500
    resp = companion_client.post(
        "/api/workspaces/provision",
        headers={"Authorization": "Bearer dev-secret-token"},
        json={"workspace_id": "ws-sec", "repo_url": "https://github.com/test/repo"},
    )
    assert resp.status_code == 500
    assert "Insecure companion secret" in resp.json()["detail"]


def test_companion_concurrency_lock(companion_client, tmp_path: Path, monkeypatch):
    """Verify executing when a task is already running in workspace returns 409 Conflict."""
    import subprocess
    import sys
    import remote_companion.main as cm

    monkeypatch.setattr(cm, "WORKSPACES_ROOT", tmp_path / "workspaces")
    ws_id = "ws-concurrent-test"
    ws_dir = tmp_path / "workspaces" / ws_id
    ws_dir.mkdir(parents=True, exist_ok=True)

    auth_header = {"Authorization": "Bearer dev-secret-token"}

    # Mock an active running process in the workspace
    dummy_proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    try:
        cm.ACTIVE_PROCESSES[ws_id] = dummy_proc

        resp = companion_client.post(
            f"/api/workspaces/{ws_id}/execute",
            headers=auth_header,
            json={
                "task_id": "task-dup",
                "prompt": "do something",
                "task_branch": "iris/task/dup",
            },
        )
        assert resp.status_code == 409
        assert "already actively executing" in resp.json()["detail"]
    finally:
        cm.kill_process_tree(dummy_proc)
        cm.ACTIVE_PROCESSES.pop(ws_id, None)


def test_companion_git_pat_sanitized_from_disk(companion_client, tmp_path: Path, monkeypatch):
    """Verify that GitHub PAT is never saved to .git/config on disk after cloning."""
    import remote_companion.main as cm

    monkeypatch.setattr(cm, "WORKSPACES_ROOT", tmp_path / "workspaces")
    auth_header = {"Authorization": "Bearer dev-secret-token"}

    # Create a bare repo
    bare_repo = tmp_path / "origin.git"
    bare_repo.mkdir()
    cm.subprocess.run(["git", "init", "--bare", "-b", "main", str(bare_repo)], check=True)

    seed = tmp_path / "seed"
    seed.mkdir()
    cm.subprocess.run(["git", "init", "-b", "main", str(seed)], check=True)
    cm.subprocess.run(["git", "config", "user.name", "Tester"], cwd=seed, check=True)
    cm.subprocess.run(["git", "config", "user.email", "test@iris.dev"], cwd=seed, check=True)
    (seed / "test.txt").write_text("ok", encoding="utf-8")
    cm.subprocess.run(["git", "add", "."], cwd=seed, check=True)
    cm.subprocess.run(["git", "commit", "-m", "init"], cwd=seed, check=True)
    cm.subprocess.run(["git", "remote", "add", "origin", str(bare_repo)], cwd=seed, check=True)
    cm.subprocess.run(["git", "push", "origin", "main"], cwd=seed, check=True)

    fake_pat = "ghp_SECRET_PAT_9876543210zyxwvutsrqponmlkjihgfedcba"
    ws_id = "ws-pat-test"

    # Provision workspace using repo_url and fake_pat
    # We use file:// URL format where PAT substitution applies or normal clone
    # Note: simulate https url with PAT
    cloned_dir = tmp_path / "workspaces" / ws_id

    # Test the PAT reset logic by provisioning
    prov_resp = companion_client.post(
        "/api/workspaces/provision",
        headers=auth_header,
        json={"workspace_id": ws_id, "repo_url": str(bare_repo), "branch": "main", "github_pat": fake_pat},
    )
    assert prov_resp.status_code == 200

    # Read .git/config directly from disk
    git_config_path = cloned_dir / ".git" / "config"
    assert git_config_path.exists()
    config_content = git_config_path.read_text(encoding="utf-8")
    assert fake_pat not in config_content
    assert "x-access-token" not in config_content


def test_companion_checkpoint_hash_and_dry_run_restore(companion_client, tmp_path: Path, monkeypatch):
    """Verify SHA-256 hash calculation on checkpoint and dry-run check on restore."""
    import hashlib
    import remote_companion.main as cm

    monkeypatch.setattr(cm, "WORKSPACES_ROOT", tmp_path / "workspaces")
    auth_header = {"Authorization": "Bearer dev-secret-token"}

    # Setup repo
    remote_origin = tmp_path / "hash_origin.git"
    remote_origin.mkdir()
    cm.subprocess.run(["git", "init", "--bare", "-b", "main", str(remote_origin)], check=True)

    seed = tmp_path / "seed_hash"
    seed.mkdir()
    cm.subprocess.run(["git", "init", "-b", "main", str(seed)], check=True)
    cm.subprocess.run(["git", "config", "user.name", "Tester"], cwd=seed, check=True)
    cm.subprocess.run(["git", "config", "user.email", "test@iris.dev"], cwd=seed, check=True)
    (seed / "hello.txt").write_text("original text\n", encoding="utf-8")
    cm.subprocess.run(["git", "add", "."], cwd=seed, check=True)
    cm.subprocess.run(["git", "commit", "-m", "init"], cwd=seed, check=True)
    cm.subprocess.run(["git", "remote", "add", "origin", str(remote_origin)], cwd=seed, check=True)
    cm.subprocess.run(["git", "push", "origin", "main"], cwd=seed, check=True)

    ws_id = "ws-hash-test"
    companion_client.post(
        "/api/workspaces/provision",
        headers=auth_header,
        json={"workspace_id": ws_id, "repo_url": str(remote_origin), "branch": "main"},
    )
    ws_dir = tmp_path / "workspaces" / ws_id

    # Modify file
    (ws_dir / "hello.txt").write_text("modified text\n", encoding="utf-8")

    # Checkpoint
    cp_resp = companion_client.post(f"/api/workspaces/{ws_id}/checkpoint", headers=auth_header)
    assert cp_resp.status_code == 200
    cp_data = cp_resp.json()
    assert cp_data["has_uncommitted_changes"] is True
    assert cp_data["patch_hash"] is not None
    expected_hash = hashlib.sha256(cp_data["patch"].encode("utf-8")).hexdigest()
    assert cp_data["patch_hash"] == expected_hash

    # Reset workspace to clean
    cm.subprocess.run(["git", "checkout", "hello.txt"], cwd=ws_dir, check=True)

    # 1. Restore with mismatched hash fails with 422
    bad_hash_resp = companion_client.post(
        f"/api/workspaces/{ws_id}/restore",
        headers=auth_header,
        json={"branch": "main", "patch": cp_data["patch"], "expected_hash": "wrong-hash-12345"},
    )
    assert bad_hash_resp.status_code == 422
    assert "Patch integrity check failed" in bad_hash_resp.json()["detail"]

    # 2. Restore with corrupted patch that cannot apply cleanly fails with 422 dry-run error
    corrupted_patch = cp_data["patch"].replace("original text", "nonexistent context line")
    corrupt_resp = companion_client.post(
        f"/api/workspaces/{ws_id}/restore",
        headers=auth_header,
        json={"branch": "main", "patch": corrupted_patch},
    )
    assert corrupt_resp.status_code == 422
    assert "Patch dry-run failed" in corrupt_resp.json()["detail"]

    # 3. Restore with correct patch succeeds
    good_resp = companion_client.post(
        f"/api/workspaces/{ws_id}/restore",
        headers=auth_header,
        json={"branch": "main", "patch": cp_data["patch"], "expected_hash": expected_hash},
    )
    assert good_resp.status_code == 200
    assert (ws_dir / "hello.txt").read_text(encoding="utf-8") == "modified text\n"


def test_kill_process_tree():
    """Verify cross-platform process tree termination."""
    import subprocess
    import sys
    import time
    from remote_companion.main import kill_process_tree

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    assert proc.poll() is None
    kill_process_tree(proc)
    time.sleep(0.5)
    assert proc.poll() is not None


def test_iris_checkpoint_and_recover_api(client, test_user, db):
    """Test IRIS Core durable checkpoint version incrementing and recovery."""
    ws = RemoteWorkspace(
        id="ws-core-cp-test",
        user_id=test_user.id,
        name="Checkpoint Test WS",
        repo_url="https://github.com/org/repo",
        branch="main",
        status="idle",
    )
    db.add(ws)
    db.commit()

    # Mock companion client checkpoint and restore
    with patch("app.api.routes.remote_workspaces._get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.checkpoint.return_value = {
            "current_commit_sha": "sha-abc-123",
            "patch": "diff --git a/test.py b/test.py\n+hello",
            "patch_hash": "sha256-hash-999",
        }
        mock_client.provision_workspace.return_value = {"base_commit_sha": "sha-abc-123"}
        mock_client.restore.return_value = {"restored": True}
        mock_get_client.return_value = mock_client

        # Call checkpoint
        cp_resp = client.post(f"/api/workspaces/{ws.id}/checkpoint")
        assert cp_resp.status_code == 200
        cp_data = cp_resp.json()
        assert cp_data["checkpointed"] is True
        assert cp_data["checkpoint_version"] == 1
        assert cp_data["checkpoint_hash"] == "sha256-hash-999"

        # Check DB state
        db.refresh(ws)
        assert ws.checkpoint_version == 1
        assert ws.checkpoint_hash == "sha256-hash-999"
        assert ws.uncommitted_patch == "diff --git a/test.py b/test.py\n+hello"
        assert ws.checkpoint_at is not None

        # Checkpoint again to verify version increments and previous_patch is saved
        mock_client.checkpoint.return_value = {
            "current_commit_sha": "sha-abc-123",
            "patch": "diff --git a/test.py b/test.py\n+hello v2",
            "patch_hash": "sha256-hash-1000",
        }
        cp_resp2 = client.post(f"/api/workspaces/{ws.id}/checkpoint")
        assert cp_resp2.status_code == 200
        assert cp_resp2.json()["checkpoint_version"] == 2

        db.refresh(ws)
        assert ws.checkpoint_version == 2
        assert ws.previous_patch == "diff --git a/test.py b/test.py\n+hello"
        assert ws.uncommitted_patch == "diff --git a/test.py b/test.py\n+hello v2"

        # Recover
        rec_resp = client.post(f"/api/workspaces/{ws.id}/recover")
        assert rec_resp.status_code == 200
        assert rec_resp.json()["recovered"] is True
        mock_client.restore.assert_called_once_with(
            workspace_id=ws.id,
            branch=ws.branch,
            patch=ws.uncommitted_patch,
            expected_hash=ws.checkpoint_hash,
        )

