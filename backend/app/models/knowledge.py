"""IRIS Knowledge persistence model.

The knowledge subsystem is additive: it does not replace ``ai_memories`` and
does not depend on any external graph or vector database. PostgreSQL is the
authoritative structured store; Markdown in Supabase Storage is the
human-readable projection.

All identifiers are UUID strings so records remain stable across exports,
imports and future storage migrations. Foreign keys are explicit, every
user-owned row carries ``user_id``, and historical rows are retained rather
than overwritten.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid4())


class KnowledgeNode(Base):
    """A durable entity: person, project, goal, technology, concept, decision…"""

    __tablename__ = "knowledge_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    node_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True, nullable=False)
    sensitivity: Mapped[str] = mapped_column(
        String(20), default="ordinary", index=True, nullable=False
    )
    access_level: Mapped[str] = mapped_column(
        String(20), default="shared", index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now(), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    claims: Mapped[list["KnowledgeClaim"]] = relationship(
        "KnowledgeClaim", back_populates="node", cascade="all, delete-orphan"
    )
    outgoing: Mapped[list["KnowledgeRelationship"]] = relationship(
        "KnowledgeRelationship",
        foreign_keys="KnowledgeRelationship.source_node_id",
        back_populates="source_node",
        cascade="all, delete-orphan",
    )
    incoming: Mapped[list["KnowledgeRelationship"]] = relationship(
        "KnowledgeRelationship",
        foreign_keys="KnowledgeRelationship.target_node_id",
        back_populates="target_node",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "node_type", "normalized_name", name="uq_knowledge_node_identity"),
        Index("ix_knowledge_nodes_user_type", "user_id", "node_type"),
        Index("ix_knowledge_nodes_user_status", "user_id", "status"),
    )


class KnowledgeSource(Base):
    """Provenance record. Stores stable references, not duplicated source bodies."""

    __tablename__ = "knowledge_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    source_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    conversation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ai_conversations.id", ondelete="SET NULL"), nullable=True
    )
    message_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ai_messages.id", ondelete="SET NULL"), nullable=True
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    sensitivity: Mapped[str] = mapped_column(String(20), default="ordinary", nullable=False)
    access_level: Mapped[str] = mapped_column(String(20), default="shared", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "source_type", "source_ref", "content_hash", name="uq_knowledge_source_identity"
        ),
        Index("ix_knowledge_sources_user_type", "user_id", "source_type"),
    )


class KnowledgeClaim(Base):
    """One assertion about a node. Type, verification and confidence are separate."""

    __tablename__ = "knowledge_claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(30), default="unverified", index=True, nullable=False
    )
    source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_sources.id", ondelete="SET NULL"), index=True, nullable=True
    )
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), nullable=False
    )
    supersedes_claim_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_claims.id", ondelete="SET NULL"), nullable=True
    )
    superseded_by_claim_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_claims.id", ondelete="SET NULL"), nullable=True
    )
    sensitivity: Mapped[str] = mapped_column(
        String(20), default="ordinary", index=True, nullable=False
    )
    access_level: Mapped[str] = mapped_column(
        String(20), default="shared", index=True, nullable=False
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now(), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    node: Mapped[KnowledgeNode] = relationship("KnowledgeNode", back_populates="claims")
    evidence: Mapped[list["KnowledgeEvidence"]] = relationship(
        "KnowledgeEvidence", back_populates="claim", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_knowledge_claims_user_node", "user_id", "node_id"),
        Index("ix_knowledge_claims_user_current", "user_id", "valid_until", "archived_at"),
        Index("ix_knowledge_claims_user_fingerprint", "user_id", "fingerprint"),
    )


class KnowledgeEvidence(Base):
    """Links a claim to supporting evidence and the extraction method used."""

    __tablename__ = "knowledge_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    claim_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_claims.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_sources.id", ondelete="SET NULL"), nullable=True
    )
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(50), default="heuristic", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), nullable=False
    )

    claim: Mapped[KnowledgeClaim] = relationship("KnowledgeClaim", back_populates="evidence")


class KnowledgeRelationship(Base):
    """A directed, temporal edge between two knowledge nodes."""

    __tablename__ = "knowledge_relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_sources.id", ondelete="SET NULL"), nullable=True
    )
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now(), nullable=False
    )

    source_node: Mapped[KnowledgeNode] = relationship(
        "KnowledgeNode", foreign_keys=[source_node_id], back_populates="outgoing"
    )
    target_node: Mapped[KnowledgeNode] = relationship(
        "KnowledgeNode", foreign_keys=[target_node_id], back_populates="incoming"
    )

    __table_args__ = (
        Index("ix_knowledge_relationships_user_source", "user_id", "source_node_id"),
        Index("ix_knowledge_relationships_user_target", "user_id", "target_node_id"),
        UniqueConstraint(
            "user_id",
            "source_node_id",
            "target_node_id",
            "relationship_type",
            "valid_from",
            name="uq_knowledge_relationship_edge",
        ),
    )


class KnowledgeVersion(Base):
    """Append-only change history for nodes, claims and notes."""

    __tablename__ = "knowledge_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    change_type: Mapped[str] = mapped_column(String(30), default="update", nullable=False)
    change_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    actor: Mapped[str] = mapped_column(String(80), default="iris", nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_knowledge_versions_entity", "user_id", "entity_type", "entity_id"),
    )


class KnowledgePermission(Base):
    """Per-item access grant. Enforced before any content reaches a model."""

    __tablename__ = "knowledge_permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    knowledge_type: Mapped[str] = mapped_column(String(30), default="global", nullable=False)
    knowledge_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    principal_type: Mapped[str] = mapped_column(String(30), default="coworker", nullable=False)
    principal_id: Mapped[str] = mapped_column(String(120), default="*", nullable=False)
    access_level: Mapped[str] = mapped_column(String(20), default="personal", nullable=False)
    can_read: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_write: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_knowledge_permissions_principal", "user_id", "principal_type", "principal_id"),
        Index("ix_knowledge_permissions_item", "user_id", "knowledge_type", "knowledge_id"),
    )


class KnowledgeEmbedding(Base):
    """Semantic representation of a claim, node or note.

    ``vector_json`` is the portable representation. pgvector, when available,
    is populated by the embedding service through the optional ``vector``
    column created by the PostgreSQL migration.
    """

    __tablename__ = "knowledge_embeddings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    knowledge_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    knowledge_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_json: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    content_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "knowledge_type", "knowledge_id", "model", name="uq_knowledge_embedding_item"
        ),
        Index("ix_knowledge_embeddings_lookup", "user_id", "knowledge_type", "model"),
    )


class KnowledgeJob(Base):
    """Durable background job with leases, retries and a dead-letter state."""

    __tablename__ = "knowledge_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), index=True, nullable=False
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_knowledge_job_idempotency"),
        Index("ix_knowledge_jobs_claim", "status", "available_at", "priority"),
    )


class KnowledgeReview(Base):
    """Optional audit record for corrections, conflicts and disputed items."""

    __tablename__ = "knowledge_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    review_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class KnowledgeNote(Base):
    """Synchronisation state for one Markdown note in the vault."""

    __tablename__ = "knowledge_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    node_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_nodes.id", ondelete="SET NULL"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    note_type: Mapped[str] = mapped_column(String(40), default="note", index=True, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    db_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    storage_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_source_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sync_status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True, nullable=False
    )  # pending | synced | conflict | failed | archived
    conflict_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sensitivity: Mapped[str] = mapped_column(String(20), default="ordinary", nullable=False)
    access_level: Mapped[str] = mapped_column(String(20), default="shared", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "storage_path", name="uq_knowledge_note_path"),
        Index("ix_knowledge_notes_user_status", "user_id", "sync_status"),
    )
