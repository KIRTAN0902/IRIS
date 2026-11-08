"""Embedding abstraction with an optional pgvector acceleration path.

IRIS must not assume pgvector exists. The portable representation is a JSON
vector; similarity is computed in Python over a bounded candidate set. When
the extension and ``knowledge_embeddings.embedding`` column are present the
same vectors are written there for future SQL-side search, without changing the
service contract.

The default provider is a deterministic hashed bag-of-words/char-ngram model.
It is free, offline and stable, and can be replaced by a remote embedding
provider by implementing ``EmbeddingProvider``.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Iterable, Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.knowledge.types import content_fingerprint
from app.models.knowledge import KnowledgeEmbedding

logger = get_logger("iris.knowledge.embeddings")

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_\-]+")


class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    def embed(self, text: str) -> list[float]: ...


@dataclass
class HashEmbeddingProvider:
    """Deterministic feature-hashing embedding (no network, no API cost)."""

    dimensions: int = 256
    name: str = "iris-hash-v1"

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = _TOKEN.findall((text or "").lower())
        if not tokens:
            return vector
        features: list[tuple[str, float]] = []
        for token in tokens:
            features.append((f"w:{token}", 1.0))
        for left, right in zip(tokens, tokens[1:]):
            features.append((f"b:{left}_{right}", 0.6))
        joined = " ".join(tokens)
        for index in range(max(0, len(joined) - 2)):
            features.append((f"c:{joined[index:index + 3]}", 0.15))
        for feature, weight in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign * weight
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector


def get_embedding_provider() -> EmbeddingProvider:
    # A remote provider can be selected here later; the rest of the system only
    # depends on the protocol.
    return HashEmbeddingProvider(
        dimensions=max(32, int(settings.knowledge_embedding_dimensions)),
        name=settings.knowledge_embedding_model or "iris-hash-v1",
    )


def cosine(left: Iterable[float], right: Iterable[float]) -> float:
    a = list(left)
    b = list(right)
    if not a or not b:
        return 0.0
    size = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(size))
    norm_a = math.sqrt(sum(a[i] * a[i] for i in range(size)))
    norm_b = math.sqrt(sum(b[i] * b[i] for i in range(size)))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


class EmbeddingService:
    def __init__(self) -> None:
        self._pgvector_ready: bool | None = None

    def pgvector_available(self, db: Session) -> bool:
        if self._pgvector_ready is not None:
            return self._pgvector_ready
        try:
            if db.get_bind().dialect.name != "postgresql":
                self._pgvector_ready = False
                return False
            extension = db.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ).first()
            column = db.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'knowledge_embeddings' AND column_name = 'embedding'"
                )
            ).first()
            self._pgvector_ready = bool(extension and column)
        except Exception:  # noqa: BLE001 - optional acceleration
            self._pgvector_ready = False
        return bool(self._pgvector_ready)

    def embed_text(self, text: str) -> list[float]:
        return get_embedding_provider().embed(text)

    def upsert(
        self,
        db: Session,
        *,
        user_id: int,
        knowledge_type: str,
        knowledge_id: str,
        text: str,
        content_version: int = 1,
    ) -> KnowledgeEmbedding | None:
        if not settings.knowledge_embeddings_enabled:
            return None
        provider = get_embedding_provider()
        content_hash = content_fingerprint(text)
        existing = (
            db.query(KnowledgeEmbedding)
            .filter(
                KnowledgeEmbedding.user_id == user_id,
                KnowledgeEmbedding.knowledge_type == knowledge_type,
                KnowledgeEmbedding.knowledge_id == knowledge_id,
                KnowledgeEmbedding.model == provider.name,
            )
            .first()
        )
        if existing and existing.content_hash == content_hash:
            return existing
        vector = provider.embed(text)
        payload = json.dumps([round(value, 6) for value in vector], separators=(",", ":"))
        if existing is None:
            existing = KnowledgeEmbedding(
                user_id=user_id,
                knowledge_type=knowledge_type,
                knowledge_id=knowledge_id,
                model=provider.name,
                dimensions=provider.dimensions,
                vector_json=payload,
                content_hash=content_hash,
                content_version=content_version,
            )
            db.add(existing)
        else:
            existing.dimensions = provider.dimensions
            existing.vector_json = payload
            existing.content_hash = content_hash
            existing.content_version = content_version
        db.flush()
        self._write_pgvector(db, existing.id, vector)
        return existing

    def _write_pgvector(self, db: Session, embedding_id: str, vector: list[float]) -> None:
        if not settings.knowledge_pgvector_enabled or not self.pgvector_available(db):
            return
        try:
            db.execute(
                text(
                    "UPDATE knowledge_embeddings SET embedding = CAST(:vec AS vector) WHERE id = :id"
                ),
                {"vec": "[" + ",".join(f"{v:.6f}" for v in vector) + "]", "id": embedding_id},
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("pgvector_write_skipped error_type=%s", type(exc).__name__)

    def semantic_scores(
        self,
        db: Session,
        *,
        user_id: int,
        query: str,
        knowledge_type: str,
        knowledge_ids: list[str] | None = None,
        candidate_limit: int = 1500,
    ) -> dict[str, float]:
        if not settings.knowledge_embeddings_enabled:
            return {}
        provider = get_embedding_provider()
        query_vector = provider.embed(query)
        if not any(query_vector):
            return {}
        q = db.query(KnowledgeEmbedding).filter(
            KnowledgeEmbedding.user_id == user_id,
            KnowledgeEmbedding.knowledge_type == knowledge_type,
            KnowledgeEmbedding.model == provider.name,
        )
        if knowledge_ids:
            q = q.filter(KnowledgeEmbedding.knowledge_id.in_(knowledge_ids[:candidate_limit]))
        rows = q.limit(candidate_limit).all()
        scores: dict[str, float] = {}
        for row in rows:
            try:
                vector = json.loads(row.vector_json)
            except (TypeError, ValueError):
                continue
            scores[row.knowledge_id] = cosine(query_vector, vector)
        return scores


embedding_service = EmbeddingService()
