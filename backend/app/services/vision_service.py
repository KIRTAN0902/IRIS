"""Ephemeral multimodal understanding for IRIS.

Images exist only as in-memory bytes for the duration of one provider call. The
service never writes them to disk, the database, conversation history, or logs.
Only the structured text extraction survives, and only as contextual memory.
"""

from __future__ import annotations

import asyncio
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
Analyze the attached image(s) and return ONLY one JSON object with exactly these keys:
{
  "summary": "1-2 concise sentences describing the image(s) and visual context",
  "extracted_text_or_code": "OCR text, code, equations, stack traces, or table cells across all images",
  "detected_domain": "COLLEGE | INTERNSHIP | STARTUP | PERSONAL | OPERATOR",
  "actionable_items": [
    {"kind": "task|expense|deadline|code_fix|note", "title": "...", "amount": null,
     "merchant": null, "category": null, "due_date": null, "details": null}
  ],
  "memory_facts": ["high-value durable facts worth remembering"]
}
Rules:
- Prefer verifiable text from the image(s) over speculation.
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
        self._fallback_instance: AIProvider | None = None

    @property
    def max_image_bytes(self) -> int:
        return max(1, int(settings.vision_max_image_mb)) * 1024 * 1024

    def reset_provider(self) -> None:
        self._provider_instance = None
        self._fallback_instance = None

    def _build_provider(self, fallback: bool = False) -> AIProvider:
        primary_name = (settings.vision_provider or "gemini").strip().lower()
        nvidia_key = settings.nvidia_api_key or os.environ.get("NVIDIA_API_KEY")
        if not nvidia_key and (settings.ai_provider or "").strip().lower() == "nvidia":
            nvidia_key = settings.ai_api_key

        gemini_key = settings.gemini_api_key or os.environ.get("GEMINI_API_KEY")
        if not gemini_key and (settings.ai_provider or "").strip().lower() == "gemini":
            gemini_key = settings.ai_api_key

        target = primary_name
        if fallback:
            target = "nvidia" if primary_name == "gemini" else "gemini"

        if target == "nvidia" and not nvidia_key and not fallback:
            logger.info("Vision: NVIDIA key missing; falling back to Gemini as primary")
            target = "gemini"

        if target == "nvidia":
            from app.ai.providers.nvidia import NvidiaProvider

            model_name = (
                settings.vision_model_name
                if (not fallback and primary_name == "nvidia")
                else (settings.vision_fallback_model or "nvidia/nemotron-3.5-super-vl-120b-a12b")
            )
            if "gemini" in model_name.lower():
                model_name = "nvidia/nemotron-3.5-super-vl-120b-a12b"
            return NvidiaProvider(
                base_url=settings.nvidia_base_url,
                api_key=nvidia_key,
                model=model_name,
                timeout_seconds=settings.vision_timeout_seconds,
            )

        if target == "gemini":
            from app.ai.providers.gemini import GeminiProvider

            model_name = (
                settings.vision_model_name
                if (not fallback and primary_name == "gemini")
                else (settings.vision_fallback_model or "gemini-3.1-flash-lite")
            )
            if "nemotron" in model_name.lower():
                model_name = "gemini-3.1-flash-lite"
            return GeminiProvider(
                api_key=gemini_key,
                model=model_name,
                timeout_seconds=settings.vision_timeout_seconds,
            )

        return create_ai_provider(target, model=settings.vision_model_name)

    def provider(self) -> AIProvider:
        if self._provider_override is not None:
            return self._provider_override
        if self._provider_instance is None:
            self._provider_instance = self._build_provider(fallback=False)
        return self._provider_instance

    def fallback_provider(self) -> AIProvider | None:
        if self._provider_override is not None:
            return None
        if self._fallback_instance is None:
            try:
                self._fallback_instance = self._build_provider(fallback=True)
            except Exception as exc:
                logger.debug("Vision fallback provider unavailable: %s", exc)
                return None
        return self._fallback_instance

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
        """Analyze one image in RAM (backward compatibility)."""
        return await self.analyze_ephemeral_images(
            [(image_bytes, mime_type)], user_prompt, domain_hint
        )

    async def analyze_ephemeral_images(
        self,
        images: list[tuple[bytes, str]],
        user_prompt: str,
        domain_hint: str | None = None,
        force_serial: bool | None = None,
    ) -> VisionExtractionResult:
        """Analyze one or more images in RAM; the raw bytes never leave this call."""
        if not images:
            raise VisionValidationError("No images provided for analysis.")

        if len(images) == 1:
            return await self._analyze_single_image(images[0], user_prompt, domain_hint)

        run_serial = (
            force_serial
            if force_serial is not None
            else bool(settings.vision_serial_processing)
        )
        if run_serial:
            logger.info("Vision: processing %d images serially as configured", len(images))
            return await self._analyze_ephemeral_images_serially(images, user_prompt, domain_hint)

        # Try batch mode first (fastest)
        try:
            return await self._analyze_batch(images, user_prompt, domain_hint)
        except Exception as exc:
            is_rate_limit = (
                "429" in str(exc)
                or "rate" in str(exc).lower()
                or "quota" in str(exc).lower()
                or "too many requests" in str(exc).lower()
            )
            is_payload_too_large = "413" in str(exc) or "payload" in str(exc).lower()
            logger.warning(
                "Vision batch call encountered %s (rate_limit=%s, payload_too_large=%s); "
                "automatically falling back to serial image processing with rate-limit backoff",
                exc,
                is_rate_limit,
                is_payload_too_large,
            )
            return await self._analyze_ephemeral_images_serially(
                images, user_prompt, domain_hint, backoff_on_start=is_rate_limit
            )

    async def _analyze_batch(
        self,
        images: list[tuple[bytes, str]],
        user_prompt: str,
        domain_hint: str | None = None,
    ) -> VisionExtractionResult:
        data_uris: list[str] = []
        total_bytes = 0
        mimes: list[str] = []
        for img_bytes, mime_type in images:
            mime = self._validated_mime(img_bytes, _normalise_mime(mime_type))
            b64 = base64.b64encode(img_bytes).decode("ascii")
            data_uris.append(f"data:{mime};base64,{b64}")
            total_bytes += len(img_bytes)
            mimes.append(mime)

        clean_prompt = (
            user_prompt.strip()
            if user_prompt and user_prompt.strip()
            else "Extract the useful context from these images and act on it."
        )
        prompt = (
            f"User request:\n{clean_prompt}\n\n"
            f"Domain hint: {(domain_hint or 'auto').strip() or 'auto'}"
        )
        messages = [
            ChatMessage(role="system", content=_SYSTEM_PROMPT),
            ChatMessage(role="user", content=prompt, images=data_uris),
        ]
        provider = self.provider()
        if not provider.enabled:
            raise VisionProviderError(f"Vision provider '{provider.name}' is not configured.")

        logger.info(
            "Ephemeral vision batch started: provider=%s model=%s images=%d bytes=%d mimes=%s",
            provider.name,
            provider.model,
            len(images),
            total_bytes,
            ",".join(mimes),
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
            parsed.provider = provider.name
            parsed.model = provider.model
            logger.info(
                "Ephemeral vision batch completed: provider=%s model=%s domain=%s actions=%d",
                provider.name,
                provider.model,
                parsed.detected_domain,
                len(parsed.actionable_items),
            )
            return parsed
        finally:
            messages.clear()
            data_uris.clear()

    async def _analyze_single_image(
        self,
        image_tuple: tuple[bytes, str],
        user_prompt: str,
        domain_hint: str | None = None,
        index: int = 1,
        total: int = 1,
    ) -> VisionExtractionResult:
        img_bytes, mime_type = image_tuple
        mime = self._validated_mime(img_bytes, _normalise_mime(mime_type))
        b64 = base64.b64encode(img_bytes).decode("ascii")
        data_uri = f"data:{mime};base64,{b64}"

        clean_prompt = (
            user_prompt.strip()
            if user_prompt and user_prompt.strip()
            else "Extract the useful context from this image and act on it."
        )
        prompt = (
            f"User request:\n{clean_prompt}\n\n"
            f"Domain hint: {(domain_hint or 'auto').strip() or 'auto'}"
        )
        messages = [
            ChatMessage(role="system", content=_SYSTEM_PROMPT),
            ChatMessage(role="user", content=prompt, images=[data_uri]),
        ]

        providers_to_try: list[AIProvider] = [self.provider()]
        fb = self.fallback_provider()
        if fb and fb.enabled and fb.name != providers_to_try[0].name:
            providers_to_try.append(fb)

        last_exc: Exception | None = None
        for p in providers_to_try:
            if not p.enabled:
                continue
            for attempt in range(2):
                try:
                    response = await p.chat(
                        messages,
                        response_format={"type": "json_object"},
                        temperature=0.1,
                        max_tokens=2048,
                    )
                    parsed = parse_structured(
                        response.content or "", VisionExtractionResult, provider=p.name
                    )
                    parsed.provider = p.name
                    parsed.model = p.model
                    return parsed
                except Exception as exc:
                    last_exc = exc
                    if "429" in str(exc) or "rate" in str(exc).lower():
                        logger.warning(
                            "Vision rate limit hit on provider %s (image %d/%d, attempt %d/2); backing off 1.5s",
                            p.name,
                            index,
                            total,
                            attempt + 1,
                        )
                        await asyncio.sleep(1.5)
                        continue
                    logger.warning(
                        "Vision single call failed on provider %s: %s; trying next provider",
                        p.name,
                        exc,
                    )
                    break

        if isinstance(last_exc, VisionError):
            raise last_exc
        raise VisionProviderError(f"Vision analysis failed for image {index}/{total}: {last_exc}")

    async def _analyze_ephemeral_images_serially(
        self,
        images: list[tuple[bytes, str]],
        user_prompt: str,
        domain_hint: str | None = None,
        backoff_on_start: bool = False,
    ) -> VisionExtractionResult:
        if backoff_on_start:
            await asyncio.sleep(1.5)

        results: list[VisionExtractionResult] = []
        for i, img_tuple in enumerate(images):
            if i > 0:
                # Small pause between serial calls to prevent rate limit bursts
                await asyncio.sleep(0.5)

            single_prompt = (
                f"Image {i + 1} of {len(images)}:\n{user_prompt.strip()}"
                if user_prompt and user_prompt.strip()
                else f"Extract the useful context from image {i + 1} of {len(images)}."
            )
            res = await self._analyze_single_image(
                img_tuple,
                single_prompt,
                domain_hint,
                index=i + 1,
                total=len(images),
            )
            results.append(res)

        return self._merge_results(results, len(images))

    def _merge_results(
        self, results: list[VisionExtractionResult], count: int
    ) -> VisionExtractionResult:
        if not results:
            raise VisionValidationError("No extraction results to merge.")
        if len(results) == 1:
            return results[0]

        summary_lines = [f"Visual analysis across {count} images:"]
        ocr_blocks: list[str] = []
        actions: list[dict[str, Any]] = []
        facts: list[str] = []
        domain_scores: dict[str, int] = {
            "COLLEGE": 5,
            "INTERNSHIP": 4,
            "STARTUP": 3,
            "PERSONAL": 2,
            "OPERATOR": 1,
        }
        best_domain = "OPERATOR"
        best_domain_score = 0

        seen_action_keys: set[str] = set()
        seen_facts: set[str] = set()

        for i, r in enumerate(results):
            summary_lines.append(f"• Image {i + 1}: {r.summary}")
            if r.extracted_text_or_code.strip():
                ocr_blocks.append(f"[Image {i + 1} Text/OCR]:\n{r.extracted_text_or_code.strip()}")

            score = domain_scores.get(r.detected_domain, 1)
            if score > best_domain_score:
                best_domain_score = score
                best_domain = r.detected_domain

            for action in r.actionable_items:
                title = str(action.get("title") or action.get("details") or "").strip().lower()
                if title and title not in seen_action_keys:
                    seen_action_keys.add(title)
                    actions.append(action)

            for fact in r.memory_facts:
                f_clean = str(fact).strip()
                if f_clean and f_clean.lower() not in seen_facts:
                    seen_facts.add(f_clean.lower())
                    facts.append(f_clean)

        return VisionExtractionResult(
            summary="\n".join(summary_lines),
            extracted_text_or_code="\n\n".join(ocr_blocks),
            detected_domain=best_domain,
            actionable_items=actions,
            memory_facts=facts,
            provider=results[0].provider,
            model=results[0].model,
        )

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
    def persisted_user_message(
        prompt: str, result: VisionExtractionResult, count: int = 1
    ) -> str:
        clean_prompt = (prompt or "").strip() or (
            "Shared images for visual context."
            if count > 1
            else "Shared an image for visual context."
        )
        summary = " ".join(result.summary.split())[:220]
        badge = (
            f"📷 Visual Context Processed ({count} images): {summary}"
            if count > 1
            else f"📷 Visual Context Processed: {summary}"
        )
        return f"{clean_prompt}\n\n[{badge}]"

    async def process_ephemeral_turn(
        self,
        *,
        db: Session,
        user: User,
        images: list[tuple[bytes, str]] | None = None,
        image_bytes: bytes | None = None,
        mime_type: str | None = None,
        prompt: str,
        conversation_id: int | None = None,
        domain_hint: str | None = None,
        agent: Any | None = None,
    ) -> tuple[Any, VisionExtractionResult, Any]:
        """Analyze, persist context-only memory, then run the normal IRIS turn."""
        img_list: list[tuple[bytes, str]] = []
        if images:
            img_list.extend(images)
        if image_bytes:
            img_list.append((image_bytes, mime_type or "image/png"))
        if not img_list:
            raise VisionValidationError("No image provided for visual turn.")

        result = await self.analyze_ephemeral_images(
            img_list, prompt, domain_hint
        )
        # Do not trust a caller-supplied conversation_id for memory ownership;
        # link the memory to the conversation actually resolved by the agent.
        memory = self.store_visual_context(db, user, result)
        count_label = f" ({len(img_list)} images)" if len(img_list) > 1 else ""
        enriched = f"{self.context_block(result)}\n\nUSER REQUEST{count_label}:\n{prompt.strip()}"
        persisted = self.persisted_user_message(prompt, result, count=len(img_list))

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
                "image_count": len(img_list),
            },
        )
        if memory is not None:
            memory.conversation_id = response.conversation_id
            db.commit()
        return response, result, memory


vision_service = VisionService()
