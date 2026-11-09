"""Slack Workspace Service for Workspace Coworker."""

from __future__ import annotations

import os
from typing import Any
import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("iris.services.slack")

SLACK_API_BASE = "https://slack.com/api"


class SlackService:
    """Interacts with authorized Slack workspaces for search, retrieval, and message drafting."""

    def __init__(self) -> None:
        pass

    def _get_token(self, db: Session | None = None, user_id: int | None = None) -> str | None:
        """Resolve active Slack OAuth token from environment or user settings."""
        token = (
            getattr(settings, "slack_bot_token", None)
            or getattr(settings, "slack_user_token", None)
            or os.getenv("SLACK_BOT_TOKEN")
            or os.getenv("SLACK_USER_TOKEN")
        )
        return token.strip() if token else None

    def is_configured(self, db: Session | None = None, user_id: int | None = None) -> bool:
        """Check whether Slack integration has an authorized token configured."""
        return self._get_token(db, user_id) is not None

    def get_status(self, db: Session | None = None, user_id: int | None = None) -> dict[str, Any]:
        """Return factual connection status for Slack integration."""
        token = self._get_token(db, user_id)
        if not token:
            return {
                "is_connected": False,
                "message": (
                    "Slack is not connected yet. Configure SLACK_BOT_TOKEN or connect your "
                    "Slack workspace in Settings."
                ),
            }
        return {
            "is_connected": True,
            "message": "Slack workspace connected",
            "token_type": "bot" if token.startswith("xoxb-") else "user" if token.startswith("xoxp-") else "custom",
        }

    async def list_channels(
        self,
        db: Session | None = None,
        user_id: int | None = None,
        types: str = "public_channel,private_channel",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List accessible channels in the authorized workspace."""
        token = self._get_token(db, user_id)
        if not token:
            return []

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{SLACK_API_BASE}/conversations.list",
                headers={"Authorization": f"Bearer {token}"},
                params={"types": types, "limit": min(limit, 100)},
            )
            data = resp.json()
            if not data.get("ok"):
                logger.warning("Slack list_channels failed: %s", data.get("error"))
                return []
            return [
                {
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "is_private": c.get("is_private", False),
                    "topic": (c.get("topic") or {}).get("value", ""),
                    "purpose": (c.get("purpose") or {}).get("value", ""),
                    "num_members": c.get("num_members", 0),
                }
                for c in data.get("channels", [])
            ]

    async def search_messages(
        self,
        query: str,
        db: Session | None = None,
        user_id: int | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search Slack messages across accessible channels in the authorized workspace."""
        token = self._get_token(db, user_id)
        if not token:
            return []

        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. Try search.messages endpoint (requires search:read scope)
            resp = await client.get(
                f"{SLACK_API_BASE}/search.messages",
                headers={"Authorization": f"Bearer {token}"},
                params={"query": query, "count": min(limit, 50)},
            )
            data = resp.json()
            if data.get("ok"):
                matches = (data.get("messages") or {}).get("matches", [])
                return [
                    {
                        "channel": m.get("channel", {}).get("name") or m.get("channel", {}).get("id"),
                        "username": m.get("username"),
                        "text": m.get("text"),
                        "permalink": m.get("permalink"),
                        "ts": m.get("ts"),
                    }
                    for m in matches
                ]

            # 2. Fallback: Search across list_channels conversation history if search.messages not granted
            logger.info("search.messages unavailable (%s); searching channel history fallback", data.get("error"))
            channels = await self.list_channels(db, user_id, limit=5)
            results: list[dict[str, Any]] = []
            query_lower = query.lower()
            for ch in channels:
                hist = await self.get_channel_history(ch["id"], db=db, user_id=user_id, limit=15)
                for msg in hist:
                    if query_lower in (msg.get("text") or "").lower():
                        results.append({
                            "channel": ch["name"],
                            "username": msg.get("user") or "user",
                            "text": msg.get("text"),
                            "ts": msg.get("ts"),
                        })
                        if len(results) >= limit:
                            break
                if len(results) >= limit:
                    break
            return results

    async def get_channel_history(
        self,
        channel_id: str,
        db: Session | None = None,
        user_id: int | None = None,
        limit: int = 15,
    ) -> list[dict[str, Any]]:
        """Retrieve recent message history from a specific Slack channel."""
        token = self._get_token(db, user_id)
        if not token:
            return []

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{SLACK_API_BASE}/conversations.history",
                headers={"Authorization": f"Bearer {token}"},
                params={"channel": channel_id, "limit": min(limit, 50)},
            )
            data = resp.json()
            if not data.get("ok"):
                logger.warning("Slack get_channel_history failed for %s: %s", channel_id, data.get("error"))
                return []
            return [
                {
                    "user": m.get("user"),
                    "text": m.get("text"),
                    "ts": m.get("ts"),
                    "thread_ts": m.get("thread_ts"),
                    "reply_count": m.get("reply_count", 0),
                }
                for m in data.get("messages", [])
            ]

    def draft_message(self, channel: str, text: str) -> dict[str, Any]:
        """Prepare a structured draft message for user review before sending."""
        return {
            "status": "draft_created",
            "channel": channel,
            "text": text,
            "requires_user_confirmation": True,
            "message": f"Draft prepared for #{channel}: \"{text[:80]}...\". Ready for your review.",
        }

    async def post_message(
        self,
        channel: str,
        text: str,
        db: Session | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Post a message directly to an authorized Slack channel."""
        token = self._get_token(db, user_id)
        if not token:
            return {
                "success": False,
                "error": "Slack is not connected. Configure SLACK_BOT_TOKEN first.",
            }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{SLACK_API_BASE}/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json={"channel": channel, "text": text},
            )
            data = resp.json()
            if not data.get("ok"):
                return {"success": False, "error": data.get("error", "Unknown Slack error")}
            return {
                "success": True,
                "channel": channel,
                "ts": data.get("ts"),
                "message": f"Message posted successfully to {channel}.",
            }


slack_service = SlackService()
