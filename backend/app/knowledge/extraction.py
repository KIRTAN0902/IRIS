"""Automatic, silent knowledge extraction.

The deterministic extractor is always available and is the tested baseline.
When an AI provider is configured, structured extraction is attempted first;
its output is validated, filtered for credentials and never allowed to upgrade
an inference into a verified fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.knowledge.types import (
    ClaimType,
    NodeType,
    Sensitivity,
    VerificationStatus,
    classify_sensitivity,
    contains_credential,
    redact_credentials,
)

logger = get_logger("iris.knowledge.extraction")

_TRIVIAL = {
    "hi", "hello", "hey", "hey iris", "hi iris", "thanks", "thank you", "ok",
    "okay", "cool", "nice", "got it", "bye", "good morning", "good evening",
    "good night", "how are you", "how are you doing", "what time is it",
    "what's the time", "what day is today", "what date is today",
}

_DECISION = re.compile(
    r"\b(?:we|i)\s+(?:have\s+)?(?:decided|decide|chose|choose|agreed|settled)\b"
    r"|\b(?:we|i)(?:'re|\s+are)\s+(?:going\s+to|gonna)\s+(?:use|adopt|build|move)\b"
    r"|\b(?:decision|decided)\s*[:\-]"
    r"|\b(?:migrated|migrating|switched|switching)\s+to\b"
    r"|\b(?:let'?s|we will|we'll|i will|i'll)\s+(?:use|adopt|go\s+with|build)\b",
    re.I,
)
_PREFERENCE = re.compile(
    r"\b(?:i|we)\s+(?:really\s+)?(?:prefer|like|love|hate|dislike|always|never|usually)\b"
    r"|\bmy\s+(?:preference|preferred)\b|\bfrom now on\b|\bplease always\b",
    re.I,
)
_GOAL = re.compile(
    r"\bmy\s+goal\s+is\b|\bi\s+(?:want|plan|aim|intend)\s+to\b|\bmy\s+(?:target|objective)\s+is\b"
    r"|\bi(?:'m| am)\s+working\s+(?:on|towards)\b",
    re.I,
)
_EXPERIENCE = re.compile(
    r"\b(?:today|yesterday|last\s+(?:week|month|night))\s+i\b|\bi\s+(?:felt|experienced|visited|tried|learned|learnt|realised|realized)\b",
    re.I,
)
_INFERENCE = re.compile(
    r"\b(?:i\s+think|i\s+guess|probably|likely|maybe|might|seems?|appears?|suspect|possibly)\b",
    re.I,
)
_OBSERVATION = re.compile(r"\bi\s+(?:noticed|observed|saw|found)\b", re.I)
_FACT = re.compile(
    r"\bmy\s+\w[\w\s]{0,40}\s+(?:is|are|was|were)\b|\bi\s+(?:work|study|live|use|run)\b"
    r"|\b(?:is|are|uses|runs\s+on|built\s+with|depends\s+on)\b",
    re.I,
)
_EXPLICIT_REMEMBER = re.compile(
    r"\b(?:remember|note|keep in mind)\s+(?:that\s+)?(.+)$", re.I
)

_TECHNOLOGIES = {
    "python", "typescript", "javascript", "react", "vite", "fastapi", "postgresql",
    "postgres", "supabase", "pgvector", "vercel", "electron", "capacitor", "android",
    "openai", "gemini", "nvidia", "groq", "docker", "redis", "sqlite", "sqlalchemy",
    "tailwind", "obsidian", "git", "github", "figma", "next.js", "node", "llm",
}
_PROJECT_HINTS = re.compile(
    r"\b(?:project|app|system|platform|product|startup|repo|repository)\s+([A-Z][A-Za-z0-9_.\-]{1,40})"
)
_PERSON_HINTS = [
    re.compile(r"\bmy\s+(co-?founder|teammate|friend|colleague|manager|mentor)\s+(?:is\s+)?([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)"),
    re.compile(r"\b(?:with|met)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)"),
]
_GOAL_HINTS = re.compile(r"\b(?:my\s+goal\s+is\s+to|i\s+want\s+to|i\s+plan\s+to|i\s+aim\s+to)\s+(.+)$", re.I)
_DECISION_HINTS = re.compile(
    r"\b(?:we|i)\s+(?:have\s+)?(?:decided|agreed|chose)\s+(?:to\s+)?(.+)$"
    r"|\b(?:decision|decided)\s*[:\-]\s*(.+)$"
    r"|\b(?:migrated|switched)\s+to\s+(.+)$",
    re.I,
)

CATEGORY_BY_TYPE = {
    NodeType.PROJECT.value: "projects",
    NodeType.GOAL.value: "goals",
    NodeType.DECISION.value: "decisions",
    NodeType.PERSON.value: "personal",
    NodeType.PREFERENCE.value: "personal",
    NodeType.EXPERIENCE.value: "experiences",
    NodeType.INSIGHT.value: "insights",
    NodeType.EVENT.value: "daily",
    NodeType.ORGANISATION.value: "work",
    NodeType.TECHNOLOGY.value: "learning",
    NodeType.TOPIC.value: "learning",
    NodeType.CONCEPT.value: "learning",
    NodeType.DOCUMENT.value: "learning",
}


class LLMRelationship(BaseModel):
    target_name: str
    target_type: str = "topic"
    relationship_type: str | None = None


class LLMClaim(BaseModel):
    text: str
    claim_type: str = "fact"
    node_name: str
    node_type: str = "topic"
    category: str = "general"
    verification_status: str = "unverified"
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    sensitivity: str | None = None
    relationships: list[LLMRelationship] = Field(default_factory=list)


class LLMKnowledgeExtraction(BaseModel):
    items: list[LLMClaim] = Field(default_factory=list)


@dataclass
class ExtractionResult:
    items: list[dict[str, Any]] = field(default_factory=list)
    method: str = "heuristic"
    excluded: int = 0
    skipped_reason: str | None = None


def is_trivial(text: str) -> bool:
    clean = (text or "").strip().lower().rstrip("?.! ")
    return len(clean) < 12 or clean in _TRIVIAL


def _safe_sentences(text: str) -> tuple[list[str], int]:
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    safe: list[str] = []
    excluded = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if contains_credential(sentence):
            excluded += 1
            continue
        safe.append(sentence)
    return safe, excluded


def _known_technologies(text: str) -> list[str]:
    lower = text.lower()
    found = []
    for technology in sorted(_TECHNOLOGIES):
        if re.search(rf"\b{re.escape(technology)}\b", lower):
            found.append(technology)
    return found[:4]


def _node_for_sentence(sentence: str) -> tuple[str, str, list[dict[str, Any]]]:
    """Return (node_name, node_type, relationships)."""
    relationships: list[dict[str, Any]] = []

    project_match = _PROJECT_HINTS.search(sentence)
    if project_match:
        name = project_match.group(1).strip(" .,:;")
        for technology in _known_technologies(sentence):
            relationships.append(
                {
                    "target_name": technology.title() if len(technology) > 3 else technology.upper(),
                    "target_type": NodeType.TECHNOLOGY.value,
                    "relationship_type": "USES",
                }
            )
        return name, NodeType.PROJECT.value, relationships

    for pattern in _PERSON_HINTS:
        person = pattern.search(sentence)
        if person:
            name = person.group(2).strip(" .,:;")
            if name and name.lower() not in {"iris", "today", "yesterday"}:
                return name, NodeType.PERSON.value, relationships

    if _DECISION.search(sentence):
        hint = _DECISION_HINTS.search(sentence)
        decision_text = (hint.group(1) if hint and hint.lastindex else sentence).strip()
        name = "Decision: " + decision_text[:110].rstrip(" .")
        for technology in _known_technologies(sentence):
            relationships.append(
                {
                    "target_name": technology.title() if len(technology) > 3 else technology.upper(),
                    "target_type": NodeType.TECHNOLOGY.value,
                    "relationship_type": "AFFECTS",
                }
            )
        return name, NodeType.DECISION.value, relationships

    goal = _GOAL_HINTS.search(sentence)
    if goal:
        return "Goal: " + goal.group(1).strip()[:110].rstrip(" ."), NodeType.GOAL.value, relationships

    if _PREFERENCE.search(sentence):
        subject = re.sub(r"^(?:i|we)\s+", "", sentence, flags=re.I)
        return "Preference: " + subject[:100].rstrip(" ."), NodeType.PREFERENCE.value, relationships

    if _EXPERIENCE.search(sentence):
        return "Experience: " + sentence[:100].rstrip(" ."), NodeType.EXPERIENCE.value, relationships

    if _INFERENCE.search(sentence):
        return "Insight: " + sentence[:100].rstrip(" ."), NodeType.INSIGHT.value, relationships

    technologies = _known_technologies(sentence)
    if technologies:
        relationships = [
            {
                "target_name": tech.title() if len(tech) > 3 else tech.upper(),
                "target_type": NodeType.TECHNOLOGY.value,
                "relationship_type": "USES",
            }
            for tech in technologies
        ]
        return technologies[0].title() if len(technologies[0]) > 3 else technologies[0].upper(), NodeType.TECHNOLOGY.value, relationships

    # Generic durable fact: use the subject before the first predicate.
    subject_match = re.match(
        r"(?P<subject>.{2,80}?)\s+(?:is|are|uses|works|runs|depends|prefers|needs|requires)\b",
        sentence,
        re.I,
    )
    subject = (subject_match.group("subject") if subject_match else sentence[:80]).strip(" .,:;")
    return subject or "General Knowledge", NodeType.TOPIC.value, relationships


def classify_sentence(
    sentence: str, *, origin: str = "conversation"
) -> tuple[str, str, float]:
    lower = sentence.lower()
    if _INFERENCE.search(lower):
        return ClaimType.INFERENCE.value, VerificationStatus.INFERRED.value, 0.45
    if _DECISION.search(lower):
        status = (
            VerificationStatus.USER_STATED.value
            if origin in {"user", "conversation", "user_explicit"}
            else VerificationStatus.SOURCE_SUPPORTED.value
        )
        return ClaimType.DECISION.value, status, 0.85
    if _PREFERENCE.search(lower):
        return ClaimType.FACT.value, (
            VerificationStatus.USER_STATED.value if origin in {"user", "conversation", "user_explicit"} else VerificationStatus.SOURCE_SUPPORTED.value
        ), 0.8
    if _EXPERIENCE.search(lower):
        return ClaimType.EXPERIENCE.value, VerificationStatus.USER_STATED.value, 0.75
    if _OBSERVATION.search(lower):
        return ClaimType.OBSERVATION.value, VerificationStatus.USER_STATED.value, 0.65
    if _GOAL.search(lower):
        return ClaimType.FACT.value, VerificationStatus.USER_STATED.value, 0.8
    if origin in {"user", "conversation", "user_explicit"}:
        return ClaimType.FACT.value, VerificationStatus.USER_STATED.value, 0.65
    return ClaimType.UNDERSTANDING.value, VerificationStatus.SOURCE_SUPPORTED.value, 0.55


def heuristic_extract(text: str, *, origin: str = "conversation") -> ExtractionResult:
    if is_trivial(text):
        return ExtractionResult(skipped_reason="trivial")
    sentences, excluded = _safe_sentences(text)
    if not sentences:
        return ExtractionResult(excluded=excluded, skipped_reason="credentials_only")

    # An explicit "remember that …" instruction is always durable.
    remember = _EXPLICIT_REMEMBER.search(text)
    if remember:
        sentences = [remember.group(1).strip()] + sentences

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sentence in sentences[:12]:
        clean = sentence.strip()
        if len(clean) < 12:
            continue
        if not (
            _DECISION.search(clean)
            or _PREFERENCE.search(clean)
            or _GOAL.search(clean)
            or _EXPERIENCE.search(clean)
            or _INFERENCE.search(clean)
            or _OBSERVATION.search(clean)
            or _FACT.search(clean)
            or remember
        ):
            continue
        node_name, node_type, relationships = _node_for_sentence(clean)
        claim_type, verification, confidence = classify_sentence(clean, origin=origin)
        if claim_type == ClaimType.INFERENCE.value:
            confidence = min(confidence, 0.55)
        category = CATEGORY_BY_TYPE.get(node_type, "general")
        sensitivity = classify_sensitivity(clean, node_type)
        key = f"{node_name.lower()}|{clean.lower()}"
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "text": clean[:2000],
                "claim_type": claim_type,
                "node_name": node_name[:200],
                "node_type": node_type,
                "category": category,
                "verification_status": verification,
                "confidence": confidence,
                "sensitivity": sensitivity,
                "relationships": relationships,
                "evidence_text": clean[:2000],
                "extraction_method": "heuristic",
                "metadata": {"origin": origin},
            }
        )
    return ExtractionResult(items=items, method="heuristic", excluded=excluded)


_EXTRACTION_SYSTEM = """You extract durable knowledge for IRIS, a personal AI operating system.

