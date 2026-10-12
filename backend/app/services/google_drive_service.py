"""Google Drive service for IRIS.

Enables the AI Assistant and user to:
1. Search and list files and folders in Google Drive.
2. Read and retrieve text documents, notes, CSVs, and Google Docs directly.
3. Upload notes, briefings, project assets, and local laptop files to Google Drive (and into NotebookLM source folders).
4. Connect via Google Cloud OAuth 2.0.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import io
import mimetypes
import os
from pathlib import Path
from typing import Any
import urllib.parse

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.models.email_account import EmailAccount
from app.models.user import User

logger = get_logger(__name__)

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive",
]


class GoogleDriveService:
    """Async service interacting with Google Drive REST API v3."""

    def _get_client_credentials(self, account: EmailAccount | None = None) -> tuple[str, str]:
        cid = (
            (account.client_id if account else None)
            or settings.google_drive_client_id
            or settings.gmail_client_id
        )
        csec = (
            (account.client_secret if account else None)
            or settings.google_drive_client_secret
            or settings.gmail_client_secret
        )
        if not cid or not csec:
            raise ValidationAppError(
                "Google Client credentials not configured. Please set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in backend/.env."
            )
        return cid, csec

    def get_drive_account(self, db: Session, user_id: int) -> EmailAccount | None:
        """Finds the EmailAccount record with Google Drive authorization."""
        # 1. Look for dedicated google_drive account
        acc = (
            db.query(EmailAccount)
            .filter(
                EmailAccount.user_id == user_id,
                EmailAccount.provider == "google_drive",
                EmailAccount.is_active.is_(True),
            )
            .first()
        )
        if acc and acc.refresh_token:
            return acc

        # 2. Look for any active Google account that has 'drive' scope in granted scopes
        accs = (
            db.query(EmailAccount)
            .filter(
                EmailAccount.user_id == user_id,
                EmailAccount.is_active.is_(True),
            )
            .all()
        )
        for a in accs:
            if a.refresh_token and a.scopes and "drive" in a.scopes.lower():
                return a

        return None

    async def get_valid_access_token(self, db: Session, user_id: int) -> tuple[str, EmailAccount]:
        """Returns a guaranteed-fresh Google OAuth access token."""
        account = self.get_drive_account(db, user_id)
        if not account or not account.refresh_token:
            raise ValidationAppError(
                "Google Drive is not connected yet. Run `python scripts/connect_drive.py` or authorize Drive in Settings."
            )

        now = datetime.now(UTC)
        expiry = account.token_expiry
        if expiry and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)

        # If token is still valid for at least 2 minutes, reuse it
        if (
            account.access_token
            and expiry
            and expiry > now + timedelta(minutes=2)
        ):
            return account.access_token, account

        # Refresh token
        cid, csec = self._get_client_credentials(account)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": cid,
                    "client_secret": csec,
                    "refresh_token": account.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            if resp.status_code != 200:
                logger.error("Failed to refresh Google Drive token: %s", resp.text)
                raise ValidationAppError(
                    f"Google token refresh failed ({resp.status_code}). Reconnection may be required: {resp.text[:200]}"
                )

            data = resp.json()
            new_token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)
            scope = data.get("scope")

            account.access_token = new_token
            account.token_expiry = now + timedelta(seconds=expires_in)
            if scope:
                account.scopes = scope
            db.commit()
            db.refresh(account)

            return new_token, account

    def build_auth_url(
        self,
        alias: str = "personal_drive",
        redirect_uri: str = "http://localhost:8085/",
        client_id: str | None = None,
    ) -> str:
        """Generates the Google OAuth consent URL for Drive."""
        cid = client_id or settings.google_drive_client_id or settings.gmail_client_id
        if not cid:
            raise ValidationAppError("Google Client ID is not configured.")

        params = {
            "client_id": cid,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(DRIVE_SCOPES + [
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile",
            ]),
            "access_type": "offline",
            "prompt": "consent",
            "state": alias,
        }
        return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code(
        self,
        db: Session,
        user_id: int,
        code: str,
        redirect_uri: str = "http://localhost:8085/",
        alias: str = "personal_drive",
    ) -> EmailAccount:
        """Exchanges authorization code for tokens and saves to database."""
        cid, csec = self._get_client_credentials()
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": cid,
                    "client_secret": csec,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if token_resp.status_code != 200:
                raise ValidationAppError(f"OAuth code exchange failed: {token_resp.text}")

            tokens = token_resp.json()
            refresh_token = tokens.get("refresh_token")
            access_token = tokens.get("access_token")
            expires_in = tokens.get("expires_in", 3600)
            scopes = tokens.get("scope")

            # Fetch user email profile
            user_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            email_address = "unknown@google.com"
            if user_resp.status_code == 200:
                email_address = user_resp.json().get("email", email_address)

            # Check if account exists
            account = (
                db.query(EmailAccount)
                .filter(EmailAccount.user_id == user_id, EmailAccount.alias == alias)
                .first()
            )

            now = datetime.now(UTC)
            if not account:
                # Also check by email
                account = (
                    db.query(EmailAccount)
                    .filter(EmailAccount.user_id == user_id, EmailAccount.email_address == email_address)
                    .first()
                )

            if not account:
                account = EmailAccount(
                    user_id=user_id,
                    alias=alias,
                    email_address=email_address,
                    provider="google_drive",
                    refresh_token=refresh_token or "",
                    access_token=access_token,
                    token_expiry=now + timedelta(seconds=expires_in),
                    scopes=scopes,
                    is_active=True,
                )
                db.add(account)
            else:
                if refresh_token:
                    account.refresh_token = refresh_token
                account.access_token = access_token
                account.token_expiry = now + timedelta(seconds=expires_in)
                account.scopes = scopes
                account.is_active = True

            db.commit()
            db.refresh(account)
            return account

    async def list_files(
        self,
        db: Session,
        user_id: int,
        query: str | None = None,
        folder_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Lists files from Google Drive matching query."""
        token, _ = await self.get_valid_access_token(db, user_id)

        q_parts = ["trashed = false"]
        if folder_id:
            q_parts.append(f"'{folder_id}' in parents")
        if query and query.strip():
            clean = query.replace("'", "\\'")
            q_parts.append(f"(name contains '{clean}' or fullText contains '{clean}')")

        q_str = " and ".join(q_parts)
        params = {
            "q": q_str,
            "pageSize": min(limit, 100),
            "fields": "files(id, name, mimeType, size, modifiedTime, webViewLink, webContentLink, parents, description)",
            "orderBy": "modifiedTime desc",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{DRIVE_API_BASE}/files",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            if resp.status_code != 200:
                logger.error("Drive list_files error: %s", resp.text)
                raise ValidationAppError(f"Google Drive API error ({resp.status_code}): {resp.text}")

            files = resp.json().get("files", [])
            return files

    async def search_files(
        self,
        db: Session,
        user_id: int,
        search_term: str,
        limit: int = 15,
    ) -> list[dict[str, Any]]:
        """Search files by keyword or title in Google Drive."""
        return await self.list_files(db, user_id, query=search_term, limit=limit)

    async def read_file(
        self,
        db: Session,
        user_id: int,
        file_id_or_name: str,
        max_chars: int = 6000,
    ) -> dict[str, Any]:
        """Retrieves and reads text content of a file in Google Drive."""
        token, _ = await self.get_valid_access_token(db, user_id)

        file_id = file_id_or_name.strip()
        # If user passed a filename rather than an ID, search for it first
        if " " in file_id or "." in file_id or len(file_id) < 15:
            matches = await self.search_files(db, user_id, search_term=file_id, limit=3)
            if not matches:
                raise NotFoundError(f"No Google Drive file found matching '{file_id}'.")
            target = matches[0]
            file_id = target["id"]
            meta = target
        else:
            # Fetch metadata
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{DRIVE_API_BASE}/files/{file_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"fields": "id, name, mimeType, size, modifiedTime, webViewLink"},
                )
                if resp.status_code != 200:
                    raise NotFoundError(f"Could not find file '{file_id}' in Google Drive ({resp.status_code}).")
                meta = resp.json()

        mime = meta.get("mimeType", "")
        name = meta.get("name", "Document")

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Handle Google Workspace docs (Docs, Sheets, Slides) via export
            if mime == "application/vnd.google-apps.document":
                export_resp = await client.get(
                    f"{DRIVE_API_BASE}/files/{file_id}/export",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"mimeType": "text/plain"},
                )
                content = export_resp.text
            elif mime == "application/vnd.google-apps.spreadsheet":
                export_resp = await client.get(
                    f"{DRIVE_API_BASE}/files/{file_id}/export",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"mimeType": "text/csv"},
                )
                content = export_resp.text
            else:
                # Direct download for text/code/pdf
                dl_resp = await client.get(
                    f"{DRIVE_API_BASE}/files/{file_id}?alt=media",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if dl_resp.status_code != 200:
                    raise ValidationAppError(f"Failed to download file content ({dl_resp.status_code}): {dl_resp.text[:200]}")
                try:
                    content = dl_resp.content.decode("utf-8")
                except UnicodeDecodeError:
                    content = f"[Binary file: {name} ({mime}, {len(dl_resp.content)} bytes)]"

        truncated = content[:max_chars]
        if len(content) > max_chars:
            truncated += f"\n... [content truncated: {len(content) - max_chars} characters remaining]"

        return {
            "id": file_id,
            "name": name,
            "mime_type": mime,
            "content": truncated,
            "total_chars": len(content),
            "web_view_link": meta.get("webViewLink"),
        }

    async def get_or_create_folder(
        self,
        db: Session,
        user_id: int,
        folder_name: str = "IRIS",
    ) -> str:
        """Finds or creates a directory folder in Google Drive and returns folder_id."""
        token, _ = await self.get_valid_access_token(db, user_id)
        clean_name = folder_name.strip()

        # Check existing folder
        q = f"name = '{clean_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{DRIVE_API_BASE}/files",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": q, "fields": "files(id, name)"},
            )
            if resp.status_code == 200:
                files = resp.json().get("files", [])
                if files:
                    return files[0]["id"]

            # Create folder
            create_resp = await client.post(
                f"{DRIVE_API_BASE}/files",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "name": clean_name,
                    "mimeType": "application/vnd.google-apps.folder",
                },
            )
            if create_resp.status_code not in (200, 201):
                logger.error("Failed to create Drive folder: %s", create_resp.text)
                raise ValidationAppError(f"Could not create Google Drive folder: {create_resp.text}")
            return create_resp.json()["id"]

    async def upload_file(
        self,
        db: Session,
        user_id: int,
        file_name: str,
        content: str | bytes,
        mime_type: str | None = None,
        folder_name: str | None = "IRIS",
    ) -> dict[str, Any]:
        """Uploads a file or document to Google Drive."""
        token, _ = await self.get_valid_access_token(db, user_id)

        target_mime = mime_type or mimetypes.guess_type(file_name)[0] or "text/plain"
        if isinstance(content, str):
            body_bytes = content.encode("utf-8")
        else:
            body_bytes = content

        metadata: dict[str, Any] = {"name": file_name}
        if folder_name:
            folder_id = await self.get_or_create_folder(db, user_id, folder_name=folder_name)
            metadata["parents"] = [folder_id]

        # Multipart upload boundary
        boundary = "===============IRIS_DRIVE_BOUNDARY=="
        delimiter = f"--{boundary}\r\n".encode("utf-8")
        close_delim = f"--{boundary}--\r\n".encode("utf-8")

        import json
        meta_json = json.dumps(metadata)
        meta_part = (
            f"Content-Type: application/json; charset=UTF-8\r\n\r\n{meta_json}\r\n"
        ).encode("utf-8")

        data_part = (
            f"Content-Type: {target_mime}\r\n\r\n"
        ).encode("utf-8") + body_bytes + b"\r\n"

        multipart_body = delimiter + meta_part + delimiter + data_part + close_delim

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
            "Content-Length": str(len(multipart_body)),
        }

        async with httpx.AsyncClient(timeout=40.0) as client:
            resp = await client.post(
                f"{DRIVE_UPLOAD_BASE}/files?uploadType=multipart&fields=id,name,mimeType,size,webViewLink,parents",
                headers=headers,
                content=multipart_body,
            )
            if resp.status_code not in (200, 201):
                logger.error("Drive upload failed: %s", resp.text)
                raise ValidationAppError(f"Google Drive upload failed ({resp.status_code}): {resp.text}")

            res = resp.json()
            return {
                "id": res.get("id"),
                "name": res.get("name"),
                "mime_type": res.get("mimeType"),
                "size_bytes": res.get("size"),
                "web_view_link": res.get("webViewLink"),
                "folder": folder_name,
            }

    async def upload_local_file(
        self,
        db: Session,
        user_id: int,
        local_path: str,
        folder_name: str | None = "IRIS",
    ) -> dict[str, Any]:
        """Uploads a local laptop file from disk directly to Google Drive."""
        p = Path(local_path)
        if not p.is_absolute():
            p = Path(r"C:\kirtan\IRIS") / local_path

        if not p.exists() or not p.is_file():
            raise NotFoundError(f"Local file '{p}' does not exist on laptop.")

        content = p.read_bytes()
        return await self.upload_file(
            db=db,
            user_id=user_id,
            file_name=p.name,
            content=content,
            folder_name=folder_name,
        )


drive_service = GoogleDriveService()
