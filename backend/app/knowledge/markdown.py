"""Markdown note rendering and parsing (YAML frontmatter + standard Markdown)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.knowledge.types import (
    CATEGORY_FOLDERS,
    NODE_TYPE_CATEGORY,
    hash_bytes,
    slugify,
    utcnow,
)

FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
MDLINK = re.compile(r"\[[^\]]+\]\(([^)]+\.md)\)")
YAML_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_\-]*):\s*(.*)$")


@dataclass
class ParsedNote:
    frontmatter: dict[str, Any]
    body: str
    links: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def _parse_scalar(value: str) -> Any:
    raw = value.strip()
    if raw in {"", "~", "null"}:
        return None
    if raw.lower() in {"true", "false"}:
        return raw.lower() == "true"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    if raw.startswith("[") and raw.endswith("]"):
        try:
            return json.loads(raw.replace("'", '"'))
        except ValueError:
            return [part.strip().strip("'\"") for part in raw[1:-1].split(",") if part.strip()]
    return raw.strip("'\"")


def parse_frontmatter(content: str) -> ParsedNote:
    text = content or ""
    match = FRONTMATTER.match(text)
    body = text
    frontmatter: dict[str, Any] = {}
    if match:
        body = text[match.end():]
        current_key: str | None = None
        for line in match.group(1).splitlines():
            if not line.strip():
                continue
            if line.startswith(("  - ", "- ")) and current_key:
                item = line.split("-", 1)[1].strip().strip("'\"")
                existing = frontmatter.get(current_key)
                if not isinstance(existing, list):
                    existing = [] if existing in {None, ""} else [existing]
                    frontmatter[current_key] = existing
                existing.append(item)
                continue
            parsed = YAML_LINE.match(line)
            if parsed:
                current_key = parsed.group(1)
                value = _parse_scalar(parsed.group(2))
                if value in {None, ""}:
                    frontmatter[current_key] = []
                else:
                    frontmatter[current_key] = value
            else:
                current_key = None
    links = sorted({link.strip() for link in WIKILINK.findall(body)})
    for target in MDLINK.findall(body):
        if not target.startswith(("http://", "https://")):
            links.append(target.split("#", 1)[0])
    tags = frontmatter.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return ParsedNote(frontmatter=frontmatter, body=body, links=sorted(set(links)), tags=list(tags))


def _yaml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(str(item)) for item in value) + "]"
    return json.dumps(str(value)) if value is not None else "null"


def render_frontmatter(metadata: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in metadata.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {_yaml_value(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


@dataclass
class RenderedNote:
    path: str
    title: str
    content: str
    content_hash: str
    note_type: str
    category: str
    metadata: dict[str, Any]


def note_folder(category: str | None, node_type: str | None = None) -> str:
    key = (category or NODE_TYPE_CATEGORY.get(node_type or "", "general")).lower()
    return CATEGORY_FOLDERS.get(key, "00-Index")


def note_path(title: str, *, category: str | None, node_type: str | None = None, suffix: str | None = None) -> str:
    folder = note_folder(category, node_type)
    stem = slugify(title)
    if suffix:
        stem = f"{stem}-{suffix[:8]}"
    return f"{folder}/{stem}.md"


def _claim_line(claim: Any) -> str:
    marker = {
        "decision": "Decision",
        "inference": "Inference",
        "experience": "Experience",
        "observation": "Observation",
        "understanding": "Understanding",
        "fact": "Fact",
    }.get(getattr(claim, "claim_type", "fact"), "Fact")
    status = getattr(claim, "verification_status", "unverified").replace("_", " ")
    confidence = getattr(claim, "confidence", None)
    confidence_text = f" · confidence {confidence:.2f}" if isinstance(confidence, (int, float)) else ""
    date = getattr(claim, "observed_at", None) or getattr(claim, "recorded_at", None)
    date_text = f" · {date.date().isoformat()}" if date else ""
    return f"- **{marker}** ({status}{confidence_text}{date_text}): {claim.claim_text}"


def render_node_note(
    *,
    node: Any,
    claims: Iterable[Any],
    relationships: Iterable[Any],
    node_names: dict[str, str],
    sources: dict[str, Any] | None = None,
    related_notes: Iterable[str] = (),
    include_history: bool = False,
) -> RenderedNote:
    category = NODE_TYPE_CATEGORY.get(node.node_type, "general")
    path = note_path(node.canonical_name, category=category, node_type=node.node_type)
    now = utcnow()
    metadata: dict[str, Any] = {
        "id": node.id,
        "title": node.canonical_name,
        "type": node.node_type,
        "status": node.status,
        "category": category,
        "sensitivity": node.sensitivity,
        "tags": sorted(set([node.node_type, category] + list(node.aliases or [])[:5])),
        "created_at": (node.created_at.date().isoformat() if node.created_at else now.date().isoformat()),
        "updated_at": now.date().isoformat(),
        "sources": sorted({claim.source_id for claim in claims if getattr(claim, "source_id", None)}),
        "related": list(related_notes),
    }
    lines = [
        f"# {node.canonical_name}",
        "",
    ]
    if node.description:
        lines += [node.description.strip(), ""]
    active_claims = [c for c in claims if include_history or not getattr(c, "valid_until", None)]
    if active_claims:
        lines += ["## Knowledge", ""]
        lines += [_claim_line(claim) for claim in active_claims]
        lines.append("")
    relation_lines = []
    for relationship in relationships:
        other_id = (
            relationship.target_node_id
            if relationship.source_node_id == node.id
            else relationship.source_node_id
        )
        other_name = node_names.get(other_id)
        if not other_name:
            continue
        arrow = "→" if relationship.source_node_id == node.id else "←"
        relation_lines.append(
            f"- {arrow} **{relationship.relationship_type.replace('_', ' ').title()}** [[{other_name}]]"
        )
    if relation_lines:
        lines += ["## Connections", ""] + relation_lines + [""]
    if sources:
        lines += ["## Sources", ""]
        for source_id, source in sources.items():
            label = getattr(source, "title", None) or getattr(source, "source_ref", source_id)
            kind = getattr(source, "source_type", "source")
            lines.append(f"- {label} (`{kind}` · `{source_id}`)")
        lines.append("")
    if include_history:
        superseded = [c for c in claims if getattr(c, "valid_until", None)]
        if superseded:
            lines += ["## History", ""]
            for claim in superseded:
                until = claim.valid_until.date().isoformat() if claim.valid_until else "unknown"
                lines.append(f"- ~~{claim.claim_text}~~ (until {until}; {claim.verification_status})")
            lines.append("")
    lines += [
        "## Notes",
        "",
        "_This section is yours. IRIS preserves it when regenerating structured sections._",
        "",
    ]
    content = render_frontmatter(metadata) + "\n" + "\n".join(lines).rstrip() + "\n"
    return RenderedNote(
        path=path,
        title=node.canonical_name,
        content=content,
        content_hash=hash_bytes(content.encode("utf-8")),
        note_type=node.node_type,
        category=category,
        metadata=metadata,
    )


def render_index_note(
    *,
    title: str,
    path: str,
    sections: dict[str, list[str]],
    description: str = "",
) -> RenderedNote:
    now = utcnow()
    metadata = {
        "id": slugify(path),
        "title": title,
        "type": "index",
        "status": "active",
        "created_at": now.date().isoformat(),
        "updated_at": now.date().isoformat(),
    }
    lines = [f"# {title}", ""]
    if description:
        lines += [description, ""]
    for heading, links in sections.items():
        if not links:
            continue
        lines += [f"## {heading}", ""]
        lines += [f"- [[{link}]]" for link in sorted(links)]
        lines.append("")
    content = render_frontmatter(metadata) + "\n" + "\n".join(lines).rstrip() + "\n"
    return RenderedNote(
        path=path,
        title=title,
        content=content,
        content_hash=hash_bytes(content.encode("utf-8")),
        note_type="index",
        category="general",
        metadata=metadata,
    )


def merge_user_section(existing: str, generated: str) -> str:
    """Preserve the user's ``## Notes`` section during regeneration."""
    marker = "## Notes"
    if marker not in existing:
        return generated
    existing_notes = existing.split(marker, 1)[1]
    if marker in generated:
        head = generated.split(marker, 1)[0]
        return head + marker + existing_notes
    return generated.rstrip() + "\n\n" + marker + existing_notes
