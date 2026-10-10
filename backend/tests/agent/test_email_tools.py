"""Tests for IRIS agent email tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import Session

from app.agent.registry import default_registry
from app.agent.tools.email import (
    CreateEmailDraftTool,
    GetEmailAccountsTool,
    GetEmailDetailsTool,
    ListUnreadEmailsTool,
    SearchEmailsTool,
    SendEmailTool,
)
from app.core.security import get_current_user
from app.models.email_account import EmailAccount
from app.schemas.email import EmailMessageDetail, EmailMessageSummary


def test_email_tools_registered_in_registry():
    assert default_registry.get("get_email_accounts") is not None
    assert default_registry.get("list_unread_emails") is not None
    assert default_registry.get("search_emails") is not None
    assert default_registry.get("get_email_details") is not None
    assert default_registry.get("create_email_draft") is not None
    assert default_registry.get("send_email") is not None
    assert default_registry.is_mutating("send_email")
    assert not default_registry.is_mutating("list_unread_emails")


@pytest.mark.asyncio
async def test_get_email_accounts_tool(db: Session, user_id: int):
    acc = EmailAccount(
        user_id=user_id,
        alias="personal",
        email_address="kirtan@gmail.com",
        refresh_token="ref-1",
        is_active=True,
    )
    db.add(acc)
    db.commit()
    user = get_current_user(db)

    tool = GetEmailAccountsTool()
    res = await tool.execute(db, user)
    assert res.success
    assert len(res.data) == 1
    assert res.data[0]["alias"] == "personal"
    assert "1 email account" in res.summary


@pytest.mark.asyncio
async def test_list_unread_emails_tool(db: Session, user_id: int):
    user = get_current_user(db)
    tool = ListUnreadEmailsTool()

    mock_summary = [
        EmailMessageSummary(
            id="m1",
            thread_id="t1",
            account_alias="personal",
            account_email="kirtan@gmail.com",
            sender="GitHub <notifications@github.com>",
            subject="Security Alert",
            snippet="A dependency was flagged",
            is_unread=True,
        )
    ]

    with patch("app.services.gmail_service.list_unread_emails", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = mock_summary
        res = await tool.execute(db, user, account_alias="personal", limit=5)
        assert res.success
        assert len(res.data) == 1
        assert res.data[0]["subject"] == "Security Alert"
        assert "Found 1 unread email" in res.summary


@pytest.mark.asyncio
async def test_search_emails_tool(db: Session, user_id: int):
    user = get_current_user(db)
    tool = SearchEmailsTool()

    mock_summary = [
        EmailMessageSummary(
            id="m2",
            thread_id="t2",
            account_alias="college",
            account_email="kirtan@college.edu",
            sender="Registrar <reg@college.edu>",
            subject="Exam Schedule Announced",
            snippet="Final exams begin next week",
            is_unread=False,
        )
    ]

    with patch("app.services.gmail_service.search_emails", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mock_summary
        res = await tool.execute(db, user, query="exam", account_alias="college", limit=5)
        assert res.success
        assert len(res.data) == 1
        assert res.data[0]["subject"] == "Exam Schedule Announced"


@pytest.mark.asyncio
async def test_get_email_details_tool(db: Session, user_id: int):
    user = get_current_user(db)
    tool = GetEmailDetailsTool()

    mock_detail = EmailMessageDetail(
        id="m3",
        thread_id="t3",
        account_alias="work",
        account_email="kirtan@startup.com",
        sender="Investor <partner@vc.com>",
        subject="Term Sheet Review",
        snippet="Please see attached draft",
        body_text="Hi Kirtan, please find our draft terms attached.",
        is_unread=True,
    )

    with patch("app.services.gmail_service.get_email_detail", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_detail
        res = await tool.execute(db, user, account_alias="work", message_id="m3")
        assert res.success
        assert res.data["body_text"] == "Hi Kirtan, please find our draft terms attached."


@pytest.mark.asyncio
async def test_create_email_draft_tool(db: Session, user_id: int):
    user = get_current_user(db)
    tool = CreateEmailDraftTool()

    mock_res = {
        "draft_id": "d-456",
        "account_alias": "personal",
        "to": "friend@example.com",
        "subject": "Catch up",
    }

    with patch("app.services.gmail_service.create_draft", new_callable=AsyncMock) as mock_draft:
        mock_draft.return_value = mock_res
        res = await tool.execute(
            db,
            user,
            account_alias="personal",
            to="friend@example.com",
            subject="Catch up",
            body="Hey, let's grab coffee this Sunday.",
        )
        assert res.success
        assert res.data["draft_id"] == "d-456"
        assert "Created draft" in res.summary


@pytest.mark.asyncio
async def test_send_email_tool(db: Session, user_id: int):
    user = get_current_user(db)
    tool = SendEmailTool()
    assert tool.is_destructive

    mock_res = {
        "message_id": "sent-789",
        "thread_id": "th-789",
        "account_alias": "work",
        "to": "client@acme.com",
        "subject": "Project Proposal",
    }

    with patch("app.services.gmail_service.send_email", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = mock_res
        res = await tool.execute(
            db,
            user,
            account_alias="work",
            to="client@acme.com",
            subject="Project Proposal",
            body="Here is the proposal we discussed.",
        )
        assert res.success
        assert res.data["message_id"] == "sent-789"
        assert "Sent email from 'work'" in res.summary
