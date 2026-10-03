"""Tests for Chat Memories API endpoints (/api/chat/memories/*)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.ai_memory import AIMemory
from app.models.user import User


def test_memories_crud_api(client: TestClient, db: Session):
    # 1. Create a memory
    resp = client.post(
        "/api/chat/memories",
        json={
            "content": "User prefers no meetings on Wednesday mornings",
            "category": "PREFERENCE",
            "key": "no_wednesday_meetings",
            "importance": 0.9,
        },
    )
    assert resp.status_code == 201
    created = resp.json()
    mem_id = created["id"]
    assert created["key"] == "no_wednesday_meetings"
    assert created["category"] == "PREFERENCE"
    assert created["importance"] == 0.9

    # 2. List memories
    resp_list = client.get("/api/chat/memories")
    assert resp_list.status_code == 200
    items = resp_list.json()
    assert any(m["id"] == mem_id for m in items)

    # 3. Filter by category
    resp_filtered = client.get("/api/chat/memories?category=PREFERENCE")
    assert resp_filtered.status_code == 200
    assert all(m["category"] == "PREFERENCE" for m in resp_filtered.json())

    # 4. Search query
    resp_search = client.get("/api/chat/memories?search=Wednesday")
    assert resp_search.status_code == 200
    search_items = resp_search.json()
    assert len(search_items) >= 1
    assert any("Wednesday" in m["content"] for m in search_items)

    # 5. Patch memory
    resp_patch = client.patch(
        f"/api/chat/memories/{mem_id}",
        json={"content": "User prefers no meetings on Wednesday all day", "importance": 0.95},
    )
    assert resp_patch.status_code == 200
    patched = resp_patch.json()
    assert "Wednesday all day" in patched["content"]
    assert patched["importance"] == 0.95

    # 6. Delete memory
    resp_del = client.delete(f"/api/chat/memories/{mem_id}")
    assert resp_del.status_code == 204

    # 7. Verify deletion
    mem_in_db = db.query(AIMemory).filter(AIMemory.id == mem_id).first()
    assert mem_in_db is None


def test_memories_cross_user_isolation(client: TestClient, db: Session):
    other_user = User(email="intruder_mem@iris.local", name="Intruder Mem", timezone="UTC")
    db.add(other_user)
    db.commit()
    db.refresh(other_user)

    other_mem = AIMemory(
        user_id=other_user.id,
        content="Intruder secret financial note",
        category="FACT",
        key="secret_key",
        importance=0.9,
    )
    db.add(other_mem)
    db.commit()
    db.refresh(other_mem)

    # Current client cannot delete other user's memory
    resp_del = client.delete(f"/api/chat/memories/{other_mem.id}")
    assert resp_del.status_code == 404

    # Current client listing does not see other user's memory
    resp_list = client.get("/api/chat/memories")
    assert resp_list.status_code == 200
    ids = [m["id"] for m in resp_list.json()]
    assert other_mem.id not in ids