Rules:
- Extract only facts, decisions, goals, preferences, experiences, observations and
  inferences that will still matter in future conversations.
- Never extract credentials, passwords, API keys, tokens, private keys or recovery codes.
- Do not invent information. If nothing durable is present, return an empty list.
- Keep claim text self-contained and faithful to the source.
- claim_type must be one of: fact, observation, experience, understanding, inference, decision.
- verification_status must be one of: user_stated, source_supported, unverified, inferred.
- Inferences must remain inferences; never present them as user-stated facts.
- node_type must be one of: person, project, goal, organisation, technology, concept,
  document, event, decision, preference, experience, insight, topic.
- sensitivity must be one of: ordinary, personal, sensitive, restricted.
- Maximum 10 items."""


async def llm_extract(text: str, *, origin: str) -> ExtractionResult:
    from app.ai.factory import get_ai_provider

    provider = get_ai_provider()
    if not provider.enabled:
        return heuristic_extract(text, origin=origin)
    try:
        result = await provider.generate_structured(
            system=_EXTRACTION_SYSTEM,
            prompt=f"Source kind: {origin}\n\nText:\n{text[:8000]}",
            schema=LLMKnowledgeExtraction,
        )
    except Exception as exc:  # noqa: BLE001 - extraction must never break chat
        logger.info("knowledge_llm_extraction_fallback error_type=%s", type(exc).__name__)
        return heuristic_extract(text, origin=origin)
    if not result or not result.items:
        return ExtractionResult(items=[], method="llm")
    allowed_types = {item.value for item in ClaimType}
    allowed_node_types = {item.value for item in NodeType}
    allowed_verification = {
        "user_stated", "source_supported", "verified", "unverified", "inferred",
    }
    allowed_sensitivity = {item.value for item in Sensitivity}
    items: list[dict[str, Any]] = []
    excluded = 0
    for raw in result.items[:10]:
        if contains_credential(raw.text) or contains_credential(raw.node_name):
            excluded += 1
            continue
        claim_type = raw.claim_type if raw.claim_type in allowed_types else ClaimType.FACT.value
        node_type = raw.node_type if raw.node_type in allowed_node_types else NodeType.TOPIC.value
        verification = (
            raw.verification_status
            if raw.verification_status in allowed_verification
            else VerificationStatus.UNVERIFIED.value
        )
        if claim_type == ClaimType.INFERENCE.value:
            verification = VerificationStatus.INFERRED.value
        if origin not in {"user", "conversation", "user_explicit"} and verification == VerificationStatus.USER_STATED.value:
            verification = VerificationStatus.SOURCE_SUPPORTED.value
        sensitivity = (
            raw.sensitivity
            if raw.sensitivity in allowed_sensitivity
            else classify_sensitivity(raw.text, node_type)
        )
        items.append(
            {
                "text": redact_credentials(raw.text.strip())[:2000],
                "claim_type": claim_type,
                "node_name": raw.node_name.strip()[:200],
                "node_type": node_type,
                "category": raw.category or CATEGORY_BY_TYPE.get(node_type, "general"),
                "verification_status": verification,
                "confidence": float(raw.confidence),
                "sensitivity": sensitivity,
                "relationships": [relation.model_dump() for relation in raw.relationships[:5]],
                "evidence_text": redact_credentials(text)[:3000],
                "extraction_method": "llm",
                "metadata": {"origin": origin},
            }
        )
    return ExtractionResult(items=items, method="llm", excluded=excluded)


def to_payload(result: ExtractionResult) -> dict[str, Any]:
    return {
        "items": result.items,
        "method": result.method,
        "excluded": result.excluded,
        "skipped_reason": result.skipped_reason,
    }
