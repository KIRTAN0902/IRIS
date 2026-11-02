"""Tests for Git worktree isolation and branch protections."""
import os
import shutil
import subprocess
from pathlib import Path
import pytest

from app.coding.git_workspace import (
    GitIsolationError,
    cleanup_isolated_worktree,
    collect_worktree_diff,
    commit_worktree_changes,
    create_isolated_worktree,
    inspect_git_state,
    make_task_branch_name,
    push_task_branch,
    validate_push_permission,
)


@pytest.fixture
def temp_git_repo(tmp_path):
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "test@iris.local"], cwd=str(repo_dir), check=True)

    readme = repo_dir / "README.md"
    readme.write_text("# Test Repo\nInitial content\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True)
    return repo_dir


def test_make_task_branch_name():
    branch = make_task_branch_name("8f31a1b2-1234-5678-90ab", "Add notification system")
    assert branch == "iris/task/8f31a1b2-add-notification-system"


def test_inspect_git_state(temp_git_repo):
    state = inspect_git_state(temp_git_repo)
    assert state["is_git"] is True
    assert state["branch"] == "main"
    assert state["has_uncommitted_changes"] is False
    assert len(state["head_commit"]) > 10


def test_create_isolated_worktree_preserves_uncommitted_changes(temp_git_repo):
    # Create uncommitted change in the parent repository
    readme = temp_git_repo / "README.md"
    readme.write_text("# Test Repo\nUser uncommitted edit!\n", encoding="utf-8")

    state_before = inspect_git_state(temp_git_repo)
    assert state_before["has_uncommitted_changes"] is True

    # Create worktree
    ws = create_isolated_worktree(
        project_id=1,
        project_dir=temp_git_repo,
        task_id="abc12345-0000",
        description="Feature in worktree",
    )

    assert ws.is_created is True
    assert ws.task_branch == "iris/task/abc12345-feature-in-worktree"
    assert ws.has_uncommitted_parent_changes is True
    assert Path(ws.worktree_dir).is_dir()

    # Verify that the parent repository's uncommitted change is STILL there
    state_after = inspect_git_state(temp_git_repo)
    assert state_after["has_uncommitted_changes"] is True
    assert readme.read_text(encoding="utf-8") == "# Test Repo\nUser uncommitted edit!\n"

    # Verify that the worktree has the clean base commit version
    wt_readme = Path(ws.worktree_dir) / "README.md"
    assert wt_readme.read_text(encoding="utf-8") == "# Test Repo\nInitial content\n"

    # Make an edit inside the worktree
    new_file = Path(ws.worktree_dir) / "feature.txt"
    new_file.write_text("Hello from worktree\n", encoding="utf-8")

    # Collect diff
    diff = collect_worktree_diff(ws.worktree_dir, ws.base_commit)
    assert diff["total_files"] == 1
    assert diff["has_uncommitted_changes"] is True

    # Commit changes in worktree
    new_commit = commit_worktree_changes(ws.worktree_dir, "Add feature in worktree")
    assert new_commit != ws.base_commit

    diff_after_commit = collect_worktree_diff(ws.worktree_dir, ws.base_commit)
    assert diff_after_commit["current_commit"] == new_commit
    assert any(f["path"] == "feature.txt" for f in diff_after_commit["changed_files"])

    # Clean up worktree
    cleaned = cleanup_isolated_worktree(temp_git_repo, ws.worktree_dir, delete_branch=True)
    assert cleaned is True
    assert not Path(ws.worktree_dir).exists()


def test_validate_push_permission():
    # Protected branches must be rejected
    with pytest.raises(GitIsolationError, match="Push denied: Branch 'main' is a protected branch"):
        validate_push_permission("main")

    with pytest.raises(GitIsolationError, match="Push denied: Branch 'master' is a protected branch"):
        validate_push_permission("master")

    # Original branch must be rejected
    with pytest.raises(GitIsolationError, match="matches the user's original working branch"):
        validate_push_permission("my-feature", original_branch="my-feature")

    # Non-iris/task/ branch must be rejected
    with pytest.raises(GitIsolationError, match="does not match the mandated task branch format"):
        validate_push_permission("random-branch")

    # Valid task branch must pass
    validate_push_permission("iris/task/12345678-test-branch", original_branch="main")
