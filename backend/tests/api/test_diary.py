"""Tests for Diary API and Agent tools."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agent.registry import default_registry
from app.core.security import get_current_user


def test_create_and_list_diary_entries(client: TestClient):
    # 1. Create a note
    res = client.post(
        "/api/diary/entries",
        json={
            "title": "Quantum Computing Ideas",
            "content": "Explore hybrid quantum-classical algorithms for portfolio optimization.",
            "category": "IDEA",
            "tags": ["quantum", "finance"],
            "is_pinned": True,
        },
    )
    assert res.status_code == 201
    entry = res.json()
    assert entry["title"] == "Quantum Computing Ideas"
    assert entry["category"] == "IDEA"
    assert entry["is_pinned"] is True
    assert entry["tags"] == ["quantum", "finance"]
    entry_id = entry["id"]

    # 2. List entries
    list_res = client.get("/api/diary/entries")
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) >= 1
    assert any(i["id"] == entry_id for i in items)

    # 3. Filter by category
    cat_res = client.get("/api/diary/entries?category=IDEA")
    assert cat_res.status_code == 200
    assert all(i["category"] == "IDEA" for i in cat_res.json())

    # 4. Search keyword
    search_res = client.get("/api/diary/entries?search=algorithms")
    assert search_res.status_code == 200
    assert len(search_res.json()) >= 1
    assert search_res.json()[0]["id"] == entry_id


def test_update_and_delete_diary_entry(client: TestClient):
    res = client.post(
        "/api/diary/entries",
        json={"title": "Draft Thought", "content": "Initial thoughts."},
    )
    entry_id = res.json()["id"]

    # Update
    patch_res = client.patch(
        f"/api/diary/entries/{entry_id}",
        json={"title": "Final Thought", "content": "Refined thoughts.", "is_pinned": True},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["title"] == "Final Thought"
    assert patch_res.json()["is_pinned"] is True

    # Delete
    del_res = client.delete(f"/api/diary/entries/{entry_id}")
    assert del_res.status_code == 204

    # Verify not found
    get_res = client.get(f"/api/diary/entries/{entry_id}")
    assert get_res.status_code == 404


def test_diary_summary(client: TestClient):
    client.post(
        "/api/diary/entries",
        json={"title": "Summary Note", "content": "testing summary", "category": "REFLECTION", "tags": ["mindset"]},
    )
    res = client.get("/api/diary/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert "REFLECTION" in data["categories"]
    assert "mindset" in data["all_tags"]


@pytest.mark.asyncio
async def test_diary_agent_tools(db: Session):
    user = get_current_user(db)

    # Execute create_diary_entry tool via registry
    result = await default_registry.execute(
        "create_diary_entry",
        db,
        user,
        {
            "title": "Agent Saved Startup Idea",
            "content": "Build autonomous pair programming agent.",
            "category": "IDEA",
            "tags": ["startup", "agentic"],
        },
    )
    assert result.success is True
    assert "Saved idea in Diary" in result.summary

    # Execute read_diary_entries tool via registry
    read_result = await default_registry.execute(
        "read_diary_entries",
        db,
        user,
        {"query": "autonomous", "category": "IDEA"},
    )
    assert read_result.success is True
    assert len(read_result.data) >= 1

