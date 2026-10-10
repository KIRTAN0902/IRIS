"""Interactive CLI script to connect a Gmail account to IRIS via Google OAuth.

Usage:
    python scripts/connect_gmail.py --alias personal
    python scripts/connect_gmail.py --alias work
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
from app.services import gmail_service

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
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
                b"""<html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h2 style="color: #10b981;">&#10003; Gmail Authorization Successful!</h2>
                <p>IRIS has captured your authentication token. You can close this browser tab and return to the terminal.</p>
                </body></html>"""
            )
        else:
            error = params.get("error", ["Unknown error"])[0]
            OAuthCallbackHandler.auth_error = error
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                f"""<html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h2 style="color: #ef4444;">Authorization Failed</h2>
                <p>Error: {error}</p>
                </body></html>""".encode("utf-8")
            )

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        # Suppress noisy HTTP request logging
        pass


def run_flow(
    alias: str,
    port: int = 8080,
    custom_client_id: str | None = None,
    custom_client_secret: str | None = None,
) -> None:
    client_id = custom_client_id or settings.gmail_client_id
    client_secret = custom_client_secret or settings.gmail_client_secret

    if not client_id or not client_secret:
        print("[!] Error: Google Client ID and Secret must be provided via arguments or .env.")
        sys.exit(1)

    redirect_uri = f"http://localhost:{port}/"

    query_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": alias,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(query_params)}"

    print("=" * 70)
    print(f" IRIS GMAIL CONNECT: Account Alias '{alias}'")
    print("=" * 70)
    print("\nStarting local listener on port", port)
    server = HTTPServer(("localhost", port), OAuthCallbackHandler)

    print("\nPlease open the following link in your browser to authorize Gmail:")
    print("-" * 70)
    print(auth_url)
    print("-" * 70)

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    print("\nWaiting for authorization callback in browser... (Press Ctrl+C to cancel)")
    while OAuthCallbackHandler.auth_code is None and OAuthCallbackHandler.auth_error is None:
        server.handle_request()

    code = OAuthCallbackHandler.auth_code
    if not code:
        print(f"[!] Authorization failed: {OAuthCallbackHandler.auth_error}")
        sys.exit(1)

    print("[✓] Authorization code received! Exchanging for tokens...")

    # Exchange code for tokens
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

    if not refresh_token:
        print("[!] Warning: Google did not return a refresh token.")
        print("    If you already authorized this app, go to your Google Account permissions,")
        print("    remove access for this app, and run this script again with prompt=consent.")
        sys.exit(1)

    # Fetch email profile
    profile_resp = httpx.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/profile",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    )
    email_address = (
        profile_resp.json().get("emailAddress", "unknown@gmail.com")
        if profile_resp.status_code == 200
        else "unknown@gmail.com"
    )

    # Persist in IRIS database
    db = SessionLocal()
    try:
        user = get_current_user(db)
        now = datetime.now(UTC).replace(tzinfo=None)

        existing = (
            db.query(EmailAccount)
            .filter(EmailAccount.user_id == user.id, EmailAccount.alias == alias)
            .first()
        )

        if existing:
            existing.email_address = email_address
            existing.refresh_token = refresh_token
            existing.access_token = access_token
            existing.token_expiry = now + timedelta(seconds=expires_in)
            if custom_client_id:
                existing.client_id = custom_client_id
            if custom_client_secret:
                existing.client_secret = custom_client_secret
            existing.is_active = True
            db.add(existing)
            action = "Updated"
        else:
            new_acc = EmailAccount(
                user_id=user.id,
                alias=alias,
                email_address=email_address,
                provider="gmail",
                refresh_token=refresh_token,
                access_token=access_token,
                token_expiry=now + timedelta(seconds=expires_in),
                client_id=custom_client_id,
                client_secret=custom_client_secret,
                is_active=True,
            )
            db.add(new_acc)
            action = "Connected"

        db.commit()
        print("\n" + "=" * 70)
        print(f"[✓] SUCCESS: {action} Gmail account in IRIS!")
        print(f"    Alias:         {alias}")
        print(f"    Email Address: {email_address}")
        print(f"    Scopes:        All Gmail read, write, draft & send scopes active")
        print("=" * 70)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Connect a Gmail account to IRIS.")
    parser.add_argument(
        "--alias",
        default="personal",
        help="Account alias ('personal', 'work', 'college'). Default: 'personal'",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Local redirect listener port. Default: 8080",
    )
    parser.add_argument(
        "--credentials-file",
        default=None,
        help="Path to a downloaded client_secret_*.json from Google Cloud Console.",
    )
    parser.add_argument(
        "--client-id",
        default=None,
        help="Optional custom Google OAuth Client ID for this account.",
    )
    parser.add_argument(
        "--client-secret",
        default=None,
        help="Optional custom Google OAuth Client Secret for this account.",
    )
    args = parser.parse_args()

    client_id = args.client_id
    client_secret = args.client_secret

    if args.credentials_file:
        import json
        with open(args.credentials_file, encoding="utf-8") as f:
            secret_data = json.load(f)
        cfg = secret_data.get("web") or secret_data.get("installed") or {}
        client_id = cfg.get("client_id") or client_id
        client_secret = cfg.get("client_secret") or client_secret

    run_flow(
        alias=args.alias,
        port=args.port,
        custom_client_id=client_id,
        custom_client_secret=client_secret,
    )
