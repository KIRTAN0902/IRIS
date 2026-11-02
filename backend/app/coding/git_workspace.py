"""Isolated Git workspace and worktree management for coding tasks."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROTECTED_BRANCHES = {
    "main",
    "master",
    "develop",
    "dev",
    "trunk",
    "production",
    "staging",
    "release",
}

SLUG_CLEAN_RE = re.compile(r"[^a-z0-9_-]+")


class GitIsolationError(RuntimeError):
    """Raised when an operation violates Git workspace isolation policies."""


@dataclass
class GitWorkspaceInfo:
    project_id: int
    task_id: str
    project_dir: str
    worktree_dir: str
    original_branch: str
    base_commit: str
    task_branch: str
    has_uncommitted_parent_changes: bool
    is_created: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def _clean_slug(text: str, max_length: int = 40) -> str:
    cleaned = SLUG_CLEAN_RE.sub("-", text.strip().lower()).strip("-")
    return cleaned[:max_length] if cleaned else "task"


def make_task_branch_name(task_id: str, description: str) -> str:
    short_id = task_id.replace("-", "")[:8]
    slug = _clean_slug(description)
    return f"iris/task/{short_id}-{slug}"


def run_git(cwd: str | Path, *args: str, timeout: int = 15) -> subprocess.CompletedProcess[str]:
    git_bin = shutil.which("git")
    if not git_bin:
        raise GitIsolationError("Git binary is not available on this host.")
    try:
        proc = subprocess.run(
            [git_bin, *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc
    except subprocess.TimeoutExpired as exc:
        raise GitIsolationError(f"Git command timed out after {timeout}s: {' '.join(args)}") from exc
    except OSError as exc:
        raise GitIsolationError(f"Failed to execute git command: {exc}") from exc


def inspect_git_state(directory: str | Path) -> dict[str, Any]:
    path = Path(directory).resolve()
    if not path.is_dir():
        return {"is_git": False, "error": "Directory does not exist"}

    proc = run_git(path, "rev-parse", "--is-inside-work-tree")
    if proc.returncode != 0:
        return {"is_git": False, "error": "Not a git repository"}

    root_proc = run_git(path, "rev-parse", "--show-toplevel")
    root = root_proc.stdout.strip()

    branch_proc = run_git(path, "branch", "--show-current")
    branch = branch_proc.stdout.strip()

    commit_proc = run_git(path, "rev-parse", "HEAD")
    head_commit = commit_proc.stdout.strip() if commit_proc.returncode == 0 else ""

    status_proc = run_git(path, "status", "--porcelain")
    uncommitted = bool(status_proc.stdout.strip())

    remotes_proc = run_git(path, "remote")
    remotes = [r.strip() for r in remotes_proc.stdout.splitlines() if r.strip()]

    return {
        "is_git": True,
        "root": root,
        "branch": branch or "HEAD",
        "head_commit": head_commit,
        "has_uncommitted_changes": uncommitted,
        "remotes": remotes,
        "status_summary": status_proc.stdout[:1000],
    }


def ensure_gitignore_entry(repo_root: Path, pattern: str) -> None:
    gitignore = repo_root / ".gitignore"
    try:
        if gitignore.is_file():
            content = gitignore.read_text(encoding="utf-8", errors="replace")
            lines = [line.strip() for line in content.splitlines()]
            if pattern not in lines:
                new_content = content.rstrip() + f"\n{pattern}\n"
                gitignore.write_text(new_content, encoding="utf-8")
        else:
            gitignore.write_text(f"{pattern}\n", encoding="utf-8")
    except OSError:
        pass


def create_isolated_worktree(
    project_id: int,
    project_dir: str | Path,
    task_id: str,
    description: str,
    worktree_parent_dir: str | Path | None = None,
) -> GitWorkspaceInfo:
    project_path = Path(project_dir).resolve()
    state = inspect_git_state(project_path)
    if not state.get("is_git"):
        raise GitIsolationError(f"Cannot create isolated worktree: '{project_dir}' is not a Git repository.")

    repo_root = Path(state["root"]).resolve()
    original_branch = state["branch"]
    base_commit = state["head_commit"]

    if not base_commit:
        raise GitIsolationError("Cannot create isolated worktree: repository has no commits on HEAD.")

    task_branch = make_task_branch_name(task_id, description)

    # Determine worktree destination
    if worktree_parent_dir:
        parent = Path(worktree_parent_dir).resolve()
    else:
        parent = repo_root / ".iris_worktrees"

    parent.mkdir(parents=True, exist_ok=True)
    ensure_gitignore_entry(repo_root, ".iris_worktrees/")
    ensure_gitignore_entry(repo_root, ".iris/")

    worktree_dir = parent / f"task_{task_id.replace('-', '')[:12]}"

    # If worktree already exists, verify branch
    if worktree_dir.exists():
        wt_state = inspect_git_state(worktree_dir)
        if wt_state.get("is_git") and wt_state.get("branch") == task_branch:
            return GitWorkspaceInfo(
                project_id=project_id,
                task_id=task_id,
                project_dir=str(repo_root),
                worktree_dir=str(worktree_dir),
                original_branch=original_branch,
                base_commit=base_commit,
                task_branch=task_branch,
                has_uncommitted_parent_changes=state["has_uncommitted_changes"],
                is_created=True,
                metadata={"reused": True},
            )
        else:
            # Stale directory, remove worktree
            cleanup_isolated_worktree(repo_root, worktree_dir)

    # Check if branch already exists
    branch_check = run_git(repo_root, "rev-parse", "--verify", task_branch)
    if branch_check.returncode == 0:
        # Branch exists, attach worktree without -b
        add_proc = run_git(repo_root, "worktree", "add", str(worktree_dir), task_branch)
    else:
        # Branch does not exist, create branch from base_commit
        add_proc = run_git(repo_root, "worktree", "add", "-b", task_branch, str(worktree_dir), base_commit)

    if add_proc.returncode != 0:
        raise GitIsolationError(f"Failed to create Git worktree: {add_proc.stderr or add_proc.stdout}")

    return GitWorkspaceInfo(
        project_id=project_id,
        task_id=task_id,
        project_dir=str(repo_root),
        worktree_dir=str(worktree_dir),
        original_branch=original_branch,
        base_commit=base_commit,
        task_branch=task_branch,
        has_uncommitted_parent_changes=state["has_uncommitted_changes"],
        is_created=True,
    )


def collect_worktree_diff(worktree_dir: str | Path, base_commit: str) -> dict[str, Any]:
    wt_path = Path(worktree_dir).resolve()
    if not wt_path.is_dir():
        return {"error": "Worktree directory does not exist", "files": [], "stat": "", "diff": ""}

    # Check uncommitted changes in worktree
    status_proc = run_git(wt_path, "status", "--porcelain")
    uncommitted = [line.strip() for line in status_proc.stdout.splitlines() if line.strip()]

    # Diff stat against base commit
    stat_proc = run_git(wt_path, "diff", "--stat", base_commit)
    stat = stat_proc.stdout.strip()

    # Full diff against base commit (capped at 50,000 chars)
    diff_proc = run_git(wt_path, "diff", base_commit)
    diff = diff_proc.stdout[:50000]

    # Name-only list of changed files
    name_proc = run_git(wt_path, "diff", "--name-status", base_commit)
    changed_files = []
    for line in name_proc.stdout.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2:
            changed_files.append({"status": parts[0], "path": parts[1]})

    # Also detect newly untracked files
    for item in uncommitted:
        if item.startswith("??"):
            path = item[2:].strip()
            if not any(f["path"] == path for f in changed_files):
                changed_files.append({"status": "A", "path": path, "uncommitted": True})

    # Get latest commit in worktree
    head_proc = run_git(wt_path, "rev-parse", "HEAD")
    current_head = head_proc.stdout.strip() if head_proc.returncode == 0 else base_commit

    return {
        "base_commit": base_commit,
        "current_commit": current_head,
        "stat": stat,
        "diff": diff,
        "changed_files": changed_files,
        "has_uncommitted_changes": bool(uncommitted),
        "total_files": len(changed_files),
    }


def commit_worktree_changes(worktree_dir: str | Path, message: str) -> str:
    wt_path = Path(worktree_dir).resolve()
    status_proc = run_git(wt_path, "status", "--porcelain")
    if not status_proc.stdout.strip():
        # Nothing to commit, return current HEAD
        head_proc = run_git(wt_path, "rev-parse", "HEAD")
        return head_proc.stdout.strip()

    run_git(wt_path, "add", "-A")
    commit_proc = run_git(wt_path, "commit", "-m", message)
    if commit_proc.returncode != 0:
        raise GitIsolationError(f"Git commit failed in worktree: {commit_proc.stderr or commit_proc.stdout}")

    head_proc = run_git(wt_path, "rev-parse", "HEAD")
    return head_proc.stdout.strip()


def validate_push_permission(branch_name: str, original_branch: str | None = None) -> None:
    cleaned = branch_name.strip()
    base_name = cleaned.split("/")[-1].lower()

    if cleaned in PROTECTED_BRANCHES or base_name in PROTECTED_BRANCHES:
        raise GitIsolationError(
            f"Push denied: Branch '{branch_name}' is a protected branch. "
            f"Coding agents are forbidden from pushing directly to {', '.join(sorted(PROTECTED_BRANCHES))}."
        )

    if original_branch and cleaned == original_branch:
        raise GitIsolationError(
            f"Push denied: Branch '{branch_name}' matches the user's original working branch. "
            "Agents must never overwrite or push directly to the original branch."
        )

    if not cleaned.startswith("iris/task/"):
        raise GitIsolationError(
            f"Push denied: Branch '{branch_name}' does not match the mandated task branch format 'iris/task/<id>-<slug>'."
        )


def push_task_branch(
    worktree_dir: str | Path,
    branch_name: str,
    original_branch: str | None = None,
    remote: str = "origin",
) -> dict[str, Any]:
    wt_path = Path(worktree_dir).resolve()
    validate_push_permission(branch_name, original_branch)

    # Check worktree current branch
    state = inspect_git_state(wt_path)
    if state.get("branch") != branch_name:
        raise GitIsolationError(
            f"Worktree branch mismatch: expected '{branch_name}', but worktree is on '{state.get('branch')}'."
        )

    # Check remote existence
    if remote not in state.get("remotes", []):
        raise GitIsolationError(
            f"Remote '{remote}' is not configured in this repository. Configured remotes: {state.get('remotes')}."
        )

    push_proc = run_git(wt_path, "push", "-u", remote, branch_name)
    if push_proc.returncode != 0:
        raise GitIsolationError(f"Git push failed: {push_proc.stderr or push_proc.stdout}")

    return {
        "success": True,
        "branch": branch_name,
        "remote": remote,
        "output": push_proc.stdout or push_proc.stderr,
    }


def cleanup_isolated_worktree(repo_root: str | Path, worktree_dir: str | Path, delete_branch: bool = False) -> bool:
    repo_path = Path(repo_root).resolve()
    wt_path = Path(worktree_dir).resolve()

    if wt_path.exists():
        # Retrieve branch before removal if delete_branch is requested
        branch_to_delete = None
        if delete_branch:
            wt_state = inspect_git_state(wt_path)
            branch = wt_state.get("branch")
            if branch and branch.startswith("iris/task/"):
                branch_to_delete = branch

        remove_proc = run_git(repo_path, "worktree", "remove", "--force", str(wt_path))
        run_git(repo_path, "worktree", "prune")

        if wt_path.exists():
            try:
                shutil.rmtree(wt_path, ignore_errors=True)
            except OSError:
                pass

        if branch_to_delete:
            validate_push_permission(branch_to_delete)
            run_git(repo_path, "branch", "-D", branch_to_delete)

        return True
    return False
