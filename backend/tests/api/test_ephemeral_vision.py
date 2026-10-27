"""Ephemeral vision pipeline and strict zero-image-storage guarantees."""

from __future__ import annotations

import json

import pytest

from app.ai.provider import ChatMessage, ChatResult
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.core.config import settings
from app.core.database import Base
from app.models.ai_conversation import AIMessage
from app.models.ai_memory import AIMemory
from app.services.vision_service import (
    VisionService,
    VisionValidationError,
    vision_service,
)

PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
PNG_BYTES = __import__("base64").b64decode(PNG_B64)
PNG_FRAGMENT = "iVBORw0KGgo"


class FakeVisionProvider:
    name = "nvidia"
    model = "nvidia/nemotron-3.5-super-vl-120b-a12b"
    enabled = True

    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []
        self.kwargs: dict = {}

    async def chat(self, messages, **kwargs):
        self.messages = [
            ChatMessage(role=m.role, content=m.content, images=list(m.images))
            for m in messages
        ]
        self.kwargs = kwargs
        return ChatResult(
            content=json.dumps(
                {
                    "summary": "Receipt from Blue Bottle for 8.50 USD.",
                    "extracted_text_or_code": "BLUE BOTTLE COFFEE\\nTOTAL 8.50",
                    "detected_domain": "personal",
                    "actionable_items": [
                        {
                            "kind": "expense",
                            "title": "Blue Bottle coffee",
                            "amount": 8.5,
                            "merchant": "Blue Bottle",
                            "category": "Food & Dining",
                        }
                    ],
                    "memory_facts": ["User bought coffee at Blue Bottle for 8.50 USD."],
                }
            )
        )


def _database_text(db) -> str:
    db.expire_all()
    chunks: list[str] = []
    for table in Base.metadata.sorted_tables:
        for row in db.execute(table.select()).mappings():
            for value in row.values():
                if isinstance(value, str):
                    chunks.append(value)
                elif isinstance(value, (dict, list)):
                    chunks.append(json.dumps(value, default=str))
                elif value is not None:
                    chunks.append(str(value))
    return "\n".join(chunks)


@pytest.mark.asyncio
async def test_vision_service_formats_multimodal_payload(monkeypatch):
    fake = FakeVisionProvider()
    monkeypatch.setattr(vision_service, "_provider_override", fake)

    result = await vision_service.analyze_ephemeral_image(
        PNG_BYTES, "image/png", "Log this receipt", domain_hint="PERSONAL"
    )

    assert result.detected_domain == "PERSONAL"
    assert result.actionable_items[0]["merchant"] == "Blue Bottle"
    assert fake.kwargs["response_format"] == {"type": "json_object"}
    assert len(fake.messages) == 2
    assert fake.messages[1].images[0].startswith("data:image/png;base64,")
    assert fake.messages[1].images[0].endswith(PNG_B64)
    assert PNG_B64 not in result.model_dump_json()


def test_openai_compatible_serializes_image_parts():
    provider = OpenAICompatibleProvider(
        name="nvidia",
        base_url="https://integrate.api.nvidia.com/v1",
        model="nvidia/nemotron-3.5-super-vl-120b-a12b",
        api_key="test",
    )
    messages = [
        ChatMessage(
            role="user",
            content="Read this",
            images=[f"data:image/png;base64,{PNG_B64}"],
        )
    ]

    serialized = provider._serialize_messages(messages)

    assert serialized[0]["role"] == "user"
    parts = serialized[0]["content"]
    assert parts[0] == {"type": "text", "text": "Read this"}
    assert parts[1] == {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{PNG_B64}"},
    }


def test_vision_provider_falls_back_without_misusing_gemini_key(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setattr(settings, "vision_provider", "nvidia")
    monkeypatch.setattr(settings, "nvidia_api_key", None)
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "ai_api_key", "gemini-only-key")

    provider = VisionService()._build_provider()

    assert provider.name == "gemini"
    assert provider.model == settings.vision_fallback_model


@pytest.mark.asyncio
async def test_vision_service_rejects_unsupported_payload(monkeypatch):
    monkeypatch.setattr(vision_service, "_provider_override", FakeVisionProvider())
    with pytest.raises(VisionValidationError):
        await vision_service.analyze_ephemeral_image(b"not an image", "image/png", "read")


