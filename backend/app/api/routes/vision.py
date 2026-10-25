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


def _parse_multipart(content_type: str, body: bytes) -> tuple[list[tuple[bytes, str]], dict[str, str]]:
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

    images: list[tuple[bytes, str]] = []
    fields: dict[str, str] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition") or ""
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename or name in {"image", "file", "images"}:
            image_mime = (part.get_content_type() or "").lower()
            images.append((payload, image_mime))
        elif name:
            fields[str(name)] = payload.decode("utf-8", errors="replace").strip()

    if not images:
        raise VisionValidationError("No image field found. Use 'image', 'file', or 'images'.")
    return images, fields


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
    if declared_length and declared_length > (max_image * 4) + 1_000_000:
        raise HTTPException(
            status_code=413,
            detail=f"Image payload exceeds the {vision_service.max_image_bytes // (1024 * 1024)} MB limit.",
        )

    fields: dict[str, str] = {}
    images_to_process: list[tuple[bytes, str]] = []

    if content_type.startswith("multipart/form-data"):
        try:
            images_to_process, fields = _parse_multipart(
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

        # Support both single image (image_base64) and multiple images (images list)
        items = []
        if isinstance(data.get("images"), list):
            items.extend(data["images"])
        if data.get("image_base64") or data.get("image"):
            items.append({
                "image_base64": data.get("image_base64") or data.get("image"),
                "mime_type": data.get("mime_type"),
            })

        if not items:
            raise HTTPException(status_code=400, detail="No image provided in request.")

        for item in items:
            if isinstance(item, str):
                b64_str, mime_str = item, None
            elif isinstance(item, dict):
                b64_str = item.get("image_base64") or item.get("data_url") or item.get("url") or ""
                mime_str = item.get("mime_type")
            else:
                continue
            if b64_str:
                try:
                    img_bytes, mime = vision_service.decode_base64_image(
                        str(b64_str), str(mime_str or "") or None
                    )
                    images_to_process.append((img_bytes, mime))
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
            detail="Use multipart/form-data or application/json with image_base64/images.",
        )

    prompt = _field(fields, "prompt") or (
        "Extract the useful context from these images and act on it."
        if len(images_to_process) > 1
        else "Extract the useful context from this image and act on it."
    )
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
            images=images_to_process,
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
        images_to_process.clear()

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
