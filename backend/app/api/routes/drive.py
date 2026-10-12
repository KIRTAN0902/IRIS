"""FastAPI endpoints for Google Drive integration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models.user import User
from app.services.google_drive_service import drive_service

router = APIRouter(prefix="/drive", tags=["drive"])


class DriveUploadRequest(BaseModel):
    file_name: str = Field(..., description="Name for the file in Google Drive")
    content: str = Field(..., description="Text or Markdown content")
    folder_name: str | None = Field("IRIS", description="Google Drive folder name")


@router.get("/status", summary="Check Google Drive connection status")
def get_drive_status(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Check whether Google Drive is connected for the user."""
    acc = drive_service.get_drive_account(db, user.id)
    if not acc or not acc.refresh_token:
        return {
            "is_connected": False,
            "account": None,
            "message": "Google Drive is not connected yet. Run `python scripts/connect_drive.py` to link your account.",
        }

    return {
        "is_connected": True,
        "account": {
            "alias": acc.alias,
            "email_address": acc.email_address,
            "scopes": acc.scopes,
            "last_synced_at": acc.last_synced_at.isoformat() if acc.last_synced_at else None,
        },
        "message": f"Connected to Google Drive ({acc.email_address})",
    }


@router.get("/auth/url", summary="Get Google Drive OAuth authorization URL")
def get_auth_url(
    alias: str = Query("personal_drive", description="Account alias"),
    redirect_uri: str = Query("http://localhost:8085/", description="Redirect callback URI"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Generate authorization URL for connecting Google Drive."""
    url = drive_service.build_auth_url(alias=alias, redirect_uri=redirect_uri)
    return {"auth_url": url}


@router.get("/auth/callback", response_class=HTMLResponse, summary="OAuth callback handler")
async def oauth_callback(
    code: str = Query(..., description="Google OAuth code"),
    state: str = Query("personal_drive", description="State parameter containing alias"),
    db: Session = Depends(get_db),
):
    """Web callback endpoint for Google OAuth consent flow."""
    try:
        user_id = 1  # Single-user local IRIS default
        account = await drive_service.exchange_code(
            db=db,
            user_id=user_id,
            code=code,
            redirect_uri="http://localhost:8000/api/drive/auth/callback",
            alias=state,
        )
        return f"""<html><body style="font-family: system-ui, sans-serif; text-align: center; padding: 60px; background: #09090b; color: #f4f4f5;">
        <h2 style="color: #10b981;">&#10003; Google Drive Connected Successfully!</h2>
        <p>IRIS is now connected to <strong>{account.email_address}</strong>.</p>
        <p style="color: #71717a;">You can close this window and return to IRIS.</p>
        </body></html>"""
    except Exception as exc:
        return f"""<html><body style="font-family: system-ui, sans-serif; text-align: center; padding: 60px; background: #09090b; color: #f4f4f5;">
        <h2 style="color: #ef4444;">Authorization Failed</h2>
        <p style="color: #a1a1aa;">{exc}</p>
        </body></html>"""


@router.get("/files", summary="List or search files in Google Drive")
async def list_drive_files(
    query: str | None = Query(None, description="Search term or filter"),
    folder_id: str | None = Query(None, description="Parent folder ID"),
    limit: int = Query(20, ge=1, le=100, description="Max files to return"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Lists files and folders from Google Drive."""
    files = await drive_service.list_files(
        db=db, user_id=user.id, query=query, folder_id=folder_id, limit=limit
    )
    return {"files": files, "count": len(files)}


@router.get("/files/{file_id}/content", summary="Read Google Drive file content")
async def read_drive_file_content(
    file_id: str,
    max_chars: int = Query(6000, ge=100, le=25000),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Retrieves and parses text or Google Doc content from Google Drive."""
    return await drive_service.read_file(
        db=db, user_id=user.id, file_id_or_name=file_id, max_chars=max_chars
    )


@router.post("/upload", summary="Upload a document to Google Drive")
async def upload_document(
    data: DriveUploadRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Uploads a text or markdown document into Google Drive."""
    return await drive_service.upload_file(
        db=db,
        user_id=user.id,
        file_name=data.file_name,
        content=data.content,
        folder_name=data.folder_name,
    )


@router.post("/upload-file", summary="Upload binary/raw file to Google Drive")
async def upload_raw_file(
    file: UploadFile = File(...),
    folder_name: str = Query("IRIS", description="Google Drive target folder"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Uploads an uploaded file from disk or browser directly into Google Drive."""
    content = await file.read()
    return await drive_service.upload_file(
        db=db,
        user_id=user.id,
        file_name=file.filename or "upload.bin",
        content=content,
        mime_type=file.content_type,
        folder_name=folder_name,
    )
