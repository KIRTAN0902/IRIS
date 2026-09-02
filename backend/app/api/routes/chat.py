"""Chat & Conversational Agent API Endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.agent.agent import default_agent
from app.agent.schemas import (
    ChatMessageIn,
    ChatMessageOut,
    ConversationDetailOut,
    ConversationOut,
)
from app.api.deps import current_user
from app.core.database import get_db
from app.models.ai_conversation import AIConversation
from app.models.user import User

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(
    title: str | None = Query(default="New conversation", max_length=255),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Create a new conversational thread."""
    conv = AIConversation(user_id=user.id, title=title or "New conversation")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """List all conversations for the user, ordered by most recent."""
    return (
        db.query(AIConversation)
        .filter(AIConversation.user_id == user.id)
        .order_by(AIConversation.updated_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(
    conversation_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Retrieve conversation details and chronological message history."""
    conv = (
        db.query(AIConversation)
        .filter(AIConversation.id == conversation_id, AIConversation.user_id == user.id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    formatted_messages: list[ChatMessageOut] = []
    for m in conv.messages:
        meta = m.metadata_json or {}
        formatted_messages.append(
            ChatMessageOut(
                id=m.id,
                conversation_id=conv.id,
                role=m.role,
                content=m.content,
                actions_taken=meta.get("actions_taken", []),
                evidence=meta.get("evidence", []),
                recommended_action=meta.get("recommended_action"),
                source=meta.get("source", "AI"),
                created_at=m.created_at,
            )
        )

    return ConversationDetailOut(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=formatted_messages,
    )


@router.post("/conversations/{conversation_id}/messages", response_model=ChatMessageOut)
async def send_message(
    conversation_id: int,
    payload: ChatMessageIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Send a user message, trigger agent reasoning and tools, and return response."""
    msg_out, _ = await default_agent.run_turn(
        db=db,
        user=user,
        user_message=payload.content,
        conversation_id=conversation_id,
    )
    return msg_out


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Delete a conversation thread and its messages."""
    conv = (
        db.query(AIConversation)
        .filter(AIConversation.id == conversation_id, AIConversation.user_id == user.id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    db.delete(conv)
    db.commit()
