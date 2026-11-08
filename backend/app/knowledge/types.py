"""Shared knowledge vocabulary, classification rules and small utilities."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.value


class NodeType(StrEnum):
    PERSON = "person"
    PROJECT = "project"
    GOAL = "goal"
    ORGANISATION = "organisation"
    TECHNOLOGY = "technology"
    CONCEPT = "concept"
    DOCUMENT = "document"
    EVENT = "event"
    DECISION = "decision"
    PREFERENCE = "preference"
    EXPERIENCE = "experience"
    INSIGHT = "insight"
    TOPIC = "topic"


class ClaimType(StrEnum):
    FACT = "fact"
    OBSERVATION = "observation"
    EXPERIENCE = "experience"
    UNDERSTANDING = "understanding"
    INFERENCE = "inference"
    DECISION = "decision"


class VerificationStatus(StrEnum):
    USER_STATED = "user_stated"
    SOURCE_SUPPORTED = "source_supported"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    INFERRED = "inferred"
    DISPUTED = "disputed"
    SUPERSEDED = "superseded"


class Sensitivity(StrEnum):
    ORDINARY = "ordinary"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


SENSITIVITY_ORDER = {
    Sensitivity.ORDINARY.value: 0,
    Sensitivity.PERSONAL.value: 1,
    Sensitivity.SENSITIVE.value: 2,
    Sensitivity.RESTRICTED.value: 3,
}


class AccessLevel(StrEnum):
    SHARED = "shared"
    PERSONAL = "personal"
    RESTRICTED = "restricted"
    PRIVATE_WORKSPACE = "private_workspace"


class JobType(StrEnum):
    EXTRACT_KNOWLEDGE = "extract_knowledge"
    GENERATE_EMBEDDINGS = "generate_embeddings"
    UPDATE_MARKDOWN = "update_markdown"
    RECONCILE_VAULT = "reconcile_vault"
    RESOLVE_ENTITIES = "resolve_entities"
    DETECT_CONTRADICTIONS = "detect_contradictions"
    REBUILD_INDEXES = "rebuild_indexes"
    CONSOLIDATE_KNOWLEDGE = "consolidate_knowledge"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD = "dead"


# Categories map to the vault's top-level folders.
CATEGORY_FOLDERS: dict[str, str] = {
    "personal": "01-Personal",
    "projects": "02-Projects",
    "goals": "03-Goals",
    "work": "04-Work",
    "financial": "05-Financial",
    "learning": "06-Learning",
    "decisions": "07-Decisions",
    "experiences": "08-Insights",
    "insights": "08-Insights",
    "daily": "09-Daily",
    "general": "00-Index",
}

CATEGORY_LABELS: dict[str, str] = {
    "personal": "Personal",
    "projects": "Projects",
    "goals": "Goals",
    "work": "Work",
    "financial": "Financial",
    "learning": "Learning",
    "decisions": "Decisions",
    "experiences": "Experiences",
    "insights": "Insights",
    "daily": "Daily",
    "general": "General",
}

NODE_TYPE_CATEGORY: dict[str, str] = {
    NodeType.PROJECT.value: "projects",
    NodeType.GOAL.value: "goals",
    NodeType.DECISION.value: "decisions",
    NodeType.PERSON.value: "personal",
    NodeType.PREFERENCE.value: "personal",
    NodeType.EXPERIENCE.value: "experiences",
    NodeType.INSIGHT.value: "insights",
    NodeType.ORGANISATION.value: "work",
    NodeType.TECHNOLOGY.value: "learning",
    NodeType.TOPIC.value: "learning",
    NodeType.CONCEPT.value: "learning",
    NodeType.DOCUMENT.value: "learning",
    NodeType.EVENT.value: "daily",
}

# Node types whose content is private unless an explicit grant exists.
SENSITIVE_NODE_TYPES = {
    NodeType.PERSON.value,
    NodeType.PREFERENCE.value,
    NodeType.EXPERIENCE.value,
    NodeType.INSIGHT.value,
}

FINANCIAL_TERMS = {
    "salary", "income", "expense", "bank", "account", "loan", "emi", "investment",
    "portfolio", "net worth", "budget", "rent", "credit card", "upi", "tax",
}
HEALTH_TERMS = {
    "medical", "diagnosis", "doctor", "prescription", "therapy", "mental health",
    "blood", "report", "hospital", "medication", "anxiety", "depression",
}
PERSONAL_TERMS = {
    "my family", "my father", "my mother", "my sister", "my brother", "girlfriend",
    "boyfriend", "wife", "husband", "home address", "phone number", "aadhaar",
    "passport", "birthday",
}

CREDENTIAL_PATTERNS = [
    re.compile(r"(?i)\b(password|passwd|pwd|passphrase)\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(api[_\s-]?key|access[_\s-]?token|auth[_\s-]?token|bearer)\b\s*[:=]?\s*[A-Za-z0-9_\-\.]{12,}"),
    re.compile(r"(?i)\bsecret[_\s-]?key\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(client_secret|app_secret|private_key)\b\s*[:=]\s*\S+"),
    re.compile(r"-----BEGIN [A-Z0-9_\- ]*PRIVATE KEY-----[^-]*?(?:-----END [A-Z0-9_\- ]*PRIVATE KEY-----|$)", re.DOTALL),
    re.compile(r"(?i)\b(recovery|backup)\s+code(s)?\b\s*[:=]\s*\S+"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_\-\.\+/=]{10,}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-_.~+/]{20,}=*\b"),
    re.compile(r"(?i)(postgres|postgresql|mysql|mongodb|redis):\/\/[^\s:]+:[^\s@]+@[^\s]+"),
    re.compile(r"\bsb_[a-zA-Z0-9_\-]{20,}\b"),
    re.compile(r"\b(AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bglpat-[0-9a-zA-Z\-_]{20,}\b"),
    re.compile(r"\bsk-(proj-)?[A-Za-z0-9\-_]{16,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b"),
    re.compile(r"(?i)\b(basic\s+[A-Za-z0-9\+/=]{24,})\b"),
]


def utcnow() -> datetime:
    """Naive UTC, matching the rest of the IRIS persistence layer."""
    return datetime.now(UTC).replace(tzinfo=None)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def normalize_entity_name(value: str) -> str:
    """Stable identity key for entity resolution (not a display name)."""
    text = normalize_text(value)
    text = re.sub(r"^(the|a|an)\s+", "", text)
    text = re.sub(r"[^a-z0-9\s\-_.]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def content_fingerprint(value: str) -> str:
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()


def hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def slugify(value: str, fallback: str = "note") -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9\s\-_]", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return (text or fallback)[:80]


def contains_credential(text: str) -> bool:
    """Credential material must never enter the knowledge store or vault."""
    return any(pattern.search(text or "") for pattern in CREDENTIAL_PATTERNS)


def redact_credentials(text: str) -> str:
    cleaned = text or ""
    for pattern in CREDENTIAL_PATTERNS:
        cleaned = pattern.sub("[redacted credential]", cleaned)
    return cleaned


def classify_sensitivity(text: str, node_type: str | None = None) -> str:
    """Deterministic, explainable sensitivity classification."""
    lower = (text or "").lower()
    if contains_credential(lower):
        return Sensitivity.RESTRICTED.value
    if any(term in lower for term in HEALTH_TERMS):
        return Sensitivity.SENSITIVE.value
    if any(term in lower for term in FINANCIAL_TERMS):
        return Sensitivity.SENSITIVE.value
    if any(term in lower for term in PERSONAL_TERMS):
        return Sensitivity.PERSONAL.value
    if node_type in SENSITIVE_NODE_TYPES:
        return Sensitivity.PERSONAL.value
    return Sensitivity.ORDINARY.value


def max_sensitivity(*values: str | None) -> str:
    best = Sensitivity.ORDINARY.value
    for value in values:
        if not value:
            continue
        if SENSITIVITY_ORDER.get(value, 0) > SENSITIVITY_ORDER.get(best, 0):
            best = value
    return best


def access_for_sensitivity(sensitivity: str) -> str:
    if sensitivity == Sensitivity.RESTRICTED.value:
        return AccessLevel.RESTRICTED.value
    if sensitivity in {Sensitivity.PERSONAL.value, Sensitivity.SENSITIVE.value}:
        return AccessLevel.PERSONAL.value
    return AccessLevel.SHARED.value


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
