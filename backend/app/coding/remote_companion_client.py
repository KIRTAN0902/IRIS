"""Client library in IRIS backend to interact with Remote Execution Companion."""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("iris.coding.remote_companion_client")


class RemoteCompanionError(RuntimeError):
    """Raised when an operation on the remote companion fails."""


class RemoteCompanionClient:
    """Communicates with the containerized Remote Execution Companion on Hugging Face or Cloud."""

    def __init__(self, base_url: str | None = None, secret_token: str | None = None, timeout: float = 30.0) -> None:
        from app.core.config import settings
        self.base_url = (base_url or os.getenv("REMOTE_COMPANION_URL") or getattr(settings, "remote_companion_url", None) or "http://localhost:7860").rstrip("/")
        self.secret_token = secret_token or os.getenv("IRIS_COMPANION_SECRET") or getattr(settings, "iris_companion_secret", None) or "dev-secret-token"
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.secret_token}",
            "Content-Type": "application/json",
        }

    async def health(self) -> dict[str, Any]:
        """Check status and readiness of remote companion."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{self.base_url}/health")
            if resp.status_code != 200:
                raise RemoteCompanionError(f"Remote companion unhealthy: {resp.text}")
            return resp.json()

    async def ready(self) -> dict[str, Any]:
        """Check if remote companion has git available and storage is writable."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{self.base_url}/ready")
            if resp.status_code != 200:
                raise RemoteCompanionError(f"Remote companion not ready: {resp.text}")
            return resp.json()

    async def provision_workspace(
        self,
        workspace_id: str,
        repo_url: str,
        branch: str = "main",
        github_pat: str | None = None,
    ) -> dict[str, Any]:
        """Clone repository and provision isolated workspace in the remote container."""
        payload = {
            "workspace_id": workspace_id,
            "repo_url": repo_url,
            "branch": branch,
            "github_pat": github_pat,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/workspaces/provision",
                headers=self.headers,
                json=payload,
            )
            if resp.status_code != 200:
                raise RemoteCompanionError(f"Provisioning failed: {resp.text}")
            return resp.json()

    async def execute_task_stream(
        self,
        workspace_id: str,
        task_id: str,
        prompt: str,
        task_branch: str,
        conversation_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream real-time NDJSON events from remote companion."""
        payload = {
            "task_id": task_id,
            "prompt": prompt,
            "task_branch": task_branch,
            "conversation_id": conversation_id,
        }
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/workspaces/{workspace_id}/execute",
                headers=self.headers,
                json=payload,
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RemoteCompanionError(f"Execution dispatch failed: {body.decode()}")
                async for line in response.aiter_lines():
                    line = line.strip()
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            yield {"event": "raw_log", "text": line}

    async def stop(self, workspace_id: str) -> dict[str, Any]:
        """Terminate active execution processes on remote companion."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/workspaces/{workspace_id}/stop",
                headers=self.headers,
            )
            return resp.json() if resp.status_code == 200 else {"stopped": False, "error": resp.text}

    async def get_diff(self, workspace_id: str) -> dict[str, Any]:
        """Fetch changed files, diff stat, and unified diff from remote workspace."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/api/workspaces/{workspace_id}/diff",
                headers=self.headers,
            )
            if resp.status_code != 200:
                raise RemoteCompanionError(f"Diff retrieval failed: {resp.text}")
            return resp.json()

    async def checkpoint(self, workspace_id: str) -> dict[str, Any]:
        """Capture in-flight uncommitted patch for durable persistence."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/workspaces/{workspace_id}/checkpoint",
                headers=self.headers,
            )
            if resp.status_code != 200:
                raise RemoteCompanionError(f"Checkpoint failed: {resp.text}")
            return resp.json()

    async def restore(
        self,
        workspace_id: str,
        branch: str,
        patch: str | None = None,
        expected_hash: str | None = None,
    ) -> dict[str, Any]:
        """Restore uncommitted patch into workspace with optional hash verification."""
        payload: dict[str, Any] = {"branch": branch, "patch": patch}
        if expected_hash:
            payload["expected_hash"] = expected_hash
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/workspaces/{workspace_id}/restore",
                headers=self.headers,
                json=payload,
            )
            if resp.status_code != 200:
                raise RemoteCompanionError(f"Restore failed: {resp.text}")
            return resp.json()

    async def commit(
        self,
        workspace_id: str,
        message: str,
        author_name: str = "IRIS Coding Co-worker",
        author_email: str = "coworker@iris.dev",
    ) -> dict[str, Any]:
        """Commit changes on remote task branch."""
        payload = {
            "message": message,
            "author_name": author_name,
            "author_email": author_email,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/workspaces/{workspace_id}/commit",
                headers=self.headers,
                json=payload,
            )
            if resp.status_code != 200:
                raise RemoteCompanionError(f"Commit failed: {resp.text}")
            return resp.json()

    async def push(self, workspace_id: str, branch: str, github_pat: str) -> dict[str, Any]:
        """Push approved commit to GitHub repository."""
        payload = {"branch": branch, "github_pat": github_pat}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/workspaces/{workspace_id}/push",
                headers=self.headers,
                json=payload,
            )
            if resp.status_code != 200:
                raise RemoteCompanionError(f"Push failed: {resp.text}")
            return resp.json()
