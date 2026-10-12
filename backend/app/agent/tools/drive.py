"""Google Drive Agent Tools: Enables IRIS to upload and retrieve files from Google Drive."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import Tool
from app.models.user import User
from app.services.google_drive_service import drive_service


# --- 1. ListGoogleDriveFilesTool ---


class ListGoogleDriveFilesParams(BaseModel):
    query: str | None = Field(
        None,
        description="Optional search filter, keyword, or folder name to narrow down files",
    )
    limit: int = Field(default=12, ge=1, le=50, description="Max files to list")


class ListGoogleDriveFilesTool(Tool):
    name = "list_google_drive_files"
    description = (
        "List and view recent or matching files and folders stored in Google Drive. "
        "Use when user asks to see what files are in their Google Drive or check recent documents."
    )
    parameters_schema = ListGoogleDriveFilesParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query")
        limit = kwargs.get("limit", 12)

        try:
            files = await drive_service.list_files(db=db, user_id=user.id, query=query, limit=limit)
            if not files:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    data={"files": [], "count": 0},
                    summary="No files found in Google Drive" + (f" matching '{query}'." if query else "."),
                )

            lines = []
            for f in files:
                name = f.get("name", "Untitled")
                fid = f.get("id")
                mime = f.get("mimeType", "")
                link = f.get("webViewLink")
                icon = "📁" if "folder" in mime else "📄"
                link_str = f" ([open]({link}))" if link else ""
                lines.append(f"- {icon} **{name}** `{fid}`{link_str}")

            summary = f"Found {len(files)} file(s) in Google Drive:\n" + "\n".join(lines)
            return ToolResult(
                tool_name=self.name,
                success=True,
                data={"files": files, "count": len(files)},
                summary=summary,
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(exc),
                summary=f"Google Drive access error: {exc}",
            )


# --- 2. SearchGoogleDriveTool ---


class SearchGoogleDriveParams(BaseModel):
    query: str = Field(..., min_length=1, description="Keywords or document title to search in Google Drive")
    limit: int = Field(default=8, ge=1, le=30, description="Max results")


class SearchGoogleDriveTool(Tool):
    name = "search_google_drive"
    description = (
        "Search files, presentations, notes, and documents in Google Drive by keyword or title."
    )
    parameters_schema = SearchGoogleDriveParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        query = kwargs["query"]
        limit = kwargs.get("limit", 8)

        try:
            files = await drive_service.search_files(db=db, user_id=user.id, search_term=query, limit=limit)
            if not files:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    data={"files": [], "count": 0},
                    summary=f"No Google Drive files found matching '{query}'.",
                )

            lines = [f"- 📄 **{f.get('name')}** (ID: `{f.get('id')}`) [View]({f.get('webViewLink')})" for f in files]
            summary = f"Found {len(files)} search result(s) in Google Drive for '{query}':\n" + "\n".join(lines)
            return ToolResult(
                tool_name=self.name,
                success=True,
                data={"files": files, "count": len(files)},
                summary=summary,
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(exc),
                summary=f"Failed to search Google Drive: {exc}",
            )


# --- 3. ReadGoogleDriveFileTool ---


class ReadGoogleDriveFileParams(BaseModel):
    file_id_or_name: str = Field(
        ...,
        description="The file ID or exact filename of the document in Google Drive",
    )
    max_chars: int = Field(default=4000, ge=100, le=20000, description="Max characters to read")


class ReadGoogleDriveFileTool(Tool):
    name = "read_google_drive_file"
    description = (
        "Retrieve and read the text contents of a document, note, or Google Doc from Google Drive. "
        "Use when user asks what is in a specific Google Drive file or wants to review a document."
    )
    parameters_schema = ReadGoogleDriveFileParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        target = kwargs["file_id_or_name"]
        max_chars = kwargs.get("max_chars", 4000)

        try:
            result = await drive_service.read_file(db=db, user_id=user.id, file_id_or_name=target, max_chars=max_chars)
            summary = (
                f"📄 **{result['name']}** ([Open in Drive]({result['web_view_link']})):\n"
                f"```\n{result['content']}\n```"
            )
            return ToolResult(
                tool_name=self.name,
                success=True,
                data=result,
                summary=summary,
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(exc),
                summary=f"Could not read Google Drive document '{target}': {exc}",
            )


# --- 4. UploadToGoogleDriveTool ---


class UploadToGoogleDriveParams(BaseModel):
    file_name: str = Field(
        ...,
        description="Desired file name in Google Drive (e.g. 'briefing_notes.md', 'summary.txt', 'roadmap.json')",
    )
    content: str | None = Field(
        None,
        description="Text or Markdown content to write into the file",
    )
    local_file_path: str | None = Field(
        None,
        description="Optional local path on the Windows laptop to upload (e.g. 'DESIGN.md', 'COOLIFY.md')",
    )
    folder_name: str | None = Field(
        default="IRIS",
        description="Target Google Drive folder name (defaults to 'IRIS')",
    )


class UploadToGoogleDriveTool(Tool):
    name = "upload_to_google_drive"
    description = (
        "Upload a document, briefing, note, or local laptop file directly to Google Drive. "
        "Use when user asks to upload or save something to Google Drive or sync a file with their Drive/NotebookLM."
    )
    parameters_schema = UploadToGoogleDriveParams
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        file_name = kwargs["file_name"]
        content = kwargs.get("content")
        local_path = kwargs.get("local_file_path")
        folder_name = kwargs.get("folder_name") or "IRIS"

        try:
            if local_path:
                res = await drive_service.upload_local_file(
                    db=db, user_id=user.id, local_path=local_path, folder_name=folder_name
                )
            elif content:
                res = await drive_service.upload_file(
                    db=db, user_id=user.id, file_name=file_name, content=content, folder_name=folder_name
                )
            else:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="Either 'content' or 'local_file_path' must be provided.",
                    summary="Upload failed: neither content nor local file path provided.",
                )

            summary = (
                f"✅ Uploaded `{res['name']}` to Google Drive (Folder: `{folder_name}`)\n"
                f"Link: {res.get('web_view_link')}"
            )
            return ToolResult(
                tool_name=self.name,
                success=True,
                data=res,
                summary=summary,
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(exc),
                summary=f"Failed to upload to Google Drive: {exc}",
            )


def drive_tools() -> list[Tool]:
    """Factory creating all Google Drive agent tools."""
    return [
        ListGoogleDriveFilesTool(),
        SearchGoogleDriveTool(),
        ReadGoogleDriveFileTool(),
        UploadToGoogleDriveTool(),
    ]
