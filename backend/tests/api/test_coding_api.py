"""Tests for autonomous coding API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_coding_api_endpoints(client: TestClient):
    # Direct launch is intentionally disabled because it bypasses brief approval.
    res = client.post(
        "/api/coding/tasks",
        json={
            "instruction": "Fix linting errors and run pytest",
            "workspace": "iris",
        },
    )
    assert res.status_code == 410
