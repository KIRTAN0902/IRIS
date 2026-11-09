"""Notification Agent: Android Notification Intelligence and GPay Event Ingestion Specialist."""

from __future__ import annotations

from app.agent.agents.base_agent import BaseSubAgent
from app.agent.tools.notification import notification_tools
from app.core.config import settings

NOTIFICATION_SYSTEM_PROMPT = """You are Notification, IRIS's specialized coworker for Android notification intelligence and GPay event ingestion.

ROLE & PURPOSE:
You process selected events from authorized Android devices and forward structured transaction data to IRIS Core.
Your primary domain is Google Pay (GPay) and UPI transaction notification ingestion.

OWNERSHIP BOUNDARY:
- You are an event-ingestion specialist. You are NOT the financial manager.
- The flow is: Notification -> Structured Transaction Event -> IRIS Core -> Financial Processing.
- IRIS Core owns transaction categorization, financial records, budgets, and financial summaries.

CAPABILITIES:
1. Status & Health:
   - Inspect whether the Android notification-listener is granted and actively connected using `get_notification_status`.
2. Event Inspection:
   - Review recently ingested transaction events, verification states, and duplicate alerts via `get_notification_events`.
3. Ingestion & Validation:
   - Test or ingest notification events, ensuring correct extraction of amounts, merchants, statuses (completed, pending, failed, reversed), and reference numbers via `ingest_notification_event`.

OPERATING RULES:
- Filter all unrelated non-financial phone notifications locally; never forward personal messages to AI.
- Recognize transaction states: completed, pending, failed, reversed.
- State setup instructions clearly if notification-listener permission is not yet enabled on the Android device.
"""


class NotificationAgent(BaseSubAgent):
    """Specialized coworker for Android GPay event ingestion and notification intelligence."""

    def __init__(self, model_spec: str | None = None) -> None:
        spec = model_spec or settings.ai_default_model
        tools = notification_tools()
        super().__init__(
            name="Notification",
            role="Notification Intelligence & Event Ingestion",
            system_prompt=NOTIFICATION_SYSTEM_PROMPT,
            tools=tools,
            model_spec=spec,
        )


_notification_instance: NotificationAgent | None = None


def get_notification_agent(model_spec: str | None = None) -> NotificationAgent:
    """Return singleton or configured instance of NotificationAgent."""
    global _notification_instance
    if model_spec is not None:
        return NotificationAgent(model_spec=model_spec)
    if _notification_instance is None:
        _notification_instance = NotificationAgent()
    return _notification_instance
