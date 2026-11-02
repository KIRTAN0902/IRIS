"""Tests for multi-agent adapter registry, isolated worktree workflow, and push protection."""
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest

from app.coding.antigravity import coding_agents
from app.coding.adapters.codex_adapter import CodexCLIAdapter
from app.coding.git_workspace import (
    GitIsolationError,
    create_isolated_worktree,
    inspect_git_state,
    push_task_branch,
    validate_push_permission,
)
from app.models.coding_task import CodingTaskRecord, CodingSessionRecord


@pytest.fixture
def temp_git_project(client, tmp_path):
    repo_dir = tmp_path / "my_project"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Dev"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "dev@iris.local"], cwd=str(repo_dir), check=True)

    readme = repo_dir / "README.md"
    readme.write_text("# My Project\nExisting architecture details.\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True)

    project = client.post(
        "/api/coding/projects",
        json={"name": "My Project", "directory": str(repo_dir), "aliases": ["my-project"]},
    )
    assert project.status_code == 201
    pid = project.json()["id"]
    client.patch(f"/api/coding/projects/{pid}", json={"write_access": True, "command_access": True})
    return {"id": pid, "dir": repo_dir}


def test_agent_registry_discovers_both_engines():
    discovered = coding_agents.discover()
    ids = [a["id"] for a in discovered]
    assert "antigravity-cli" in ids
    assert "codex-cli" in ids

    codex = coding_agents.get("codex-cli")
    assert codex is not None
    assert codex.agent_id == "codex-cli"
    det = codex.detect()
    assert "capabilities" in det
    assert det["capabilities"]["streaming_output"] is True


def test_create_and_approve_task_with_codex_cli_uses_isolated_worktree(client, db, temp_git_project, monkeypatch):
    pid = temp_git_project["id"]
    repo_dir = temp_git_project["dir"]

    # Mock codex launch
    launched_dirs = []

    class MockCodexAdapter:
        agent_id = "codex-cli"
        def detect(self):
            return {"id": "codex-cli", "name": "Codex CLI", "available": True}
        def launch(self, directory, prompt, session_id, permissions=None):
            launched_dirs.append(directory)
            return SimpleNamespace(key="mock-codex-session")

    monkeypatch.setattr(coding_agents, "_adapters", {
        **coding_agents._adapters,
        "codex-cli": MockCodexAdapter(),
    })

    brief = {
        "objective": "Add payment gateway",
        "project_id": pid,
        "agent_id": "codex-cli",
        "acceptance_criteria": ["Payment route active"],
    }
    create_res = client.post(
        "/api/coding/execution/tasks",
        json={
            "project_id": pid,
            "agent_id": "codex-cli",
            "instruction": "Add payment gateway",
            "brief": brief,
        },
    )
    assert create_res.status_code == 201
    task = create_res.json()
    tid = task["id"]
    assert "task_branch" in task["brief"]
    assert task["brief"]["task_branch"].startswith("iris/task/")

    # Approve task
    approve_res = client.post(
        f"/api/coding/execution/tasks/{tid}/approve",
        json={"prompt": "Implement the payment gateway in isolated branch"},
    )
    assert approve_res.status_code == 200
    approved_task = approve_res.json()
    assert approved_task["status"] == "running"

    # Verify execution directory was the isolated worktree, NOT the main repo dir!
    assert len(launched_dirs) == 1
    worktree_dir = launched_dirs[0]
    assert worktree_dir != str(repo_dir)
    assert ".iris_worktrees" in worktree_dir

    # Check worktree git state
    wt_state = inspect_git_state(worktree_dir)
    assert wt_state["is_git"] is True
    assert wt_state["branch"].startswith("iris/task/")

    # Create a file inside worktree to simulate agent work
    payment_file = Path(worktree_dir) / "payment.py"
    payment_file.write_text("def process_payment(): pass\n", encoding="utf-8")

    # Call diff endpoint
    diff_res = client.get(f"/api/coding/execution/tasks/{tid}/diff")
    assert diff_res.status_code == 200
    diff_data = diff_res.json()
    assert diff_data["isolated_worktree"] is True
    assert any(f["path"] == "payment.py" for f in diff_data["changed_files"])

    # Commit changes in worktree via endpoint
    commit_res = client.post(
        f"/api/coding/execution/tasks/{tid}/commit",
        json={"message": "Implement payment service"},
    )
    assert commit_res.status_code == 200
    commit_data = commit_res.json()
    assert len(commit_data["commit_hash"]) > 10

    # Cleanup worktree
    cleanup_res = client.post(f"/api/coding/execution/tasks/{tid}/cleanup", params={"delete_branch": False})
    assert cleanup_res.status_code == 200
    assert cleanup_res.json()["cleaned"] is True
    assert not Path(worktree_dir).exists()


def test_push_endpoint_strictly_blocks_protected_branches(client, db, temp_git_project):
    pid = temp_git_project["id"]
    repo_dir = temp_git_project["dir"]

    # If someone tries to push with main or master branch name, it must be rejected with 403
    with pytest.raises(GitIsolationError, match="Push denied: Branch 'main' is a protected branch"):
        validate_push_permission("main")

    with pytest.raises(GitIsolationError, match="Push denied: Branch 'master' is a protected branch"):
        validate_push_permission("master")

    # Original branch must be rejected
    with pytest.raises(GitIsolationError, match="matches the user's original working branch"):
        validate_push_permission("my-feature", original_branch="my-feature")
