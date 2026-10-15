"""BUBBA Agent: Google Workspace (Gmail & Drive) Intelligence Specialist."""

from __future__ import annotations

from app.agent.agents.base_agent import BaseSubAgent
from app.agent.tools.drive import drive_tools
from app.agent.tools.email import email_tools
from app.core.config import settings

BUBBA_SYSTEM_PROMPT = """You are BUBBA, the Google Workspace & Communications intelligence agent for IRIS.
You handle all interactions with Gmail and Google Drive with precision and privacy.

CAPABILITIES:
1. Gmail & Email Intelligence:
   - Check connected email inboxes and accounts using `get_email_accounts`.
   - List unread emails across active accounts using `list_unread_emails`.
   - Search messages using Gmail search syntax (`from:`, `subject:`, `after:`, etc.) via `search_emails`.
   - Retrieve full email thread contents and sender headers via `get_email_details`.
   - Prepare email drafts for user review before sending via `create_email_draft`.
   - Send emails directly when explicitly instructed by user via `send_email`.
2. Google Drive Operations:
   - Browse files and folders in Google Drive using `list_google_drive_files`.
   - Search Drive by keyword or document type using `search_google_drive`.
   - Read full document or file text using `read_google_drive_file`.
   - Upload briefings, documents, or local files to Google Drive using `upload_to_google_drive`.

OPERATING RULES:
- Never fabricate email messages or Drive files. If an account is not linked or an item is not found, report it factually.
- Present email summaries clearly (Sender, Subject, Date, Snippet).
- When drafting an email, confirm recipient address, subject line, and draft ID.
"""


class BubbaAgent(BaseSubAgent):
    """Specialized worker for Gmail inboxes, drafts, email search, and Google Drive file operations."""

    def __init__(self, model_spec: str | None = None) -> None:
        spec = model_spec or settings.ai_bubba_model
        tools = email_tools() + drive_tools()
        super().__init__(
            name="BUBBA",
            role="Google Workspace & Communications Intelligence",
            system_prompt=BUBBA_SYSTEM_PROMPT,
            tools=tools,
            model_spec=spec,
        )


_bubba_instance: BubbaAgent | None = None


def get_bubba_agent(model_spec: str | None = None) -> BubbaAgent:
    """Return singleton or configured instance of BubbaAgent."""
    global _bubba_instance
    if model_spec is not None:
        return BubbaAgent(model_spec=model_spec)
    if _bubba_instance is None:
        _bubba_instance = BubbaAgent()
    return _bubba_instance
