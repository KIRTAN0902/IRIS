"""Ephemeral multimodal understanding for IRIS.

Images exist only as in-memory bytes for the duration of one provider call. The
service never writes them to disk, the database, conversation history, or logs.
Only the structured text extraction survives, and only as contextual memory.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.ai.factory import create_ai_provider
from app.ai.provider import AIProvider, ChatMessage
from app.ai.structured import parse_structured
from app.core.config import settings
from app.core.logging import get_logger
from app.models.user import User
from app.services.memory_service import memory_service

logger = get_logger("iris.services.vision")

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
DETECTED_DOMAINS = {"COLLEGE", "INTERNSHIP", "STARTUP", "PERSONAL", "OPERATOR"}

_SYSTEM_PROMPT = """You are IRIS's ephemeral vision extractor.
Analyze the attached image and return ONLY one JSON object with exactly these keys:
{
  "summary": "1-2 concise sentences describing the image",
  "extracted_text_or_code": "OCR text, code, equations, stack traces, or table cells",
  "detected_domain": "COLLEGE | INTERNSHIP | STARTUP | PERSONAL | OPERATOR",
  "actionable_items": [
    {"kind": "task|expense|deadline|code_fix|note", "title": "...", "amount": null,
     "merchant": null, "category": null, "due_date": null, "details": null}
  ],
  "memory_facts": ["high-value durable facts worth remembering"]
}
Rules:
- Prefer verifiable text from the image over speculation.
- Never include the base64 payload, data URI, or image bytes in the response.
- Use an empty actionable_items list when nothing is actionable.
- detected_domain must be exactly one of the five uppercase values.
"""


class VisionError(Exception):
    """Base error for the ephemeral vision pipeline."""


class VisionValidationError(VisionError):
    """The image or request failed validation."""


class VisionImageTooLarge(VisionError):
    """The image exceeds VISION_MAX_IMAGE_MB."""


class VisionProviderError(VisionError):
    """The vision model call failed."""


class VisionExtractionResult(BaseModel):
    """Structured, persistence-safe output from the vision model."""

    summary: str = "Image processed."
    extracted_text_or_code: str = ""
    detected_domain: str = "OPERATOR"
    actionable_items: list[dict[str, Any]] = Field(default_factory=list)
    memory_facts: list[str] = Field(default_factory=list)
    provider: str = ""
    model: str = ""

    @field_validator("summary", mode="before")
    @classmethod
    def _clean_summary(cls, value: Any) -> str:
        text = " ".join(str(value or "").split())
        return (text or "Image processed.")[:1000]

    @field_validator("extracted_text_or_code", mode="before")
    @classmethod
    def _clean_extracted(cls, value: Any) -> str:
        return str(value or "")[:8000]

    @field_validator("detected_domain", mode="before")
    @classmethod
    def _clean_domain(cls, value: Any) -> str:
        domain = str(value or "OPERATOR").strip().upper()
        return domain if domain in DETECTED_DOMAINS else "OPERATOR"

    @field_validator("actionable_items", mode="before")
    @classmethod
    def _clean_actions(cls, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if isinstance(value, dict):
            value = [value]
        if isinstance(value, str):
            value = [value]
        out: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, str):
                out.append({"kind": "task", "title": item[:500]})
            elif isinstance(item, dict):
                out.append({str(k): v for k, v in item.items()})
        return out[:30]

    @field_validator("memory_facts", mode="before")
    @classmethod
    def _clean_facts(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return [str(item)[:500] for item in value][:20]

    def card(self) -> dict[str, Any]:
        """JavaScript-safe payload for the visual-context UI card."""
        return {
            "summary": self.summary,
            "extracted_text_or_code": self.extracted_text_or_code,
            "detected_domain": self.detected_domain,
            "actionable_items": self.actionable_items,
            "memory_facts": self.memory_facts,
            "provider": self.provider,
            "model": self.model,
            "image_persisted": False,
        }


def _detect_mime(image: bytes) -> str | None:
    if image.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(image) >= 12 and image[:4] == b"RIFF" and image[8:12] == b"WEBP":
        return "image/webp"
    return None


def _normalise_mime(mime_type: str | None) -> str | None:
    mime = (mime_type or "").strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    return mime if mime in ALLOWED_MIME_TYPES else None


class VisionService:
    """Runs one transient image through Nemotron Super VL and keeps text only."""

    def __init__(self, provider: AIProvider | None = None) -> None:
        self._provider_override = provider
        self._provider_instance: AIProvider | None = None

    @property
    def max_image_bytes(self) -> int:
        return max(1, int(settings.vision_max_image_mb)) * 1024 * 1024

    def reset_provider(self) -> None:
        self._provider_instance = None

    def _build_provider(self) -> AIProvider:
        requested = (settings.vision_provider or "nvidia").strip().lower()
        nvidia_key = settings.nvidia_api_key or os.environ.get("NVIDIA_API_KEY")
        # Only treat AI_API_KEY as an NVIDIA key when the main agent is also
        # configured for NVIDIA; otherwise it is likely a Gemini key.
        if not nvidia_key and (settings.ai_provider or "").strip().lower() == "nvidia":
            nvidia_key = settings.ai_api_key
        if requested == "nvidia" and not nvidia_key:
            logger.info("Vision: NVIDIA key missing; falling back to Gemini")
            requested = "gemini"

        if requested == "nvidia":
            from app.ai.providers.nvidia import NvidiaProvider

            return NvidiaProvider(
                base_url=settings.nvidia_base_url,
                api_key=nvidia_key,
                model=settings.vision_model_name,
                timeout_seconds=settings.vision_timeout_seconds,
            )

        if requested == "gemini":
            from app.ai.providers.gemini import GeminiProvider

            fallback_model = (
                settings.vision_fallback_model
                or settings.gemini_model
                or settings.ai_model
                or "gemini-3.5-flash"
            )
            gemini_key = settings.gemini_api_key or os.environ.get("GEMINI_API_KEY")
            if not gemini_key and (settings.ai_provider or "").strip().lower() == "gemini":
                gemini_key = settings.ai_api_key
            return GeminiProvider(
                api_key=gemini_key,
                model=fallback_model,
                timeout_seconds=settings.vision_timeout_seconds,
            )

        return create_ai_provider(requested, model=settings.vision_model_name)

    def provider(self) -> AIProvider:
        if self._provider_override is not None:
            return self._provider_override
        if self._provider_instance is None:
            self._provider_instance = self._build_provider()
        return self._provider_instance

    def decode_base64_image(
        self, image_base64: str, mime_type: str | None = None
    ) -> tuple[bytes, str]:
        """Decode a base64 or data-URI payload into transient bytes."""
        raw = (image_base64 or "").strip()
        declared = _normalise_mime(mime_type)
        if raw.startswith("data:"):
            header, _, raw = raw.partition(",")
            if not declared and header.startswith("data:"):
                declared = _normalise_mime(header[5:].split(";", 1)[0])
        raw = re.sub(r"\s+", "", raw)
        if not raw:
            raise VisionValidationError("Image payload is empty.")
        max_encoded = (self.max_image_bytes * 4 // 3) + 16
        if len(raw) > max_encoded:
            raise VisionImageTooLarge(
                f"Image exceeds the {settings.vision_max_image_mb} MB limit."
            )
        try:
            image_bytes = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise VisionValidationError("Image payload is not valid base64.") from exc
        if len(image_bytes) > self.max_image_bytes:
            raise VisionImageTooLarge(
                f"Image exceeds the {settings.vision_max_image_mb} MB limit."
            )
        mime = self._validated_mime(image_bytes, declared)
        return image_bytes, mime

    def _validated_mime(self, image_bytes: bytes, declared: str | None) -> str:
        if not image_bytes:
            raise VisionValidationError("Image payload is empty.")
        if len(image_bytes) > self.max_image_bytes:
            raise VisionImageTooLarge(
                f"Image exceeds the {settings.vision_max_image_mb} MB limit."
            )
        detected = _detect_mime(image_bytes)
        if detected is None:
            raise VisionValidationError("Unsupported image. Use PNG, JPEG, or WebP.")
        if declared and declared != detected:
            raise VisionValidationError(
                f"Image content is {detected}, not the declared {declared}."
            )
        return detected

    async def analyze_ephemeral_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        user_prompt: str,
        domain_hint: str | None = None,
    ) -> VisionExtractionResult:
        """Analyze one image in RAM; the raw bytes never leave this call."""
        mime = self._validated_mime(image_bytes, _normalise_mime(mime_type))
        if not user_prompt.strip():
            user_prompt = "Extract the useful context from this image and act on it."

        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_uri = f"data:{mime};base64,{b64}"
        prompt = (
            f"User request:\n{user_prompt.strip()}\n\n"
            f"Domain hint: {(domain_hint or 'auto').strip() or 'auto'}"
        )
        messages = [
            ChatMessage(role="system", content=_SYSTEM_PROMPT),
            ChatMessage(role="user", content=prompt, images=[data_uri]),
        ]
        provider = self.provider()
        if not provider.enabled:
            raise VisionProviderError(
                f"Vision provider '{provider.name}' is not configured."
            )

        logger.info(
            "Ephemeral vision started: provider=%s model=%s bytes=%d mime=%s",
            provider.name,
            provider.model,
            len(image_bytes),
            mime,
        )
        try:
            response = await provider.chat(
                messages,
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=2048,
            )
            parsed = parse_structured(
                response.content or "", VisionExtractionResult, provider=provider.name
            )
        except Exception as exc:
            if isinstance(exc, VisionError):
                raise
            logger.warning("Vision provider call failed: %s", type(exc).__name__)
            raise VisionProviderError("Vision analysis failed. Please retry.") from None
        finally:
            # Drop the only references to the raw image and its encoded payload.
            messages.clear()
            del messages
            del data_uri
            del b64
            del image_bytes

        parsed.provider = provider.name
        parsed.model = provider.model
        logger.info(
            "Ephemeral vision completed: provider=%s model=%s domain=%s actions=%d",
            provider.name,
            provider.model,
            parsed.detected_domain,
            len(parsed.actionable_items),
        )
        return parsed

    def store_visual_context(
        self,
        db: Session,
        user: User,
        result: VisionExtractionResult,
    ) -> Any:
        """Persist only the synthesized context, never the image."""
        pieces = [result.summary]
        if result.extracted_text_or_code:
            pieces.append("Extracted text/code: " + result.extracted_text_or_code[:2000])
        if result.memory_facts:
            pieces.append("Facts: " + "; ".join(result.memory_facts))
        action_titles = [
            str(item.get("title") or item.get("details") or "").strip()
            for item in result.actionable_items
        ]
        action_titles = [title for title in action_titles if title]
        if action_titles:
            pieces.append("Actions: " + "; ".join(action_titles[:10]))
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
        key = f"vision:{result.detected_domain.lower()}:{stamp}"
        return memory_service.store_memory(
            db,
            user,
            content="\n".join(pieces)[:6000],
            category="visual_context",
            key=key,
            importance=0.7,
            source="AGENT_TOOL",
        )

    @staticmethod
    def context_block(result: VisionExtractionResult) -> str:
        payload = result.model_dump(
            mode="json", exclude={"provider", "model", "image_persisted"}
        )
        return (
            "[EPHEMERAL VISION TELEMETRY (Nemotron 3.5 Super VL — "
            "Image Discarded after Processing)]:\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )

    @staticmethod
    def persisted_user_message(prompt: str, result: VisionExtractionResult) -> str:
        clean_prompt = (prompt or "").strip() or "Shared an image for visual context."
        summary = " ".join(result.summary.split())[:220]
        return f"{clean_prompt}\n\n[📷 Visual Context Processed: {summary}]"

    async def process_ephemeral_turn(
        self,
        *,
        db: Session,
        user: User,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        conversation_id: int | None = None,
        domain_hint: str | None = None,
        agent: Any | None = None,
    ) -> tuple[Any, VisionExtractionResult, Any]:
        """Analyze, persist context-only memory, then run the normal IRIS turn."""
        result = await self.analyze_ephemeral_image(
            image_bytes, mime_type, prompt, domain_hint
        )
        # Do not trust a caller-supplied conversation_id for memory ownership;
        # link the memory to the conversation actually resolved by the agent.
        memory = self.store_visual_context(db, user, result)
        enriched = f"{self.context_block(result)}\n\nUSER REQUEST:\n{prompt.strip()}"
        persisted = self.persisted_user_message(prompt, result)

        if agent is None:
            from app.agent.agent import default_agent

            agent = default_agent

        response, _conversation = await agent.run_turn(
            db=db,
            user=user,
            user_message=enriched,
            conversation_id=conversation_id,
            skip_fast_path=True,
            skip_memory=True,
            persisted_user_message=persisted,
            extra_metadata={
                "visual_context": result.card(),
                "vision_memory_id": memory.id,
                "image_persisted": False,
            },
        )
        if memory is not None:
            memory.conversation_id = response.conversation_id
            db.commit()
        return response, result, memory


vision_service = VisionService()
