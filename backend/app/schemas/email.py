"""Pydantic schemas for multi-account email integration."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EmailAccountBase(BaseModel):
    alias: str = Field(..., min_length=1, max_length=64, description="Unique account alias (e.g. 'personal', 'work', 'college')")
    email_address: str = Field(..., min_length=3, max_length=255, description="Email address")
    provider: str = Field("gmail", description="Email provider ('gmail')")
    is_active: bool = Field(True, description="Whether this account is active")


class EmailAccountCreate(EmailAccountBase):
    refresh_token: str = Field(..., description="OAuth refresh token")
    client_id: str | None = Field(None, description="Optional per-account Google OAuth Client ID")
    client_secret: str | None = Field(None, description="Optional per-account Google OAuth Client Secret")
    scopes: str | None = Field(None, description="Authorized scopes")


class EmailAccountUpdate(BaseModel):
    email_address: str | None = None
    is_active: bool | None = None
    refresh_token: str | None = None
    client_id: str | None = None
    client_secret: str | None = None


class EmailAccountOut(EmailAccountBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_synced_at: datetime | None = None
    created_at: datetime
    has_refresh_token: bool = True


class EmailMessageSummary(BaseModel):
    id: str = Field(..., description="Message ID")
    thread_id: str = Field(..., description="Thread ID")
    account_alias: str = Field(..., description="Account alias ('personal', 'work', etc.)")
    account_email: str = Field(..., description="Account email address")
    sender: str = Field(..., description="From header")
    recipient: str | None = Field(None, description="To header")
    subject: str = Field(..., description="Email subject")
    date: str | None = Field(None, description="Sent date header")
    snippet: str = Field(..., description="Brief snippet or preview of email content")
    is_unread: bool = Field(True, description="Whether the email is currently unread")
    labels: list[str] = Field(default_factory=list, description="Gmail labels attached to this message")


class EmailMessageDetail(EmailMessageSummary):
    body_text: str = Field("", description="Plain text content of the email")
    body_html: str | None = Field(None, description="HTML content if available")


class EmailDraftCreate(BaseModel):
    account_alias: str | None = Field(None, description="Account alias to use (e.g. 'personal' or 'work'). Defaults to primary/first active account.")
    to: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body text")
    cc: str | None = Field(None, description="Optional CC recipient(s)")
    bcc: str | None = Field(None, description="Optional BCC recipient(s)")


class EmailSendCreate(BaseModel):
    account_alias: str | None = Field(None, description="Account alias to send from (e.g. 'personal' or 'work'). Defaults to primary/first active account.")
    to: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body text")
    cc: str | None = Field(None, description="Optional CC recipient(s)")
    bcc: str | None = Field(None, description="Optional BCC recipient(s)")
