"""Tests for Chat API endpoints (/api/chat/*)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_chat_conversations_api_crud(client: TestClient, db: Session):
    # 1. Create conversation
    resp = client.post("/api/chat/conversations?title=Morning%20Standup")
    assert resp.status_code == 201
    conv_data = resp.json()
    conv_id = conv_data["id"]
    assert conv_data["title"] == "Morning Standup"

    # 2. List conversations
    resp_list = client.get("/api/chat/conversations")
    assert resp_list.status_code == 200
    items = resp_list.json()
    assert any(c["id"] == conv_id for c in items)

    # 3. Post a message
    resp_msg = client.post(
        f"/api/chat/conversations/{conv_id}/messages",
        json={"content": "What should I do right now?"},
    )
    assert resp_msg.status_code == 200
    msg_data = resp_msg.json()
    assert msg_data["conversation_id"] == conv_id
    assert msg_data["role"] == "ASSISTANT"
    assert len(msg_data["content"]) > 0

    # 4. Get conversation with messages
    resp_get = client.get(f"/api/chat/conversations/{conv_id}")
    assert resp_get.status_code == 200
    detail = resp_get.json()
    assert len(detail["messages"]) >= 1

    # 5. Delete conversation
    resp_del = client.delete(f"/api/chat/conversations/{conv_id}")
    assert resp_del.status_code == 204

    # 6. Verify deleted
    resp_after = client.get(f"/api/chat/conversations/{conv_id}")
    assert resp_after.status_code == 404


def test_chat_conversation_cross_user_isolation(client: TestClient, db: Session):
    """Ensure user cannot retrieve, message, or delete another user's conversation."""
    from app.models.ai_conversation import AIConversation
    from app.models.user import User

    other_user = User(email="intruder@iris.local", name="Intruder", timezone="UTC")
    db.add(other_user)
    db.commit()
    db.refresh(other_user)

    other_conv = AIConversation(user_id=other_user.id, title="Intruder Private Chat")
    db.add(other_conv)
    db.commit()
    db.refresh(other_conv)

    # Current client user tries to get other_conv
    resp_get = client.get(f"/api/chat/conversations/{other_conv.id}")
    assert resp_get.status_code == 404

    # Current client user tries to message other_conv
    resp_msg = client.post(
        f"/api/chat/conversations/{other_conv.id}/messages",
        json={"content": "I am snooping"},
    )
    # Since other_conv does not belong to current user, agent resolves a new conversation
    # for current user or fails
    if resp_msg.status_code == 200:
        data = resp_msg.json()
        assert data["conversation_id"] != other_conv.id

    # Current client user tries to delete other_conv
    resp_del = client.delete(f"/api/chat/conversations/{other_conv.id}")
    assert resp_del.status_code == 404

