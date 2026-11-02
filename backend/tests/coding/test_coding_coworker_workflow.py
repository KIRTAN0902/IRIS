"""End-to-end integration test for the Coding Coworker workflow."""
import subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest

from app.models.coding_project import CodingProject
from app.models.coworker import Coworker, CoworkerTask
from app.coding.antigravity import coding_agents


@pytest.fixture
def test_repo_and_coworker(client, db, tmp_path):
    repo_dir = tmp_path / "app_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Coworker User"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "coworker@iris.local"], cwd=str(repo_dir), check=True)

    readme = repo_dir / "README.md"
    readme.write_text("# App Repo\nBaseline code.\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True)

    # Register project
    proj_res = client.post(
        "/api/coding/projects",
        json={"name": "App Repo", "directory": str(repo_dir), "aliases": ["app-repo"]},
    )
    assert proj_res.status_code == 201
    pid = proj_res.json()["id"]
    client.patch(f"/api/coding/projects/{pid}", json={"write_access": True, "command_access": True})

    # Create Coding Coworker from template
    coworker_res = client.post("/api/coworkers?template=coding_coworker", json={
        "name": "Alex",
        "role": "Coding Coworker",
        "project_id": pid,
    })
    assert coworker_res.status_code == 201
    cid = coworker_res.json()["id"]

    return {"project_id": pid, "repo_dir": repo_dir, "coworker_id": cid}


def test_coding_coworker_creates_plan_and_isolated_worktree(client, db, test_repo_and_coworker, monkeypatch):
    cid = test_repo_and_coworker["coworker_id"]
    pid = test_repo_and_coworker["project_id"]
    repo_dir = test_repo_and_coworker["repo_dir"]

    # Assign task to Coding Coworker
    task_res = client.post(f"/api/coworkers/{cid}/tasks", json={
        "instruction": "Build user notification bell",
        "project_id": pid,
        "run": True,
    })
    assert task_res.status_code == 202
    task_data = client.get(f"/api/coworkers/{cid}").json()["tasks"][0]
    assert task_data["status"] == "waiting_input"
    assert task_data["coding_task_id"] is not None

    coding_id = task_data["coding_task_id"]
    plan = task_data["result"]
    assert plan["coding_status"] == "awaiting_approval"
    assert "iris/task/" in plan["task_branch"]

    # Mock engine launch
    launched_worktrees = []
    class MockAdapter:
        agent_id = plan["agent_id"]
        def detect(self): return {"name": "Mock Engine", "available": True}
        def launch(self, directory, prompt, session_id, permissions=None):
            launched_worktrees.append(directory)
            return SimpleNamespace(key="mock-session-123")

    monkeypatch.setattr(coding_agents, "_adapters", {
        **coding_agents._adapters,
        plan["agent_id"]: MockAdapter(),
    })

    # User approves plan
    approve_res = client.post(
        f"/api/coding/execution/tasks/{coding_id}/approve",
        json={"prompt": "Proceed with building the notification bell in the task branch"},
    )
    assert approve_res.status_code == 200
    assert len(launched_worktrees) == 1
    worktree_path = launched_worktrees[0]
    assert worktree_path != str(repo_dir)
    assert Path(worktree_path).is_dir()

    # Simulate changes inside isolated worktree
    bell_file = Path(worktree_path) / "bell.py"
    bell_file.write_text("class NotificationBell: pass\n", encoding="utf-8")

    # Verify diff through task diff endpoint
    diff_res = client.get(f"/api/coding/execution/tasks/{coding_id}/diff")
    assert diff_res.status_code == 200
    diff_data = diff_res.json()
    assert diff_data["isolated_worktree"] is True
    assert any(f["path"] == "bell.py" for f in diff_data["changed_files"])

    # Commit worktree changes
    commit_res = client.post(
        f"/api/coding/execution/tasks/{coding_id}/commit",
        json={"message": "Implement NotificationBell component"},
    )
    assert commit_res.status_code == 200

    # Clean up worktree
    clean_res = client.post(f"/api/coding/execution/tasks/{coding_id}/cleanup")
    assert clean_res.status_code == 200
    assert not Path(worktree_path).exists()


def test_coding_coworker_auto_resolves_project_or_prompts(client, db, test_repo_and_coworker):
    cid = test_repo_and_coworker["coworker_id"]

    # When instruction mentions the project alias "app-repo" without project_id
    task_res = client.post(f"/api/coworkers/{cid}/tasks", json={
        "instruction": "Fix bug in app-repo layout",
        "project_id": None,
        "run": True,
    })
    assert task_res.status_code == 202
    task_data = client.get(f"/api/coworkers/{cid}").json()["tasks"][0]
    assert task_data["status"] == "waiting_input"
    assert task_data["project_id"] == test_repo_and_coworker["project_id"]
    assert task_data["coding_task_id"] is not None
