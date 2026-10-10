"""Tests for Email API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.email_account import EmailAccount
from app.schemas.email import EmailMessageSummary


def test_email_accounts_api(client: TestClient, db: Session, user_id: int):
    # GET accounts (initially empty)
    res = client.get("/api/email/accounts")
    assert res.status_code == 200
    assert res.json() == []

    # POST create account 1 (personal)
    res = client.post(
        "/api/email/accounts",
        json={
            "alias": "personal",
            "email_address": "kirtan.personal@gmail.com",
            "provider": "gmail",
            "refresh_token": "mock-ref-1",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["alias"] == "personal"
    assert data["email_address"] == "kirtan.personal@gmail.com"

    # POST create account 2 (work)
    res = client.post(
        "/api/email/accounts",
        json={
            "alias": "work",
            "email_address": "kirtan.work@gmail.com",
            "provider": "gmail",
            "refresh_token": "mock-ref-2",
        },
    )
    assert res.status_code == 201

    # GET accounts
    res = client.get("/api/email/accounts")
    assert res.status_code == 200
    assert len(res.json()) == 2

    # PATCH account
    res = client.patch("/api/email/accounts/personal", json={"is_active": False})
    assert res.status_code == 200
    assert res.json()["is_active"] is False

    # DELETE account
    res = client.delete("/api/email/accounts/work")
    assert res.status_code == 204

    res = client.get("/api/email/accounts")
    assert len(res.json()) == 1


def test_auth_url_api(client: TestClient, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "gmail_client_id", "mock-client-id-api")
    res = client.get("/api/email/auth/url?alias=college")
    assert res.status_code == 200
    data = res.json()
    assert "mock-client-id-api" in data["url"]
    assert data["alias"] == "college"


def test_email_unread_and_search_api(client: TestClient):
    mock_summary = [
        EmailMessageSummary(
            id="m-api-1",
            thread_id="t-api-1",
            account_alias="personal",
            account_email="kirtan@gmail.com",
            sender="GitHub <notifications@github.com>",
            subject="New PR comment",
            snippet="Looks good to merge",
            is_unread=True,
        )
    ]

    with patch("app.services.gmail_service.list_unread_emails", new_callable=AsyncMock) as mock_unread:
        mock_unread.return_value = mock_summary
        res = client.get("/api/email/unread?account_alias=personal")
        assert res.status_code == 200
        assert len(res.json()) == 1
        assert res.json()[0]["subject"] == "New PR comment"

    with patch("app.services.gmail_service.search_emails", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mock_summary
        res = client.get("/api/email/search?q=github")
        assert res.status_code == 200
        assert len(res.json()) == 1
        assert res.json()[0]["subject"] == "New PR comment"
