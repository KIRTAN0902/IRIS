"""Email tools for the IRIS Agent.

Enables IRIS to inspect unread emails across multiple accounts (e.g. personal and work/college),
search messages, fetch full email bodies, create drafts, and send replies.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import Tool
from app.models.user import User
from app.schemas.email import EmailAccountOut, EmailDraftCreate, EmailSendCreate
from app.services import gmail_service


class ListUnreadEmailsParams(BaseModel):
    account_alias: str | None = Field(
        None,
        description="Filter by account alias (e.g. 'personal' or 'work'). If omitted, checks all active accounts.",
    )
    limit: int = Field(10, ge=1, le=50, description="Maximum number of emails to return")


class SearchEmailsParams(BaseModel):
    query: str = Field(
        ...,
        description="Gmail search syntax query (e.g. 'from:prof', 'subject:meeting', 'has:attachment', 'is:starred')",
    )
    account_alias: str | None = Field(
        None,
        description="Filter by account alias (e.g. 'personal' or 'work'). If omitted, searches across all active accounts.",
    )
    limit: int = Field(10, ge=1, le=50, description="Maximum number of emails to return")


class GetEmailDetailsParams(BaseModel):
    account_alias: str = Field(
        ..., description="Account alias that contains this message (e.g. 'personal' or 'work')"
    )
    message_id: str = Field(..., description="Gmail message ID")


class GetEmailAccountsTool(Tool):
    name = "get_email_accounts"
    description = "List all connected email accounts (e.g. personal, work/college), showing alias, email address, and active status."
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        accounts = gmail_service.list_accounts(db, user.id, active_only=False)
        data = [EmailAccountOut.model_validate(a).model_dump(mode="json") for a in accounts]
        active_count = sum(1 for a in accounts if a.is_active)
        summary = f"{len(accounts)} email account(s) connected ({active_count} active): {', '.join(a.alias for a in accounts) or 'none'}"
        return ToolResult(tool_name=self.name, success=True, data=data, summary=summary)


class ListUnreadEmailsTool(Tool):
    name = "list_unread_emails"
    description = (
        "Check unread emails across personal, work, or all connected Gmail accounts. "
        "Returns sender, subject, date, and preview snippet."
    )
    parameters_schema = ListUnreadEmailsParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        account_alias = kwargs.get("account_alias")
        limit = kwargs.get("limit", 10)
        emails = await gmail_service.list_unread_emails(
            db, user, account_alias=account_alias, limit=limit
        )
        data = [e.model_dump(mode="json") for e in emails]
        target = f" in '{account_alias}'" if account_alias else " across all accounts"
        summary = f"Found {len(emails)} unread email(s){target}."
        return ToolResult(tool_name=self.name, success=True, data=data, summary=summary)


class SearchEmailsTool(Tool):
    name = "search_emails"
    description = (
        "Search emails using Gmail search syntax (e.g. from:, subject:, after:, has:attachment) "
        "across personal, work, or all connected accounts."
    )
    parameters_schema = SearchEmailsParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        query = kwargs["query"]
        account_alias = kwargs.get("account_alias")
        limit = kwargs.get("limit", 10)
        emails = await gmail_service.search_emails(
            db, user, query=query, account_alias=account_alias, limit=limit
        )
        data = [e.model_dump(mode="json") for e in emails]
        target = f" in '{account_alias}'" if account_alias else ""
        summary = f"Found {len(emails)} email(s) matching '{query}'{target}."
        return ToolResult(tool_name=self.name, success=True, data=data, summary=summary)


class GetEmailDetailsTool(Tool):
    name = "get_email_details"
    description = "Fetch full body text, headers, and labels for a specific email message."
    parameters_schema = GetEmailDetailsParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        account_alias = kwargs["account_alias"]
        message_id = kwargs["message_id"]
        detail = await gmail_service.get_email_detail(
            db, user, account_alias=account_alias, message_id=message_id
        )
        summary = f"Retrieved email '{detail.subject}' from {detail.sender} ({account_alias})"
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=detail.model_dump(mode="json"),
            summary=summary,
        )


class CreateEmailDraftTool(Tool):
    name = "create_email_draft"
    description = (
        "Create a draft email in Gmail for the user to review and approve before sending. "
        "Specify account_alias ('personal' or 'work')."
    )
    parameters_schema = EmailDraftCreate
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        res = await gmail_service.create_draft(
            db,
            user,
            account_alias=kwargs.get("account_alias"),
            to=kwargs["to"],
            subject=kwargs["subject"],
            body=kwargs["body"],
            cc=kwargs.get("cc"),
            bcc=kwargs.get("bcc"),
        )
        summary = f"Created draft in '{res['account_alias']}' for {res['to']}: '{res['subject']}'"
        return ToolResult(tool_name=self.name, success=True, data=res, summary=summary)


class SendEmailTool(Tool):
    name = "send_email"
    description = (
        "Send an email directly from personal or work Gmail. Destructive: only execute when the user explicitly instructed to send."
    )
    parameters_schema = EmailSendCreate
    read_only = False
    is_destructive = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        res = await gmail_service.send_email(
            db,
            user,
            account_alias=kwargs.get("account_alias"),
            to=kwargs["to"],
            subject=kwargs["subject"],
            body=kwargs["body"],
            cc=kwargs.get("cc"),
            bcc=kwargs.get("bcc"),
        )
        summary = f"Sent email from '{res['account_alias']}' to {res['to']}: '{res['subject']}'"
        return ToolResult(tool_name=self.name, success=True, data=res, summary=summary)


def email_tools() -> list[Tool]:
    """Factory returning all multi-account email agent tools."""
    return [
        GetEmailAccountsTool(),
        ListUnreadEmailsTool(),
        SearchEmailsTool(),
        GetEmailDetailsTool(),
        CreateEmailDraftTool(),
        SendEmailTool(),
    ]
