"""Shared episodic memory across conversations.

Facts ("co-founder is Alex") live in ``AIMemory``. This module remembers
*what was talked about*: every conversation keeps a rolling summary (topics,
decisions, plans, open questions) that every other conversation can see, so
an internship thread knows what was decided in yesterday's startup thread.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.ai_conversation import AIConversation, AIMessage
from app.models.enums import AIRole
from app.utils.datetime import to_local, utcnow

SUMMARY_MAX_CHARS = 900
_FALLBACK_LINES = 5
_STOPWORDS = {
    "the", "and", "for", "you", "your", "are", "was", "what", "with", "that", "this",
    "have", "how", "can", "should", "about", "from", "into", "will", "just", "now",
    "my", "me", "i", "a", "an", "to", "of", "in", "on", "is", "it", "do", "we",
}


# --- Writing ----------------------------------------------------------------------


def fallback_summary(previous: str | None, user_message: str) -> str:
    """Deterministic summary when no model is available: the last few user asks."""
    lines = [ln for ln in (previous or "").splitlines() if ln.startswith("- ")]
    lines.append("- " + " ".join(user_message.split())[:140])
    return "\n".join(lines[-_FALLBACK_LINES:])


def save_summary(
    db: Session, conversation: AIConversation, summary: str, topics: list[str] | None = None
) -> None:
    summary = (summary or "").strip()
    if not summary:
        return
    conversation.summary = summary[:SUMMARY_MAX_CHARS]
    if topics:
        conversation.topics = [t.strip()[:40] for t in topics if t and t.strip()][:6]
    conversation.updated_at = utcnow()
    db.add(conversation)


# --- Reading ----------------------------------------------------------------------


def _effective_summary(db: Session, conv: AIConversation) -> str | None:
    """Stored summary, or a quick one built from the user's messages (older threads)."""
    if conv.summary:
        return conv.summary
    rows = (
        db.query(AIMessage.content)
        .filter(AIMessage.conversation_id == conv.id, AIMessage.role == AIRole.USER.value)
        .order_by(AIMessage.created_at.desc())
        .limit(_FALLBACK_LINES)
        .all()
    )
    if not rows:
        return None
    summary = None
    for (content,) in reversed(rows):
        summary = fallback_summary(summary, content)
    return summary


def _when(dt: datetime | None, tz: str) -> str:
    if dt is None:
        return ""
    local, now = to_local(dt, tz), to_local(utcnow(), tz)
    days = (now.date() - local.date()).days
    if days <= 0:
        return f"today {local:%H:%M}"
    if days == 1:
        return f"yesterday {local:%H:%M}"
    if days < 7:
        return f"{local:%A}"
    return f"{local:%d %b}"


def _brief(db: Session, conv: AIConversation, tz: str) -> dict[str, Any] | None:
    summary = _effective_summary(db, conv)
    if not summary:
        return None
    return {
        "conversation_id": conv.id,
        "title": conv.title,
        "when": _when(conv.updated_at, tz),
        "topics": conv.topics or [],
        "summary": summary,
    }


def recent_conversations(
    db: Session,
    user_id: int,
    tz: str,
    *,
    exclude_id: int | None = None,
    limit: int = 5,
    within_days: int = 30,
) -> list[dict[str, Any]]:
    """Most recently active other conversations, newest first."""
    q = db.query(AIConversation).filter(
        AIConversation.user_id == user_id,
        AIConversation.updated_at >= utcnow() - timedelta(days=within_days),
    )
    if exclude_id:
        q = q.filter(AIConversation.id != exclude_id)
    out = []
    for conv in q.order_by(AIConversation.updated_at.desc()).limit(limit * 2):
        brief = _brief(db, conv, tz)
        if brief:
            out.append(brief)
        if len(out) >= limit:
            break
    return out


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", text.lower()) if w not in _STOPWORDS}


def search_conversations(
    db: Session,
    user_id: int,
    tz: str,
    query: str,
    *,
    exclude_id: int | None = None,
    exclude_ids: set[int] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Conversations whose title, summary, topics or messages match ``query``."""
    terms = _terms(query)
    if not terms:
        return []
    skip = set(exclude_ids or ()) | ({exclude_id} if exclude_id else set())

    like = [AIMessage.content.ilike(f"%{t}%") for t in list(terms)[:8]]
    hits: dict[int, list[str]] = {}
    for conv_id, content in (
        db.query(AIMessage.conversation_id, AIMessage.content)
        .join(AIConversation, AIConversation.id == AIMessage.conversation_id)
        .filter(AIConversation.user_id == user_id, or_(*like))
        .order_by(AIMessage.created_at.desc())
        .limit(200)
    ):
        if conv_id not in skip:
            hits.setdefault(conv_id, []).append(content)

    convs = (
        db.query(AIConversation)
        .filter(AIConversation.user_id == user_id)
        .order_by(AIConversation.updated_at.desc())
        .limit(200)
        .all()
    )
    scored: list[tuple[float, AIConversation, str | None]] = []
    for conv in convs:
        if conv.id in skip:
            continue
        meta = " ".join([conv.title or "", conv.summary or "", " ".join(conv.topics or [])])
        score = 2.0 * len(terms & _terms(meta))
        snippet = None
        for content in hits.get(conv.id, []):
            overlap = len(terms & _terms(content))
            score += overlap
            if overlap and snippet is None:
                snippet = " ".join(content.split())[:220]
        if score > 0:
            scored.append((score, conv, snippet))

    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for _, conv, snippet in scored[:limit]:
        brief = _brief(db, conv, tz) or {
            "conversation_id": conv.id,
            "title": conv.title,
            "when": _when(conv.updated_at, tz),
            "topics": conv.topics or [],
            "summary": "",
        }
        if snippet:
            brief["matching_message"] = snippet
        out.append(brief)
    return out


def conversation_transcript(
    db: Session, user_id: int, conversation_id: int, limit: int = 20
) -> dict[str, Any] | None:
    conv = (
        db.query(AIConversation)
        .filter(AIConversation.id == conversation_id, AIConversation.user_id == user_id)
        .first()
    )
    if not conv:
        return None
    rows = (
        db.query(AIMessage)
        .filter(AIMessage.conversation_id == conv.id)
        .order_by(AIMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "conversation_id": conv.id,
        "title": conv.title,
        "summary": conv.summary,
        "messages": [
            {"role": m.role.lower(), "content": m.content[:1500], "at": m.created_at.isoformat()}
            for m in reversed(rows)
        ],
    }


# --- Rendering ---------------------------------------------------------------------


def render_conversations(recent: list[dict[str, Any]], related: list[dict[str, Any]]) -> str:
    if not recent and not related:
        return ""
    lines = [
        "SHARED MEMORY: OTHER CONVERSATIONS WITH THIS USER (you were part of all of these; "
        "treat them as things you already know):"
    ]

    def block(item: dict[str, Any]) -> None:
        topics = f" [{', '.join(item['topics'])}]" if item.get("topics") else ""
        lines.append(f"- #{item['conversation_id']} \"{item['title']}\" ({item['when']}){topics}")
        for ln in item["summary"].splitlines():
            if ln.strip():
                lines.append(f"    {ln.strip()}")

    for item in recent:
        block(item)
    if related:
        lines.append("Older conversations related to this message:")
        for item in related:
            block(item)
    lines.append(
        "Use search_conversations or get_conversation for exact details from any of these."
    )
    return "\n".join(lines)
