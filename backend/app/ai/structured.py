"""Model-agnostic helpers for getting structured output out of any LLM.

Models differ wildly in how they wrap JSON: some emit reasoning first
(``<think>...</think>``), some fence it in markdown, some add a sentence of
preamble. These helpers normalise all of that and compact JSON Schemas so they
are accepted by strict tool-calling endpoints and cheap to put in prompts.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.ai.provider import AISchemaValidationError

T = TypeVar("T", bound=BaseModel)

_THINK_RE = re.compile(r"<(think|thinking|reasoning)>([\s\S]*?)</\1>", re.IGNORECASE)
_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.DOTALL)


def split_reasoning(text: str) -> tuple[str, str | None]:
    """Separate inline reasoning blocks from the answer.

    Returns ``(answer, reasoning)``. Handles an unterminated leading block
    (model hit the token limit mid-thought, or the template opened the tag).
    """
    if not text:
        return "", None
    reasoning_parts = [m.group(2) for m in _THINK_RE.finditer(text)]
    answer = _THINK_RE.sub("", text)
    # Some templates emit only the closing tag ("...thoughts</think>answer").
    if "</think>" in answer.lower():
        head, _, tail = re.split(r"(</think>)", answer, maxsplit=1, flags=re.IGNORECASE)
        reasoning_parts.append(head)
        answer = tail
    reasoning = "\n".join(p.strip() for p in reasoning_parts if p.strip()) or None
    return answer.strip(), reasoning


def _clean_json_markdown(text: str) -> str:
    """Strip markdown code fences (e.g. ```json ... ```) and leading/trailing whitespace."""
    text = text.strip()
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text


def _first_json_value(text: str) -> str | None:
    """Return the first balanced top-level JSON object/array in ``text``."""
    start = None
    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if start is None:
            if ch in "{[":
                start = i
                depth = 1
            continue
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json(text: str) -> Any:
    """Extract a JSON value from arbitrary model output.

    Raises ``json.JSONDecodeError`` if nothing parseable is found.
    """
    answer, _ = split_reasoning(text)
    candidate = _clean_json_markdown(answer)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        embedded = _first_json_value(candidate)
        if embedded is None:
            raise
        return json.loads(embedded)


def parse_structured(text: str, schema: type[T], *, provider: str | None = None) -> T:
    """Parse model output into ``schema`` or raise ``AISchemaValidationError``."""
    if not text or not text.strip():
        raise AISchemaValidationError("Model returned empty content", provider=provider)
    try:
        data = extract_json(text)
    except json.JSONDecodeError as exc:
        raise AISchemaValidationError(
            f"Model output was not valid JSON: {exc}", provider=provider, cause=exc
        ) from exc
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise AISchemaValidationError(
            f"Model output failed schema validation for {schema.__name__}: {exc}",
            provider=provider,
            cause=exc,
        ) from exc


# --- JSON Schema compaction ----------------------------------------------------


def compact_schema(schema: dict[str, Any] | type[BaseModel]) -> dict[str, Any]:
    """Return a self-contained, portable JSON Schema.

    - Inlines ``$ref``/``$defs`` (many tool-calling endpoints reject refs)
    - Collapses ``Optional[X]`` (``anyOf: [X, null]``) to ``X``
    - Drops noisy ``title`` keys to save prompt tokens
    """
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        schema = schema.model_json_schema()
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {}) or schema.pop("definitions", {})

    def resolve(node: Any, seen: frozenset[str] = frozenset()) -> Any:
        if isinstance(node, list):
            return [resolve(n, seen) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            if name in seen or name not in defs:
                return {"type": "object"}
            merged = {**defs[name], **{k: v for k, v in node.items() if k != "$ref"}}
            return resolve(merged, seen | {name})
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key == "title" and isinstance(value, str):
                continue
            out[key] = resolve(value, seen)
        any_of = out.get("anyOf")
        if isinstance(any_of, list):
            non_null = [v for v in any_of if v != {"type": "null"}]
            if len(non_null) == 1 and len(non_null) < len(any_of):
                out.pop("anyOf")
                base = non_null[0]
                out = {**base, **out}
                if out.get("default", ...) is None:
                    out.pop("default")
        return out

    return resolve(schema)


def schema_instruction(schema: type[BaseModel]) -> str:
    """Prompt suffix asking for JSON matching ``schema``."""
    return (
        "\n\nRespond ONLY with a single valid JSON object (no prose, no markdown) "
        "that conforms to this JSON Schema:\n"
        f"{json.dumps(compact_schema(schema), separators=(',', ':'))}"
    )


def repair_instruction(error: Exception) -> str:
    """Follow-up message asking the model to fix invalid structured output."""
    detail = str(error)
    if len(detail) > 1200:
        detail = detail[:1200] + "..."
    return (
        "Your previous reply could not be used: "
        f"{detail}\n\nReturn ONLY the corrected JSON object, with no other text."
    )
