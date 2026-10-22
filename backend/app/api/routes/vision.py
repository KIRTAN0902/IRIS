"""Ephemeral vision ingestion.

The request image is read into RAM only. It is sent to Nemotron Super VL and
discarded; this module never writes image bytes to disk or the database.
"""

from __future__ import annotations

from email.parser import BytesParser
from email.policy import default
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models.user import User
from app.services.vision_service import (
    VisionError,
    VisionImageTooLarge,
    VisionValidationError,
    vision_service,
)

router = APIRouter(prefix="/vision", tags=["vision"])


def _field(fields: dict[str, str], key: str) -> str | None:
    value = fields.get(key)
    return value.strip() if value and value.strip() else None


def _parse_multipart(content_type: str, body: bytes) -> tuple[bytes, str, dict[str, str]]:
    """Parse multipart form-data entirely in memory (never spool to disk)."""
    envelope = (
        b"Content-Type: "
        + content_type.encode("latin-1", errors="replace")
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + body
    )
    message = BytesParser(policy=default).parsebytes(envelope)
    if not message.is_multipart():
        raise VisionValidationError("Malformed multipart image payload.")

    image_bytes: bytes | None = None
    image_mime = ""
    fields: dict[str, str] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition") or ""
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename or name in {"image", "file"}:
            image_bytes = payload
            image_mime = (part.get_content_type() or "").lower()
        elif name:
            fields[str(name)] = payload.decode("utf-8", errors="replace").strip()

    if not image_bytes:
        raise VisionValidationError("No image field found. Use 'image' or 'file'.")
    fields["mime_type"] = _field(fields, "mime_type") or image_mime
    return image_bytes, fields["mime_type"], fields


@router.post("/ingest", summary="Analyze an ephemeral image and act on its context")
async def ingest_image(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Accept JSON base64 or multipart form-data and keep only text context."""
    content_type = (request.headers.get("content-type") or "").lower()
    max_image = vision_service.max_image_bytes
    try:
        declared_length = int(request.headers.get("content-length") or 0)
    except ValueError:
        declared_length = 0
    if declared_length and declared_length > (max_image * 2) + 1_000_000:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds the {vision_service.max_image_bytes // (1024 * 1024)} MB limit.",
        )

    fields: dict[str, str] = {}
    if content_type.startswith("multipart/form-data"):
        try:
            image_bytes, mime_type, fields = _parse_multipart(
                request.headers.get("content-type") or "", await request.body()
            )
        except VisionValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif content_type.startswith("application/json"):
        try:
            data = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body.") from exc
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object.")
        encoded = data.get("image_base64") or data.get("image") or ""
        try:
            image_bytes, mime_type = vision_service.decode_base64_image(
                str(encoded), str(data.get("mime_type") or "") or None
            )
        except VisionImageTooLarge as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except VisionValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        fields = {
            "prompt": str(data.get("prompt") or ""),
            "conversation_id": str(data.get("conversation_id") or ""),
            "domain_hint": str(data.get("domain_hint") or ""),
        }
    else:
        raise HTTPException(
            status_code=415,
            detail="Use multipart/form-data or application/json with image_base64.",
        )

    prompt = _field(fields, "prompt") or "Extract the useful context from this image and act on it."
    domain_hint = _field(fields, "domain_hint")
    conversation_raw = _field(fields, "conversation_id")
    try:
        conversation_id = int(conversation_raw) if conversation_raw else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="conversation_id must be an integer.") from exc

    try:
        response, result, memory = await vision_service.process_ephemeral_turn(
            db=db,
            user=user,
            image_bytes=image_bytes,
            mime_type=mime_type,
            prompt=prompt,
            conversation_id=conversation_id,
            domain_hint=domain_hint,
        )
    except VisionImageTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except VisionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except VisionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        image_bytes = b""

    return {
        "answer": response.content,
        "conversation_id": response.conversation_id,
        "source": response.source,
        "actions_taken": response.actions_taken,
        "visual_context": result.card(),
        "memory_id": memory.id,
        "image_persisted": False,
        "message": response.model_dump(mode="json"),
    }
