"""Memory and contextual knowledge tools for the IRIS Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import Tool
from app.models.ai_memory import AIMemory
from app.models.user import User
from app.schemas.memory import MEMORY_CATEGORY_GUIDE, MemoryCategory
from app.services.memory_service import memory_service


# --- 1. SaveMemoryTool ---


class SaveMemoryParams(BaseModel):
    content: str = Field(..., min_length=2, description="The durable fact, preference, rule, or context to store")
    category: MemoryCategory = Field(
        "GENERAL",
        description="Category: " + MEMORY_CATEGORY_GUIDE,
    )
    key: str | None = Field(None, description="Optional unique identifier slug, e.g. 'deep_work_time', 'startup_focus'")
    importance: float = Field(0.7, ge=0.0, le=1.0, description="Importance score (0.0=low, 1.0=critical)")


class SaveMemoryTool(Tool):
    name = "save_memory"
    description = "Store a durable fact, preference, instruction, or context into IRIS long-term memory."
    parameters_schema = SaveMemoryParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        content = kwargs["content"]
        category = kwargs.get("category", "GENERAL")
        key = kwargs.get("key")
        importance = kwargs.get("importance", 0.7)

        mem = memory_service.store_memory(
            db=db,
            user=user,
            content=content,
            category=category,
            key=key,
            importance=importance,
            source="AGENT_TOOL",
        )

        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "id": mem.id,
                "key": mem.key,
                "category": mem.category,
                "content": mem.content,
                "importance": mem.importance,
            },
            summary=f"Saved context to memory: [{mem.category}] {mem.content}",
        )


# --- 2. SearchMemoryTool ---


class SearchMemoryParams(BaseModel):
    query: str = Field(..., min_length=1, description="Keywords or concept to search for in stored memory")
    limit: int = Field(5, ge=1, le=20, description="Maximum number of memories to return")


class SearchMemoryTool(Tool):
    name = "search_memory"
    description = "Search or recall memories and contextual knowledge stored from past conversations."
    parameters_schema = SearchMemoryParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        query = kwargs["query"]
        limit = kwargs.get("limit", 5)

        memories = memory_service.search_relevant_memories(
            db=db,
            user_id=user.id,
            query=query,
            limit=limit,
            mark_accessed=True,
        )

        data = [
            {
                "id": m.id,
                "category": m.category,
                "key": m.key,
                "content": m.content,
                "importance": m.importance,
                "access_count": m.access_count,
            }
            for m in memories
        ]

        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"memories": data, "count": len(data)},
            summary=f"Recalled {len(data)} memories matching '{query}'.",
        )


# --- 3. ForgetMemoryTool ---


class ForgetMemoryParams(BaseModel):
    memory_id: int | None = Field(None, description="ID of the memory to remove")
    key: str | None = Field(None, description="Key of the memory to remove")


class ForgetMemoryTool(Tool):
    name = "forget_memory"
    description = "Remove or forget an outdated memory or preference by ID or key."
    parameters_schema = ForgetMemoryParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        memory_id = kwargs.get("memory_id")
        key = kwargs.get("key")

        if not memory_id and not key:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="Must provide either memory_id or key to forget.",
                summary="Failed to forget memory: neither memory_id nor key provided.",
            )

        if memory_id:
            success = memory_service.delete_memory(db=db, user_id=user.id, memory_id=memory_id)
            if success:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    summary=f"Removed memory #{memory_id}.",
                )
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Memory #{memory_id} not found.",
                summary=f"Memory #{memory_id} not found.",
            )

        # Forget by key
        mem = (
            db.query(AIMemory)
            .filter(AIMemory.user_id == user.id, AIMemory.key == key.lower().strip())
            .first()
        )
        if mem:
            db.delete(mem)
            db.commit()
            return ToolResult(
                tool_name=self.name,
                success=True,
                summary=f"Forgot memory with key '{key}'.",
            )

        return ToolResult(
            tool_name=self.name,
            success=False,
            error=f"No memory found with key '{key}'.",
            summary=f"No memory found with key '{key}'.",
        )


# --- 4. ListMemoriesTool ---


class ListMemoriesParams(BaseModel):
    category: MemoryCategory | None = Field(None, description="Optional category filter")
    limit: int = Field(20, ge=1, le=50, description="Max memories to retrieve")


class ListMemoriesTool(Tool):
    name = "list_memories"
    description = "List active memories, preferences, and facts known to IRIS."
    parameters_schema = ListMemoriesParams

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        category = kwargs.get("category")
        limit = kwargs.get("limit", 20)

        memories = memory_service.get_memories(
            db=db, user_id=user.id, category=category, is_active=True, limit=limit
        )

        data = [
            {
                "id": m.id,
                "category": m.category,
                "key": m.key,
                "content": m.content,
                "importance": m.importance,
            }
            for m in memories
        ]

        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"memories": data, "count": len(data)},
            summary=f"Listed {len(data)} stored memories.",
        )