def test_vision_ingest_stores_context_but_never_base64(client, db, monkeypatch):
    monkeypatch.setattr(vision_service, "_provider_override", FakeVisionProvider())

    response = client.post(
        "/api/vision/ingest",
        json={
            "image_base64": PNG_B64,
            "mime_type": "image/png",
            "prompt": "Log this receipt",
            "domain_hint": "PERSONAL",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["visual_context"]["summary"].startswith("Receipt from Blue Bottle")
    assert payload["image_persisted"] is False
    assert payload["actions_taken"] == []

    memory = (
        db.query(AIMemory)
        .filter(AIMemory.category == "VISUAL_CONTEXT")
        .order_by(AIMemory.id.desc())
        .first()
    )
    assert memory is not None
    assert "Blue Bottle" in memory.content
    assert "BLUE BOTTLE COFFEE" in memory.content
    assert memory.conversation_id == payload["conversation_id"]
    assert PNG_FRAGMENT not in memory.content

    user_message = (
        db.query(AIMessage)
        .filter(AIMessage.role == "USER")
        .order_by(AIMessage.id.desc())
        .first()
    )
    assert user_message is not None
    assert "Log this receipt" in user_message.content
    assert "[📷 Visual Context Processed:" in user_message.content

    assistant_message = (
        db.query(AIMessage)
        .filter(AIMessage.role == "ASSISTANT")
        .order_by(AIMessage.id.desc())
        .first()
    )
    assert assistant_message is not None
    assert assistant_message.metadata_json["image_persisted"] is False
    assert assistant_message.metadata_json["memory_pending"] is False
    assert "visual_context" in assistant_message.metadata_json

    database_text = _database_text(db)
    assert "Blue Bottle" in database_text
    assert PNG_B64 not in database_text
    assert PNG_FRAGMENT not in database_text


def test_vision_accepts_multipart_without_disk_storage(client, db, monkeypatch):
    monkeypatch.setattr(vision_service, "_provider_override", FakeVisionProvider())

    response = client.post(
        "/api/vision/ingest",
        files={"image": ("receipt.png", PNG_BYTES, "image/png")},
        data={"prompt": "What did I buy?"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["visual_context"]["detected_domain"] == "PERSONAL"
    assert PNG_FRAGMENT not in _database_text(db)


def test_chat_message_accepts_transient_image_and_strips_it(client, db, monkeypatch):
    monkeypatch.setattr(vision_service, "_provider_override", FakeVisionProvider())
    conversation = client.post("/api/chat/conversations", params={"title": "Vision"})
    assert conversation.status_code == 201
    conversation_id = conversation.json()["id"]

    response = client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={
            "content": "Log this receipt",
            "image_base64": PNG_B64,
            "mime_type": "image/png",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["visual_context"]["summary"].startswith("Receipt from Blue Bottle")
    assert body["conversation_id"] == conversation_id

    database_text = _database_text(db)
    assert PNG_B64 not in database_text
    assert PNG_FRAGMENT not in database_text
    assert "Blue Bottle" in database_text

    # Verify conversation detail endpoint preserves visual_context
    conv_res = client.get(f"/api/chat/conversations/{conversation_id}")
    assert conv_res.status_code == 200
    detail = conv_res.json()
    assert len(detail["messages"]) > 0
    assistant_msg = next((m for m in detail["messages"] if m["role"] == "ASSISTANT"), None)
    assert assistant_msg is not None
    assert assistant_msg["visual_context"] is not None
    assert assistant_msg["visual_context"]["detected_domain"] == "PERSONAL"


def test_chat_message_accepts_image_without_text(client, db, monkeypatch):
    monkeypatch.setattr(vision_service, "_provider_override", FakeVisionProvider())
    conversation = client.post("/api/chat/conversations", params={"title": "Vision Empty Prompt"})
    assert conversation.status_code == 201
    conversation_id = conversation.json()["id"]

    response = client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={
            "content": "",
            "image_base64": PNG_B64,
            "mime_type": "image/png",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["visual_context"]["summary"].startswith("Receipt from Blue Bottle")
    assert body["conversation_id"] == conversation_id


def test_chat_message_accepts_multiple_images(client, db, monkeypatch):
    fake = FakeVisionProvider()
    monkeypatch.setattr(vision_service, "_provider_override", fake)
    conversation = client.post("/api/chat/conversations", params={"title": "Multi Vision"})
    assert conversation.status_code == 201
    conversation_id = conversation.json()["id"]

    response = client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={
            "content": "Analyze both diagrams",
            "images": [
                {"image_base64": PNG_B64, "mime_type": "image/png"},
                {"image_base64": PNG_B64, "mime_type": "image/png"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["visual_context"]["summary"].startswith("Receipt from Blue Bottle")
    assert body["conversation_id"] == conversation_id

    # Verify both images were passed to the multimodal provider
    assert len(fake.messages) == 2
    assert len(fake.messages[1].images) == 2
    for img_uri in fake.messages[1].images:
        assert img_uri.startswith("data:image/png;base64,")

    # Verify user message recorded the multi-image badge
    user_msg = (
        db.query(AIMessage)
        .filter(AIMessage.conversation_id == conversation_id, AIMessage.role == "USER")
        .first()
    )
    assert user_msg is not None
    assert "Analyze both diagrams" in user_msg.content
    assert "[📷 Visual Context Processed (2 images):" in user_msg.content

    # Strict zero-storage assertion
    database_text = _database_text(db)
    assert PNG_B64 not in database_text
    assert PNG_FRAGMENT not in database_text


def test_vision_ingest_accepts_multiple_images(client, db, monkeypatch):
    fake = FakeVisionProvider()
    monkeypatch.setattr(vision_service, "_provider_override", fake)

    response = client.post(
        "/api/vision/ingest",
        json={
            "images": [
                {"image_base64": PNG_B64, "mime_type": "image/png"},
                {"image_base64": PNG_B64, "mime_type": "image/png"},
                {"image_base64": PNG_B64, "mime_type": "image/png"},
            ],
            "prompt": "Compare these three screenshots",
        },
    )
    assert response.status_code == 200, response.text
    assert len(fake.messages[1].images) == 3
    assert PNG_FRAGMENT not in _database_text(db)


def test_chat_message_does_not_duplicate_image_when_both_fields_sent(client, db, monkeypatch):
    fake = FakeVisionProvider()
    monkeypatch.setattr(vision_service, "_provider_override", fake)
    conversation = client.post("/api/chat/conversations", params={"title": "Multi Vision No Dup"})
    assert conversation.status_code == 201
    conversation_id = conversation.json()["id"]

    response = client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={
            "content": "Check both images",
            "image_base64": PNG_B64,
            "mime_type": "image/png",
            "images": [
                {"image_base64": PNG_B64, "mime_type": "image/png"},
                {"image_base64": PNG_B64, "mime_type": "image/png"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    # Exactly 2 images must be processed, NOT 3
    assert len(fake.messages[1].images) == 2


@pytest.mark.asyncio
async def test_vision_service_serial_processing_fallback_on_rate_limit(monkeypatch):
    class RateLimitedBatchProvider:
        name = "gemini"
        model = "gemini-3.1-flash-lite"
        enabled = True

        def __init__(self):
            self.call_count = 0

        async def chat(self, messages, **kwargs):
            self.call_count += 1
            # If batch (more than 1 image), simulate rate limit 429
            user_msg = next(m for m in messages if m.role == "user")
            if len(user_msg.images) > 1:
                raise RuntimeError("HTTP 429: Too Many Requests - Rate limit exceeded")
            return ChatResult(
                content=json.dumps(
                    {
                        "summary": f"Image {self.call_count} processed successfully.",
                        "extracted_text_or_code": f"TEXT_{self.call_count}",
                        "detected_domain": "STARTUP",
                        "actionable_items": [{"kind": "task", "title": f"Action {self.call_count}"}],
                        "memory_facts": [f"Fact {self.call_count}"],
                    }
                )
            )

    provider = RateLimitedBatchProvider()
    monkeypatch.setattr(vision_service, "_provider_override", provider)

    result = await vision_service.analyze_ephemeral_images(
        [(PNG_BYTES, "image/png"), (PNG_BYTES, "image/png")],
        user_prompt="Analyze these documents",
    )

    # 1 batch call (failed with 429) + 2 serial calls = 3 total calls
    assert provider.call_count == 3
    assert result.detected_domain == "STARTUP"
    assert "TEXT_2" in result.extracted_text_or_code
    assert "TEXT_3" in result.extracted_text_or_code
    assert len(result.actionable_items) == 2
    assert "Image 1:" in result.summary
    assert "Image 2:" in result.summary

