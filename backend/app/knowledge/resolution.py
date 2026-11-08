"""Deduplication, entity resolution and temporal contradiction heuristics.

These functions are deliberately conservative: uncertain identities are never
merged, and a contradiction is only recorded when the subject and predicate
match while the value changed. Anything else is stored as a separate claim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.knowledge.types import normalize_entity_name, normalize_text

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_\-]+")
_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "to", "of", "and",
    "or", "in", "on", "at", "for", "with", "that", "this", "it", "we", "i", "my",
    "our", "has", "have", "had", "will", "would", "can", "could", "should", "do",
    "does", "did", "using", "use", "uses", "used",
}

_PREDICATES = [
    ("migrated_to", re.compile(r"(?P<subject>.+?)\s+(?:has\s+)?migrated\s+to\s+(?P<object>.+)$", re.I)),
    ("switched_to", re.compile(r"(?P<subject>.+?)\s+(?:has\s+)?switched\s+to\s+(?P<object>.+)$", re.I)),
    ("decided_to_use", re.compile(r"(?P<subject>.+?)\s+(?:decided|chose|chosen)\s+to\s+(?:use|adopt)\s+(?P<object>.+)$", re.I)),
    ("uses", re.compile(r"(?P<subject>.+?)\s+(?:uses|is using|will use|adopts)\s+(?P<object>.+)$", re.I)),
    ("is", re.compile(r"(?P<subject>.+?)\s+(?:is|will be|has become)\s+(?P<object>.+)$", re.I)),
]


def tokens(text: str) -> set[str]:
    return {
        token for token in _TOKEN.findall((text or "").lower())
        if token not in _STOP and len(token) > 1
    }


def jaccard(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def is_near_duplicate(left: str, right: str, threshold: float = 0.9) -> bool:
    return jaccard(left, right) >= threshold


def is_refinement(existing: str, new: str) -> bool:
    """New adds detail to the existing statement without contradicting it."""
    existing_tokens, new_tokens = tokens(existing), tokens(new)
    if not existing_tokens or not new_tokens:
        return False
    return existing_tokens.issubset(new_tokens) and len(new_tokens) > len(existing_tokens)


@dataclass(frozen=True)
class Predicate:
    kind: str
    subject: str
    object: str


def extract_predicate(text: str) -> Predicate | None:
    clean = normalize_text(text).strip(" .")
    for kind, pattern in _PREDICATES:
        match = pattern.match(clean)
        if match:
            subject = re.sub(r"^(the|a|an)\s+", "", match.group("subject").strip())
            obj = match.group("object").strip()
            if subject and obj and len(subject) < 160 and len(obj) < 240:
                return Predicate(kind=kind, subject=subject, object=obj)
    return None


def detect_contradiction(existing_text: str, new_text: str) -> tuple[bool, str | None]:
    """Return (is_contradiction, reason) using conservative structural rules."""
    old = normalize_text(existing_text)
    new = normalize_text(new_text)
    if old == new:
        return False, None

    old_pred, new_pred = extract_predicate(old), extract_predicate(new)
    if old_pred and new_pred:
        same_subject = jaccard(old_pred.subject, new_pred.subject) >= 0.75 or (
            normalize_entity_name(old_pred.subject) == normalize_entity_name(new_pred.subject)
        )
        compatible_predicate = old_pred.kind == new_pred.kind or {
            old_pred.kind, new_pred.kind
        } <= {"migrated_to", "switched_to", "decided_to_use", "uses"}
        if same_subject and compatible_predicate and jaccard(old_pred.object, new_pred.object) < 0.85:
            return True, "changed_value"

    old_negated = bool(re.search(r"\b(not|never|no longer|stopped|discontinued)\b", old))
    new_negated = bool(re.search(r"\b(not|never|no longer|stopped|discontinued)\b", new))
    if old_negated != new_negated and jaccard(
        re.sub(r"\b(not|never|no longer|stopped|discontinued)\b", "", old),
        re.sub(r"\b(not|never|no longer|stopped|discontinued)\b", "", new),
    ) >= 0.8:
        return True, "negation_changed"
    return False, None


def relationship_type_for(source_type: str, target_type: str, context: str = "") -> str:
    lower = (context or "").lower()
    pair = (source_type, target_type)
    mapping = {
        ("person", "project"): "WORKS_ON",
        ("person", "organisation"): "MEMBER_OF",
        ("project", "technology"): "USES",
        ("project", "goal"): "SUPPORTS",
        ("goal", "project"): "SUPPORTED_BY",
        ("decision", "project"): "AFFECTS",
        ("decision", "technology"): "AFFECTS",
        ("decision", "concept"): "AFFECTS",
        ("experience", "event"): "RELATES_TO",
        ("preference", "concept"): "INFLUENCES",
        ("insight", "project"): "RELATES_TO",
        ("insight", "goal"): "RELATES_TO",
        ("person", "goal"): "PURSUES",
        ("project", "document"): "DOCUMENTED_BY",
    }
    if pair in mapping:
        return mapping[pair]
    if "work" in lower:
        return "RELATES_TO"
    return "RELATED_TO"


def merge_candidate_names(name: str, aliases: list[str] | None = None) -> list[str]:
    """Names that may identify the same entity, used only for candidate lookup."""
    values = [name, *(aliases or [])]
    seen: list[str] = []
    for value in values:
        normalized = normalize_entity_name(value)
        if normalized and normalized not in seen:
            seen.append(normalized)
    return seen
