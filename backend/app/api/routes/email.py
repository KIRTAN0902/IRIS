"""FastAPI routes for multi-account email integration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.email import (
    EmailAccountCreate,
    EmailAccountOut,
    EmailAccountUpdate,
    EmailDraftCreate,
    EmailMessageDetail,
    EmailMessageSummary,
    EmailSendCreate,
)
from app.services import gmail_service

router = APIRouter(prefix="/email", tags=["email"])


@router.get("/accounts", response_model=list[EmailAccountOut])
def list_accounts(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    active_only: bool = False,
):
    """List connected email accounts for the user."""
    accounts = gmail_service.list_accounts(db, user.id, active_only=active_only)
    return [EmailAccountOut.model_validate(a) for a in accounts]


@router.post("/accounts", response_model=EmailAccountOut, status_code=status.HTTP_201_CREATED)
def create_account(
    data: EmailAccountCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Register or update an email account with OAuth tokens."""
    account = gmail_service.create_or_update_account(db, user.id, data)
    return EmailAccountOut.model_validate(account)


@router.patch("/accounts/{alias}", response_model=EmailAccountOut)
def update_account(
    alias: str,
    data: EmailAccountUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Update settings or state for an existing email account."""
    account = gmail_service.update_account(db, user.id, alias, data)
    return EmailAccountOut.model_validate(account)


@router.delete("/accounts/{alias}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    alias: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Disconnect and remove an email account."""
    gmail_service.delete_account(db, user.id, alias)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/url")
def get_auth_url(
    alias: str = Query("personal", description="Alias for this account, e.g. 'personal' or 'work'"),
    redirect_uri: str | None = None,
    user: User = Depends(current_user),
):
    """Get the Google OAuth 2.0 authorization URL for connecting a Gmail account."""
    url = gmail_service.build_auth_url(
        alias=alias,
        redirect_uri=redirect_uri,
        state=f"{user.id}:{alias}",
    )
    return {"url": url, "alias": alias}


@router.get("/auth/callback", response_class=HTMLResponse)
async def auth_callback(
    code: str,
    state: str,
    redirect_uri: str | None = None,
    db: Session = Depends(get_db),
):
    """OAuth 2.0 callback endpoint. Exchanges authorization code for tokens and persists the account."""
    tokens = await gmail_service.exchange_code_for_tokens(code=code, redirect_uri=redirect_uri)
    refresh_token = tokens.get("refresh_token")

    user_id_str, _, alias = state.partition(":")
    user_id = int(user_id_str) if user_id_str.isdigit() else 1
    alias = alias or "personal"

    if not refresh_token:
        # Prompt consent might have been bypassed; we still need a refresh token
        return HTMLResponse(
            "<h3>Warning: Google did not return a refresh_token.</h3>"
            "<p>Please revoke application access in your Google Account security settings and retry to grant offline access.</p>",
            status_code=400,
        )

    # Use access token to fetch user profile email address
    import httpx
    async with httpx.AsyncClient(timeout=10.0) as client:
        profile_resp = await client.get(
            f"{gmail_service.GMAIL_API_BASE}/profile",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        email_addr = (
            profile_resp.json().get("emailAddress", f"{alias}@gmail.com")
            if profile_resp.status_code == 200
            else f"{alias}@gmail.com"
        )

    create_data = EmailAccountCreate(
        alias=alias,
        email_address=email_addr,
        refresh_token=refresh_token,
        scopes=tokens.get("scope"),
        is_active=True,
    )
    gmail_service.create_or_update_account(db, user_id, create_data)

    return HTMLResponse(
        f"<h2>Success! Connected '{alias}' ({email_addr}) to IRIS.</h2>"
        "<p>You can close this window now and return to IRIS.</p>"
    )


@router.get("/unread", response_model=list[EmailMessageSummary])
async def list_unread(
    account_alias: str | None = None,
    limit: int = 10,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Fetch unread emails across one or all accounts."""
    return await gmail_service.list_unread_emails(
        db, user, account_alias=account_alias, limit=limit
    )


@router.get("/search", response_model=list[EmailMessageSummary])
async def search_messages(
    q: str = Query(..., description="Gmail search query string"),
    account_alias: str | None = None,
    limit: int = 10,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Search messages across accounts using Gmail search syntax."""
    return await gmail_service.search_emails(
        db, user, query=q, account_alias=account_alias, limit=limit
    )


@router.get("/messages/{alias}/{message_id}", response_model=EmailMessageDetail)
async def get_message_detail(
    alias: str,
    message_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Get full body and headers of a specific email."""
    return await gmail_service.get_email_detail(
        db, user, account_alias=alias, message_id=message_id
    )


@router.post("/drafts")
async def create_draft(
    data: EmailDraftCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Create a draft in Gmail."""
    return await gmail_service.create_draft(
        db,
        user,
        account_alias=data.account_alias,
        to=data.to,
        subject=data.subject,
        body=data.body,
        cc=data.cc,
        bcc=data.bcc,
    )


@router.post("/send")
async def send_email(
    data: EmailSendCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Send an email via Gmail."""
    return await gmail_service.send_email(
        db,
        user,
        account_alias=data.account_alias,
        to=data.to,
        subject=data.subject,
        body=data.body,
        cc=data.cc,
        bcc=data.bcc,
    )
