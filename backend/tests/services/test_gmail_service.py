"""Tests for multi-account Gmail service."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.models.email_account import EmailAccount
from app.schemas.email import EmailAccountCreate, EmailAccountUpdate
from app.services import gmail_service


def test_multi_account_crud(db: Session, user_id: int):
    # Register 2 email accounts (personal & startup/work)
    acc1 = gmail_service.create_or_update_account(
        db,
        user_id,
        EmailAccountCreate(
            alias="personal",
            email_address="kirtan.personal@gmail.com",
            refresh_token="mock-refresh-personal",
        ),
    )
    assert acc1.id is not None
    assert acc1.alias == "personal"

    acc2 = gmail_service.create_or_update_account(
        db,
        user_id,
        EmailAccountCreate(
            alias="work",
            email_address="kirtan.work@gmail.com",
            refresh_token="mock-refresh-work",
        ),
    )
    assert acc2.id is not None
    assert acc2.alias == "work"

    # List accounts
    accounts = gmail_service.list_accounts(db, user_id)
    assert len(accounts) == 2
    aliases = [a.alias for a in accounts]
    assert "personal" in aliases
    assert "work" in aliases

    # Update account
    updated = gmail_service.update_account(
        db, user_id, "personal", EmailAccountUpdate(is_active=False)
    )
    assert not updated.is_active

    active = gmail_service.list_accounts(db, user_id, active_only=True)
    assert len(active) == 1
    assert active[0].alias == "work"

    # Delete account
    gmail_service.delete_account(db, user_id, "work")
    remaining = gmail_service.list_accounts(db, user_id, active_only=False)
    assert len(remaining) == 1
    assert remaining[0].alias == "personal"


def test_build_auth_url(monkeypatch):
    monkeypatch.setattr(gmail_service.settings, "gmail_client_id", "test-client-id-123")
    monkeypatch.setattr(
        gmail_service.settings,
        "gmail_redirect_uri",
        "http://localhost:8000/api/email/auth/callback",
    )

    url = gmail_service.build_auth_url(alias="personal")
    assert "test-client-id-123" in url
    assert "state=personal" in url
    assert "gmail.modify" in url


@pytest.mark.asyncio
async def test_get_valid_access_token_cached(db: Session, user_id: int):
    # Account with valid unexpired token returns cached token without network call
    future = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=30)
    acc = EmailAccount(
        user_id=user_id,
        alias="personal",
        email_address="test@gmail.com",
        refresh_token="ref-123",
        access_token="cached-token-abc",
        token_expiry=future,
        client_id="cid",
        client_secret="sec",
    )
    db.add(acc)
    db.commit()

    token = await gmail_service.get_valid_access_token(db, acc)
    assert token == "cached-token-abc"


@pytest.mark.asyncio
async def test_get_valid_access_token_refresh(db: Session, user_id: int, monkeypatch):
    past = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
    acc = EmailAccount(
        user_id=user_id,
        alias="work",
        email_address="work@gmail.com",
        refresh_token="ref-refresh",
        access_token="old-token",
        token_expiry=past,
        client_id="cid",
        client_secret="sec",
    )
    db.add(acc)
    db.commit()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "new-refreshed-token", "expires_in": 3600}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        token = await gmail_service.get_valid_access_token(db, acc)
        assert token == "new-refreshed-token"
        assert acc.access_token == "new-refreshed-token"
        assert acc.token_expiry is not None


@pytest.mark.asyncio
async def test_list_unread_and_search_multi_account(db: Session, user_id: int):
    # Connect 2 accounts
    now = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
    acc1 = EmailAccount(
        user_id=user_id,
        alias="personal",
        email_address="p@gmail.com",
        refresh_token="r1",
        access_token="tok1",
        token_expiry=now,
    )
    acc2 = EmailAccount(
        user_id=user_id,
        alias="college",
        email_address="c@college.edu",
        refresh_token="r2",
        access_token="tok2",
        token_expiry=now,
    )
    db.add_all([acc1, acc2])
    db.commit()

    mock_msg_list = {"messages": [{"id": "msg-1"}]}
    mock_msg_detail = {
        "id": "msg-1",
        "threadId": "th-1",
        "snippet": "Assignment 2 is posted",
        "labelIds": ["UNREAD", "INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": "Professor <prof@college.edu>"},
                {"name": "Subject", "value": "Assignment 2"},
                {"name": "Date", "value": "Sat, 10 Oct 2026 12:00:00 +0000"},
            ]
        },
    }

    user = get_current_user(db)

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        resp_list = MagicMock(status_code=200)
        resp_list.json.return_value = mock_msg_list
        resp_detail = MagicMock(status_code=200)
        resp_detail.json.return_value = mock_msg_detail

        mock_get.side_effect = [resp_list, resp_detail, resp_list, resp_detail]

        emails = await gmail_service.list_unread_emails(db, user, account_alias=None, limit=10)
        assert len(emails) >= 1
        assert emails[0].subject == "Assignment 2"
        assert emails[0].sender == "Professor <prof@college.edu>"


@pytest.mark.asyncio
async def test_create_draft_and_send(db: Session, user_id: int):
    now = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
    acc = EmailAccount(
        user_id=user_id,
        alias="startup",
        email_address="founder@startup.com",
        refresh_token="r-startup",
        access_token="tok-startup",
        token_expiry=now,
    )
    db.add(acc)
    db.commit()
    user = get_current_user(db)

    # Draft test
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        resp_draft = MagicMock(status_code=200)
        resp_draft.json.return_value = {"id": "draft-99"}
        mock_post.return_value = resp_draft

        draft = await gmail_service.create_draft(
            db,
            user,
            account_alias="startup",
            to="investor@fund.com",
            subject="IRIS Demo",
            body="Here is the link to our demo.",
        )
        assert draft["draft_id"] == "draft-99"
        assert draft["account_alias"] == "startup"

    # Send test
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        resp_send = MagicMock(status_code=200)
        resp_send.json.return_value = {"id": "sent-msg-101", "threadId": "th-101"}
        mock_post.return_value = resp_send

        sent = await gmail_service.send_email(
            db,
            user,
            account_alias="startup",
            to="investor@fund.com",
            subject="IRIS Demo",
            body="Here is the link to our demo.",
        )
        assert sent["message_id"] == "sent-msg-101"
        assert sent["account_alias"] == "startup"
