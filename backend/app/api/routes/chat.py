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
from app.schemas.memory import MemoryCreate, MemoryOut, MemoryUpdate
from app.services.memory_service import memory_service

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
                memories_updated=meta.get("memories_updated", []),
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
        voice=payload.voice,
        defer_memory=payload.defer_memory,
    )
    return msg_out


@router.post("/messages/{message_id}/remember")
async def remember_message(
    message_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Update IRIS's memory from a reply sent with ``defer_memory`` (idempotent)."""
    return {"memories_updated": await default_agent.remember_turn(db, user, message_id)}


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


# --- Memories (Contextual Memory Management) ---------------------------------


@router.get("/memories", response_model=list[MemoryOut])
def list_memories(
    category: str | None = Query(
        None, description="Filter by category (PREFERENCE, FACT, PROJECT, CONSTRAINT, INSTRUCTION)"
    ),
    search: str | None = Query(None, description="Optional search query"),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """List persistent user memories, optionally filtered or searched."""
    if search:
        return memory_service.search_relevant_memories(
            db, user_id=user.id, query=search, limit=limit, mark_accessed=False
        )
    return memory_service.get_memories(
        db, user_id=user.id, category=category, is_active=True, limit=limit
    )


@router.post("/memories", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
def create_memory(
    payload: MemoryCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Explicitly save a persistent memory or context item."""
    mem = memory_service.store_memory(
        db=db,
        user=user,
        content=payload.content,
        category=payload.category,
        key=payload.key,
        importance=payload.importance,
        confidence=payload.confidence,
        conversation_id=payload.conversation_id,
        source="USER_EXPLICIT",
    )
    return mem


@router.patch("/memories/{memory_id}", response_model=MemoryOut)
def update_memory(
    memory_id: int,
    payload: MemoryUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Update a stored memory item."""
    from app.models.ai_memory import AIMemory

    mem = (
        db.query(AIMemory)
        .filter(AIMemory.id == memory_id, AIMemory.user_id == user.id)
        .first()
    )
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found.")

    if payload.content is not None:
        mem.content = payload.content.strip()
    if payload.category is not None:
        mem.category = payload.category.upper()
    if payload.key is not None:
        mem.key = payload.key.strip().lower()
    if payload.importance is not None:
        mem.importance = payload.importance
    if payload.is_active is not None:
        mem.is_active = payload.is_active

    db.commit()
    db.refresh(mem)
    return mem


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Delete a memory item."""
    success = memory_service.delete_memory(db=db, user_id=user.id, memory_id=memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found.")

