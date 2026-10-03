"""AI Memory and Context Service for IRIS.

Manages persistent user context across conversations:
- Long-term context storage and deduplication
- Automatic memory extraction from conversation turns (LLM + deterministic fallback)
- Semantic and keyword retrieval for agent prompts
- Synchronizing key facts/preferences with User profile
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.ai_memory import AIMemory
from app.models.user import User
from app.schemas.memory import MEMORY_CATEGORY_GUIDE, MemoryExtractionResponse
from app.utils.datetime import utcnow



class MemoryService:
    """Service for managing, retrieving, and extracting long-term user memories."""

    def get_memories(
        self,
        db: Session,
        user_id: int,
        category: str | None = None,
        is_active: bool = True,
        limit: int = 50,
    ) -> list[AIMemory]:
        """Fetch stored memories for a user, ordered by importance and recency."""
        query = db.query(AIMemory).filter(AIMemory.user_id == user_id)
        if is_active is not None:
            query = query.filter(AIMemory.is_active == is_active)
        if category:
            query = query.filter(AIMemory.category == category.upper())
        return query.order_by(AIMemory.importance.desc(), AIMemory.updated_at.desc()).limit(limit).all()

    def search_relevant_memories(
        self,
        db: Session,
        user_id: int,
        query: str,
        limit: int = 8,
        mark_accessed: bool = True,
    ) -> list[AIMemory]:
        """Search active memories relevant to a query using term-matching and importance weighting."""
        active_memories = (
            db.query(AIMemory)
            .filter(AIMemory.user_id == user_id, AIMemory.is_active.is_(True))
            .order_by(AIMemory.importance.desc(), AIMemory.updated_at.desc())
            .limit(100)
            .all()
        )

        if not active_memories:
            return []

        if not query.strip():
            # Return top memories by importance
            top = active_memories[:limit]
            if mark_accessed:
                self._touch_memories(db, top)
            return top

        # Extract words from query for keyword scoring
        query_words = set(re.findall(r"\w{3,}", query.lower()))

        scored_memories: list[tuple[float, AIMemory]] = []
        now = utcnow()

        for mem in active_memories:
            score = mem.importance  # Base score between 0.0 and 1.0

            content_lower = mem.content.lower()
            key_lower = (mem.key or "").lower()
            cat_lower = mem.category.lower()

            # Exact phrase match
            if query.lower() in content_lower:
                score += 2.0

            # Match on key
            if mem.key and (mem.key.lower() in query.lower() or any(w in key_lower for w in query_words)):
                score += 1.5

            # Word overlap match
            for word in query_words:
                if word in content_lower:
                    score += 0.5
                if word in key_lower:
                    score += 0.8
                if word in cat_lower:
                    score += 0.3

            # Recency bias (bonus for recently updated memories)
            if mem.updated_at:
                days_old = max(0, (now - mem.updated_at).total_seconds() / 86400)
                score += max(0.0, 0.5 - (days_old * 0.05))

            scored_memories.append((score, mem))

        # Sort by score descending
        scored_memories.sort(key=lambda x: x[0], reverse=True)

        # Select top candidates that meet minimal relevance threshold or high importance
        top_candidates: list[AIMemory] = []
        for s, mem in scored_memories[:limit]:
            if s >= 0.7 or len(top_candidates) < 3:
                top_candidates.append(mem)

        if mark_accessed and top_candidates:
            self._touch_memories(db, top_candidates)

        return top_candidates

    def _touch_memories(self, db: Session, memories: list[AIMemory]) -> None:
        """Bump access count and last_accessed_at for retrieved memories."""
        now = utcnow()
        for m in memories:
            m.access_count = (m.access_count or 0) + 1
            m.last_accessed_at = now
        db.commit()

    def store_memory(
        self,
        db: Session,
        user: User,
        content: str,
        category: str = "GENERAL",
        key: str | None = None,
        importance: float = 0.5,
        confidence: float = 0.9,
        conversation_id: int | None = None,
        source: str = "CONVERSATION_EXTRACTED",
    ) -> AIMemory:
        """Store or update a memory item, deduplicating by key or near-identical content."""
        clean_content = content.strip()
        cat_clean = category.upper()

        # Check existing memory with matching key
        existing: AIMemory | None = None
        if key:
            clean_key = key.strip().lower().replace(" ", "_")
            existing = (
                db.query(AIMemory)
                .filter(
                    AIMemory.user_id == user.id,
                    AIMemory.key == clean_key,
                    AIMemory.is_active.is_(True),
                )
                .first()
            )
        else:
            clean_key = None
            # Check near-identical content match (first 80 chars)
            existing = (
                db.query(AIMemory)
                .filter(
                    AIMemory.user_id == user.id,
                    AIMemory.content.ilike(f"{clean_content[:80]}%"),
                    AIMemory.is_active.is_(True),
                )
                .first()
            )

        if existing:
            existing.content = clean_content
            existing.category = cat_clean
            existing.importance = max(existing.importance, importance)
            existing.confidence = confidence
            existing.source = source
            existing.updated_at = utcnow()
            if conversation_id:
                existing.conversation_id = conversation_id
            db.commit()
            db.refresh(existing)
            mem = existing
        else:
            mem = AIMemory(
                user_id=user.id,
                conversation_id=conversation_id,
                category=cat_clean,
                key=clean_key,
                content=clean_content,
                importance=importance,
                confidence=confidence,
                source=source,
                is_active=True,
            )
            db.add(mem)
            db.commit()
            db.refresh(mem)

        # Sync with user profile facts/preferences if key is present
        if clean_key:
            self._sync_user_profile(db, user, cat_clean, clean_key, clean_content)

        return mem

    def _sync_user_profile(
        self, db: Session, user: User, category: str, key: str, content: str
    ) -> None:
        """Sync key context with user.preferences or user.facts for system-wide awareness."""
        changed = False
        if category in {"PREFERENCE", "ROUTINE", "WORK_STYLE"}:
            prefs = dict(user.preferences or {})
            prefs[key] = content
            user.preferences = prefs
            changed = True
        elif category in {"FACT", "PROJECT", "CONSTRAINT", "PEOPLE"}:
            facts = dict(user.facts or {})
            facts[key] = content
            user.facts = facts
            changed = True

        if changed:
            db.add(user)
            db.commit()

    def delete_memory(self, db: Session, user_id: int, memory_id: int) -> bool:
        """Deactivate or remove a memory by ID."""
        mem = (
            db.query(AIMemory)
            .filter(AIMemory.id == memory_id, AIMemory.user_id == user_id)
            .first()
        )
        if not mem:
            return False
        db.delete(mem)
        db.commit()
        return True

    async def extract_and_store_from_conversation(
        self,
        db: Session,
        user: User,
        user_message: str,
        assistant_message: str,
        conversation_id: int | None = None,
    ) -> list[AIMemory]:
        """Extract key context from conversational turns using LLM or rule-based heuristics."""
        from app.ai.factory import get_ai_provider

        from app.models.ai_conversation import AIConversation
        from app.services import conversation_memory

        extracted_items: list[dict[str, Any]] = []
        provider = get_ai_provider()
        conversation = db.get(AIConversation, conversation_id) if conversation_id else None
        new_summary: str | None = None
        new_topics: list[str] = []

        # 1. Attempt LLM structured extraction if provider is enabled
        if provider.enabled:
            extraction_system = (
                "You are the IRIS Personal Memory & Context Engine. "
                "Your role is to continuously extract lasting personal context, facts, "
                "preferences, work habits, rules, project status, and constraints "
                "from conversation turns.\n\n"
                "GUIDELINES:\n"
                "- Extract ONLY lasting, durable information that IRIS should remember in future conversations.\n"
                f"- Categories: {MEMORY_CATEGORY_GUIDE}.\n"
                "- Day-to-day schedule details belong in ROUTINE; how and when they work best "
                "belongs in WORK_STYLE. Use a stable 'key' (e.g. 'wake_time', 'peak_focus_hours') "
                "so updates replace the old value instead of duplicating it.\n"
                "- Do NOT extract temporary queries like 'What time is it?' or ephemeral acknowledgments.\n"
                "- If no new durable context is present in this turn, return an empty list.\n"
                "- ALSO return conversation_summary: the previous summary updated with this turn, "
                "so a later, different conversation knows what was discussed and decided here."
            )
            previous = (conversation.summary if conversation else None) or "(none yet)"
            turn_text = (
                f"Previous conversation summary:\n{previous}\n\n"
                f"Latest turn:\nUser said: {user_message}\nIRIS replied: {assistant_message}"
            )

            try:
                result = await provider.generate_structured(
                    system=extraction_system,
                    prompt=turn_text,
                    schema=MemoryExtractionResponse,
                )
                if result and result.conversation_summary.strip():
                    new_summary = result.conversation_summary
                    new_topics = result.topics
                if result and result.memories:
                    for m in result.memories:
                        extracted_items.append(
                            {
                                "content": m.content,
                                "category": m.category,
                                "key": m.key,
                                "importance": m.importance,
                                "source": "CONVERSATION_EXTRACTED",
                            }
                        )
            except Exception:
                extracted_items = []

        # 2. Heuristic fallback extractor if LLM returned nothing or is offline
        if not extracted_items:
            heuristic_items = self._heuristic_extract(user_message)
            extracted_items.extend(heuristic_items)

        # 3. Keep this conversation's shared summary current
        if conversation is not None:
            if not new_summary:
                new_summary = conversation_memory.fallback_summary(conversation.summary, user_message)
            conversation_memory.save_summary(db, conversation, new_summary, new_topics)
            db.commit()

        # 4. Persist extracted context items
        stored: list[AIMemory] = []
        for item in extracted_items:
            mem = self.store_memory(
                db=db,
                user=user,
                content=item["content"],
                category=item.get("category", "GENERAL"),
                key=item.get("key"),
                importance=item.get("importance", 0.5),
                conversation_id=conversation_id,
                source=item.get("source", "CONVERSATION_EXTRACTED"),
            )
            stored.append(mem)

        return stored

    def _heuristic_extract(self, text: str) -> list[dict[str, Any]]:
        """Rule-based pattern matcher for extracting key context when LLM is unavailable."""
        results: list[dict[str, Any]] = []
        lower = text.lower().strip()

        # Preference patterns
        pref_patterns = [
            (r"(?:i prefer|my preference is|i like to|i always prefer)\s+([^.\n]+)", "preference", "PREFERENCE", 0.8),
            (r"(?:i want to focus on|my main focus is)\s+([^.\n]+)", "focus_preference", "PREFERENCE", 0.85),
            (r"(?:from now on|please always|always make sure to)\s+([^.\n]+)", "operating_instruction", "INSTRUCTION", 0.9),
            (r"(?:remember that|note that|keep in mind that)\s+([^.\n]+)", "explicit_note", "FACT", 0.85),
            (r"(?:i don't work|i can't work|i must sleep at)\s+([^.\n]+)", "schedule_constraint", "CONSTRAINT", 0.9),
            (r"(?:i wake up at|i usually wake up at|i get up at)\s+([^.\n]+)", "wake_time", "ROUTINE", 0.85),
            (r"(?:i go to bed at|i usually sleep at|i sleep at)\s+([^.\n]+)", "sleep_time", "ROUTINE", 0.85),
            (r"(?:every day i|every morning i|every evening i|every night i|my routine is|on weekdays i|on weekends i)\s+([^.\n]+)", "daily_routine", "ROUTINE", 0.8),
            (r"(?:i work best|i'm most productive|i am most productive|i focus best|i'm most focused|i do my best work)\s+([^.\n]+)", "peak_focus", "WORK_STYLE", 0.85),
            (r"(?:i usually work|i like to work in|i work in)\s+([^.\n]+)", "work_pattern", "WORK_STYLE", 0.75),
            (r"(?:my co-?founder is|my teammate is|working with)\s+([^.\n]+)", "team_info", "FACT", 0.75),
            (r"(?:nexus is|marketory is|our startup is|our product is|pivoting to|targeting)\s+([^.\n]+)", "startup_context", "PROJECT", 0.85),
            (r"(?:my exam is on|my finals are on|submission deadline is)\s+([^.\n]+)", "academic_deadline", "FACT", 0.8),
        ]

        for pattern, default_key, cat, imp in pref_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Use captured group 1 if present, otherwise full match
                extracted_content = match.group(1).strip() if match.groups() else match.group(0).strip()
                # Ensure clean sentence capitalization
                if extracted_content:
                    extracted_content = extracted_content[0].upper() + extracted_content[1:]
                results.append(
                    {
                        "content": extracted_content,
                        "category": cat,
                        "key": default_key,
                        "importance": imp,
                        "source": "CONVERSATION_EXTRACTED",
                    }
                )

        return results


    def format_memories_for_prompt(self, memories: list[AIMemory]) -> str:
        """Format retrieved memories into a clean markdown block for agent system prompt."""
        if not memories:
            return ""

        lines = ["STORED USER MEMORY & CONTEXT (learned from past conversations):"]
        for m in memories:
            key_part = f" [{m.key}]" if m.key else ""
            lines.append(f"- [{m.category}]{key_part}: {m.content}")

        return "\n".join(lines)


# Global singleton instance
memory_service = MemoryService()
