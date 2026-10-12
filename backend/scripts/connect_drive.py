"""Interactive CLI script to connect Google Drive to IRIS via Google OAuth 2.0.

Usage:
    python scripts/connect_drive.py
    python scripts/connect_drive.py --alias personal_drive --port 8085
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import sys
from urllib.parse import parse_qs, urlencode, urlparse
import webbrowser

# Add backend directory to path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import httpx
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import get_current_user
from app.models.email_account import EmailAccount

DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    auth_code: str | None = None
    auth_error: str | None = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"""<html><body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; text-align: center; padding: 60px; background: #09090b; color: #f4f4f5;">
                <div style="max-width: 500px; margin: 0 auto; background: #18181b; border: 1px solid #27272a; border-radius: 16px; padding: 32px; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);">
                    <div style="font-size: 40px; margin-bottom: 16px;">&#10004;</div>
                    <h2 style="color: #10b981; margin: 0 0 12px 0;">Google Drive Connected to IRIS!</h2>
                    <p style="color: #a1a1aa; font-size: 14px; line-height: 1.5; margin: 0 0 24px 0;">
                        IRIS has securely captured your authentication tokens. You can close this browser tab and return to the terminal.
                    </p>
                    <div style="font-size: 12px; color: #71717a; border-top: 1px solid #27272a; padding-top: 16px;">
                        IRIS Sovereign Autonomous Intelligence
                    </div>
                </div>
                </body></html>"""
            )
        else:
            error = params.get("error", ["Unknown error"])[0]
            OAuthCallbackHandler.auth_error = error
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<html><body><h2>Authorization Failed: {error}</h2></body></html>".encode("utf-8"))

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


def run_flow(
    alias: str = "personal_drive",
    port: int = 8085,
    custom_client_id: str | None = None,
    custom_client_secret: str | None = None,
) -> None:
    client_id = (
        custom_client_id
        or settings.google_drive_client_id
        or settings.gmail_client_id
    )
    client_secret = (
        custom_client_secret
        or settings.google_drive_client_secret
        or settings.gmail_client_secret
    )

    if not client_id or not client_secret:
        print("[!] Error: Google Client ID and Secret must be provided in backend/.env (GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET).")
        sys.exit(1)

    redirect_uri = f"http://localhost:{port}/"

    query_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(DRIVE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": alias,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(query_params)}"

    print("=" * 70)
    print(" IRIS GOOGLE DRIVE CONNECT")
    print("=" * 70)
    print(f"Target Alias : {alias}")
    print(f"Redirect URI : {redirect_uri}")
    print("\nStarting local listener on port", port)
    server = HTTPServer(("localhost", port), OAuthCallbackHandler)

    print("\nPlease open the following link in your browser to authorize Google Drive:")
    print("-" * 70)
    print(auth_url)
    print("-" * 70)

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    print("\nWaiting for authorization in your browser... (Press Ctrl+C to cancel)")
    while OAuthCallbackHandler.auth_code is None and OAuthCallbackHandler.auth_error is None:
        server.handle_request()

    code = OAuthCallbackHandler.auth_code
    if not code:
        print(f"[!] Authorization failed: {OAuthCallbackHandler.auth_error}")
        sys.exit(1)

    print("[✓] Authorization code received! Exchanging for tokens...")

    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=15.0,
    )

    if resp.status_code != 200:
        print(f"[!] Failed to exchange code with Google: {resp.text}")
        sys.exit(1)

    token_data = resp.json()
    refresh_token = token_data.get("refresh_token")
    access_token = token_data.get("access_token")
    expires_in = token_data.get("expires_in", 3600)
    granted_scopes = token_data.get("scope", "")

    if not refresh_token:
        print("[!] Warning: Google did not return a refresh token.")
        print("    If you already authorized this app, go to your Google Account permissions,")
        print("    revoke access for this OAuth client, and run this script again.")

    # Fetch email profile
    profile_resp = httpx.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    )
    email_address = "unknown@google.com"
    if profile_resp.status_code == 200:
        email_address = profile_resp.json().get("email", email_address)

    print(f"[✓] Successfully authenticated as: {email_address}")

    # Store in database
    db = SessionLocal()
    try:
        user = get_current_user(db)
        now = datetime.now(UTC)
        expiry = now + timedelta(seconds=expires_in)

        # Check existing account by alias or email
        account = (
            db.query(EmailAccount)
            .filter(EmailAccount.user_id == user.id, EmailAccount.alias == alias)
            .first()
        )
        if not account:
            account = (
                db.query(EmailAccount)
                .filter(EmailAccount.user_id == user.id, EmailAccount.email_address == email_address)
                .first()
            )

        if account:
            if refresh_token:
                account.refresh_token = refresh_token
            account.access_token = access_token
            account.token_expiry = expiry
            account.scopes = granted_scopes
            account.is_active = True
            print(f"[✓] Updated existing account record '{account.alias}' in database.")
        else:
            account = EmailAccount(
                user_id=user.id,
                alias=alias,
                email_address=email_address,
                provider="google_drive",
                refresh_token=refresh_token or "",
                access_token=access_token,
                token_expiry=expiry,
                scopes=granted_scopes,
                is_active=True,
            )
            db.add(account)
            print(f"[✓] Created new account record '{alias}' ({email_address}) in database.")

        db.commit()
        print("\n" + "=" * 70)
        print(" SUCCESS! Google Drive is now fully connected to IRIS.")
        print("=" * 70)
        print("You can now ask IRIS via voice or chat:")
        print("  - 'List my Google Drive files'")
        print("  - 'Search Google Drive for <topic>'")
        print("  - 'Read Google Drive document <name>'")
        print("  - 'Upload <file> to Google Drive'")
        print("=" * 70)

    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect Google Drive to IRIS via Google OAuth 2.0")
    parser.add_argument("--alias", default="personal_drive", help="Account alias (default: personal_drive)")
    parser.add_argument("--port", type=int, default=8085, help="Local HTTP listener port (default: 8085)")
    parser.add_argument("--client-id", help="Optional custom Google Client ID override")
    parser.add_argument("--client-secret", help="Optional custom Google Client Secret override")
    args = parser.parse_args()

    run_flow(
        alias=args.alias,
        port=args.port,
        custom_client_id=args.client_id,
        custom_client_secret=args.client_secret,
    )


if __name__ == "__main__":
    main()
