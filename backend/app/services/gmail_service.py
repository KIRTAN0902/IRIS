"""Gmail service for multi-account email integration with IRIS.

Connects personal and work/college Gmail accounts using Google Cloud OAuth 2.0
and the Gmail REST API v1 over async HTTPX.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any
import urllib.parse

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError, ValidationAppError
from app.models.email_account import EmailAccount
from app.models.user import User
from app.schemas.email import (
    EmailAccountCreate,
    EmailAccountUpdate,
    EmailMessageDetail,
    EmailMessageSummary,
)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
]


# --- OAuth Utilities ---


def build_auth_url(
    alias: str,
    client_id: str | None = None,
    redirect_uri: str | None = None,
    state: str | None = None,
) -> str:
    """Generate Google OAuth 2.0 authorization URL for a specific account alias."""
    cid = client_id or settings.gmail_client_id
    if not cid:
        raise ValidationAppError(
            "Gmail Client ID is not configured. Set GMAIL_CLIENT_ID in your .env or pass client_id."
        )
    ruri = redirect_uri or settings.gmail_redirect_uri
    query = {
        "client_id": cid,
        "redirect_uri": ruri,
        "response_type": "code",
        "scope": " ".join(DEFAULT_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state or alias,
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(query)}"


async def exchange_code_for_tokens(
    code: str,
    redirect_uri: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> dict[str, Any]:
    """Exchange authorization code from OAuth callback for access and refresh tokens."""
    cid = client_id or settings.gmail_client_id
    secret = client_secret or settings.gmail_client_secret
    ruri = redirect_uri or settings.gmail_redirect_uri

    if not cid or not secret:
        raise ValidationAppError("Google Client ID and Client Secret must be configured.")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": cid,
                "client_secret": secret,
                "redirect_uri": ruri,
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code != 200:
            raise ValidationAppError(
                f"Failed to exchange Google OAuth code: {resp.text}"
            )
        return resp.json()


async def get_valid_access_token(db: Session, account: EmailAccount) -> str:
    """Ensure the email account has a valid access token, auto-refreshing via Google OAuth if expired."""
    now = datetime.now(UTC).replace(tzinfo=None)

    # If we have a cached access token that hasn't expired yet (with a 2-minute buffer)
    if account.access_token and account.token_expiry:
        if account.token_expiry > now + timedelta(seconds=120):
            return account.access_token

    # Token needs refresh
    cid = account.client_id or settings.gmail_client_id
    secret = account.client_secret or settings.gmail_client_secret
    if not cid or not secret:
        raise ValidationAppError(
            f"Cannot refresh token for account '{account.alias}': Google Client ID/Secret not set."
        )

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": cid,
                "client_secret": secret,
                "refresh_token": account.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code != 200:
            raise ValidationAppError(
                f"Failed to refresh Gmail token for '{account.alias}' ({account.email_address}): {resp.text}"
            )
        data = resp.json()
        access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)

        account.access_token = access_token
        account.token_expiry = now + timedelta(seconds=expires_in)
        db.add(account)
        db.commit()
        db.refresh(account)
        return access_token


# --- Account Management ---


def list_accounts(
    db: Session, user_id: int, active_only: bool = True
) -> list[EmailAccount]:
    """List connected email accounts for the user."""
    query = db.query(EmailAccount).filter(EmailAccount.user_id == user_id)
    if active_only:
        query = query.filter(EmailAccount.is_active.is_(True))
    return query.order_by(EmailAccount.alias.asc()).all()


def get_account_by_alias(
    db: Session, user_id: int, alias: str
) -> EmailAccount | None:
    """Fetch an email account by user_id and alias."""
    return (
        db.query(EmailAccount)
        .filter(EmailAccount.user_id == user_id, EmailAccount.alias == alias)
        .first()
    )


def create_or_update_account(
    db: Session, user_id: int, data: EmailAccountCreate
) -> EmailAccount:
    """Register or update an email account with fresh credentials."""
    existing = get_account_by_alias(db, user_id, data.alias)
    if existing:
        existing.email_address = data.email_address
        existing.refresh_token = data.refresh_token
        if data.client_id:
            existing.client_id = data.client_id
        if data.client_secret:
            existing.client_secret = data.client_secret
        if data.scopes:
            existing.scopes = data.scopes
        existing.is_active = data.is_active
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    account = EmailAccount(
        user_id=user_id,
        alias=data.alias,
        email_address=data.email_address,
        provider=data.provider,
        refresh_token=data.refresh_token,
        client_id=data.client_id,
        client_secret=data.client_secret,
        scopes=data.scopes,
        is_active=data.is_active,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def update_account(
    db: Session, user_id: int, alias: str, data: EmailAccountUpdate
) -> EmailAccount:
    """Update settings for an existing account."""
    account = get_account_by_alias(db, user_id, alias)
    if not account:
        raise NotFoundError(f"Email account '{alias}' not found.")
    if data.email_address is not None:
        account.email_address = data.email_address
    if data.is_active is not None:
        account.is_active = data.is_active
    if data.refresh_token is not None:
        account.refresh_token = data.refresh_token
    if data.client_id is not None:
        account.client_id = data.client_id
    if data.client_secret is not None:
        account.client_secret = data.client_secret
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def delete_account(db: Session, user_id: int, alias: str) -> bool:
    """Disconnect and delete an email account."""
    account = get_account_by_alias(db, user_id, alias)
    if not account:
        raise NotFoundError(f"Email account '{alias}' not found.")
    db.delete(account)
    db.commit()
    return True


# --- Parsing Helpers ---


def _decode_body(data_b64: str) -> str:
    try:
        padded = data_b64 + "=" * (-len(data_b64) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode(
            "utf-8", errors="replace"
        )
    except Exception:
        return ""


def _extract_bodies(payload: dict[str, Any]) -> tuple[str, str | None]:
    """Recursively extracts plain text and HTML bodies from a Gmail message payload."""
    body_text = ""
    body_html: str | None = None

    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")

    if body_data:
        decoded = _decode_body(body_data)
        if "text/plain" in mime_type:
            body_text = decoded
        elif "text/html" in mime_type:
            body_html = decoded

    parts = payload.get("parts", [])
    for part in parts:
        part_text, part_html = _extract_bodies(part)
        if part_text and not body_text:
            body_text = part_text
        if part_html and not body_html:
            body_html = part_html

    return body_text, body_html


def _parse_message(
    msg: dict[str, Any], account: EmailAccount, include_body: bool = False
) -> EmailMessageSummary | EmailMessageDetail:
    """Parses a Gmail REST API message object into our Pydantic schema."""
    msg_id = msg.get("id", "")
    thread_id = msg.get("threadId", "")
    snippet = msg.get("snippet", "")
    labels = msg.get("labelIds", [])
    is_unread = "UNREAD" in labels

    headers = {
        h["name"].lower(): h["value"]
        for h in msg.get("payload", {}).get("headers", [])
    }
    sender = headers.get("from", "Unknown Sender")
    recipient = headers.get("to")
    subject = headers.get("subject", "(No Subject)")
    date = headers.get("date")

    if not include_body:
        return EmailMessageSummary(
            id=msg_id,
            thread_id=thread_id,
            account_alias=account.alias,
            account_email=account.email_address,
            sender=sender,
            recipient=recipient,
            subject=subject,
            date=date,
            snippet=snippet,
            is_unread=is_unread,
            labels=labels,
        )

    body_text, body_html = _extract_bodies(msg.get("payload", {}))
    return EmailMessageDetail(
        id=msg_id,
        thread_id=thread_id,
        account_alias=account.alias,
        account_email=account.email_address,
        sender=sender,
        recipient=recipient,
        subject=subject,
        date=date,
        snippet=snippet,
        is_unread=is_unread,
        labels=labels,
        body_text=body_text.strip() or snippet,
        body_html=body_html,
    )


# --- Gmail REST Client Actions ---


async def _fetch_account_messages(
    db: Session,
    account: EmailAccount,
    query: str,
    limit: int = 10,
) -> list[EmailMessageSummary]:
    """Queries messages for a single Gmail account."""
    token = await get_valid_access_token(db, account)
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Step 1: list message IDs
        list_resp = await client.get(
            f"{GMAIL_API_BASE}/messages",
            headers=headers,
            params={"q": query, "maxResults": limit},
        )
        if list_resp.status_code != 200:
            raise ValidationAppError(
                f"Gmail API error for '{account.alias}': {list_resp.text}"
            )
        list_data = list_resp.json()
        items = list_data.get("messages", [])

        # Step 2: fetch details for each message
        summaries: list[EmailMessageSummary] = []
        for itm in items:
            msg_id = itm["id"]
            msg_resp = await client.get(
                f"{GMAIL_API_BASE}/messages/{msg_id}",
                headers=headers,
                params={"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date"]},
            )
            if msg_resp.status_code == 200:
                summary = _parse_message(msg_resp.json(), account, include_body=False)
                summaries.append(summary)  # type: ignore

        return summaries


async def list_unread_emails(
    db: Session,
    user: User,
    account_alias: str | None = None,
    limit: int = 10,
) -> list[EmailMessageSummary]:
    """Fetch unread emails. If account_alias is None, aggregates across all connected accounts."""
    accounts = list_accounts(db, user.id, active_only=True)
    if not accounts:
        return []

    if account_alias:
        target = next((a for a in accounts if a.alias.lower() == account_alias.lower()), None)
        if not target:
            raise NotFoundError(f"Email account '{account_alias}' is not connected or active.")
        return await _fetch_account_messages(db, target, query="is:unread", limit=limit)

    # Fan out across all active accounts
    all_summaries: list[EmailMessageSummary] = []
    for acct in accounts:
        try:
            res = await _fetch_account_messages(db, acct, query="is:unread", limit=limit)
            all_summaries.extend(res)
        except Exception:
            # Continue reading other accounts if one encounters a temporary error
            continue

    return all_summaries[:limit]


async def search_emails(
    db: Session,
    user: User,
    query: str,
    account_alias: str | None = None,
    limit: int = 10,
) -> list[EmailMessageSummary]:
    """Search emails using Gmail search syntax across specific account or all connected accounts."""
    accounts = list_accounts(db, user.id, active_only=True)
    if not accounts:
        return []

    if account_alias:
        target = next((a for a in accounts if a.alias.lower() == account_alias.lower()), None)
        if not target:
            raise NotFoundError(f"Email account '{account_alias}' is not connected or active.")
        return await _fetch_account_messages(db, target, query=query, limit=limit)

    all_summaries: list[EmailMessageSummary] = []
    for acct in accounts:
        try:
            res = await _fetch_account_messages(db, acct, query=query, limit=limit)
            all_summaries.extend(res)
        except Exception:
            continue

    return all_summaries[:limit]


async def get_email_detail(
    db: Session,
    user: User,
    account_alias: str,
    message_id: str,
) -> EmailMessageDetail:
    """Fetch full details and body for a specific email."""
    account = get_account_by_alias(db, user.id, account_alias)
    if not account:
        raise NotFoundError(f"Email account '{account_alias}' not found.")

    token = await get_valid_access_token(db, account)
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{GMAIL_API_BASE}/messages/{message_id}",
            headers=headers,
            params={"format": "full"},
        )
        if resp.status_code != 200:
            raise NotFoundError(f"Email #{message_id} not found in account '{account_alias}'.")
        return _parse_message(resp.json(), account, include_body=True)  # type: ignore


def _build_mime_raw(
    from_email: str,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
) -> str:
    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


async def create_draft(
    db: Session,
    user: User,
    account_alias: str | None,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
) -> dict[str, Any]:
    """Create a draft message in Gmail for review before sending."""
    accounts = list_accounts(db, user.id, active_only=True)
    if not accounts:
        raise ValidationAppError("No active Gmail accounts connected.")

    if account_alias:
        target = next((a for a in accounts if a.alias.lower() == account_alias.lower()), None)
        if not target:
            raise NotFoundError(f"Email account '{account_alias}' not found.")
    else:
        target = accounts[0]

    token = await get_valid_access_token(db, target)
    raw = _build_mime_raw(target.email_address, to, subject, body, cc=cc, bcc=bcc)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{GMAIL_API_BASE}/drafts",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"message": {"raw": raw}},
        )
        if resp.status_code not in (200, 201):
            raise ValidationAppError(f"Failed to create draft in '{target.alias}': {resp.text}")
        data = resp.json()
        return {
            "draft_id": data.get("id"),
            "account_alias": target.alias,
            "account_email": target.email_address,
            "to": to,
            "subject": subject,
        }


async def send_email(
    db: Session,
    user: User,
    account_alias: str | None,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
) -> dict[str, Any]:
    """Send an email directly from the specified account."""
    accounts = list_accounts(db, user.id, active_only=True)
    if not accounts:
        raise ValidationAppError("No active Gmail accounts connected.")

    if account_alias:
        target = next((a for a in accounts if a.alias.lower() == account_alias.lower()), None)
        if not target:
            raise NotFoundError(f"Email account '{account_alias}' not found.")
    else:
        target = accounts[0]

    token = await get_valid_access_token(db, target)
    raw = _build_mime_raw(target.email_address, to, subject, body, cc=cc, bcc=bcc)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{GMAIL_API_BASE}/messages/send",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"raw": raw},
        )
        if resp.status_code not in (200, 201):
            raise ValidationAppError(f"Failed to send email via '{target.alias}': {resp.text}")
        data = resp.json()
        return {
            "message_id": data.get("id"),
            "thread_id": data.get("threadId"),
            "account_alias": target.alias,
            "account_email": target.email_address,
            "to": to,
            "subject": subject,
        }
