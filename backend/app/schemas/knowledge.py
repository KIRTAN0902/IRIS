"""Pydantic contracts for the IRIS Knowledge API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class KnowledgeNodeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    node_type: str = "topic"
    description: str | None = None
    category: str | None = None
    aliases: list[str] = Field(default_factory=list)
    sensitivity: str | None = None
    access_level: str | None = None


class KnowledgeNodeUpdate(BaseModel):
    canonical_name: str | None = None
    description: str | None = None
    status: Literal["active", "archived"] | None = None
    sensitivity: str | None = None
    access_level: str | None = None
    aliases: list[str] | None = None


class KnowledgeNodeOut(BaseModel):
    id: str
    node_type: str
    canonical_name: str
    normalized_name: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: str
    sensitivity: str
    access_level: str
    claim_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None


class KnowledgeClaimCreate(BaseModel):
    node_id: str
    text: str = Field(min_length=1, max_length=2000)
    claim_type: str = "fact"
    category: str = "general"
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    verification_status: str = "unverified"
    sensitivity: str | None = None
    evidence_text: str | None = None


class KnowledgeClaimUpdate(BaseModel):
    claim_text: str | None = Field(default=None, max_length=2000)
    verification_status: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    sensitivity: str | None = None


class KnowledgeClaimOut(BaseModel):
    id: str
    node_id: str
    node_name: str | None = None
    node_type: str | None = None
    claim_text: str
    claim_type: str
    category: str
    confidence: float
    verification_status: str
    source_id: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    observed_at: datetime | None = None
    recorded_at: datetime | None = None
    supersedes_claim_id: str | None = None
    superseded_by_claim_id: str | None = None
    sensitivity: str
    access_level: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    archived_at: datetime | None = None


class KnowledgeSourceOut(BaseModel):
    id: str
    source_type: str
    source_ref: str
    title: str | None = None
    conversation_id: int | None = None
    message_id: int | None = None
    sensitivity: str
    access_level: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class KnowledgeRelationshipCreate(BaseModel):
    source_node_id: str
    target_node_id: str
    relationship_type: str = Field(min_length=1, max_length=50)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeRelationshipOut(BaseModel):
    id: str
    source_node_id: str
    target_node_id: str
    relationship_type: str
    confidence: float
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeNoteOut(BaseModel):
    id: str
    node_id: str | None = None
    title: str
    note_type: str
    storage_path: str
    content_hash: str
    db_version: int
    sync_status: str
    conflict_path: str | None = None
    sensitivity: str
    access_level: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_synced_at: datetime | None = None
    archived_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class KnowledgeNoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(default="", max_length=5_000_000)
    category: str = "general"
    tags: list[str] = Field(default_factory=list)
    node_id: str | None = None


class KnowledgeNoteUpdate(BaseModel):
    content: str = Field(..., max_length=5_000_000)
    expected_hash: str | None = None


class KnowledgeNoteRename(BaseModel):
    title: str | None = None
    category: str | None = None


class KnowledgeNoteDetail(BaseModel):
    note: KnowledgeNoteOut
    content: str
    content_hash: str
    missing: bool = False


class KnowledgeVersionOut(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    version_number: int
    change_type: str
    change_reason: str | None = None
    actor: str
    snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class KnowledgeOverviewOut(BaseModel):
    recent_nodes: list[KnowledgeNodeOut] = Field(default_factory=list)
    recent_claims: list[KnowledgeClaimOut] = Field(default_factory=list)
    important_projects: list[KnowledgeNodeOut] = Field(default_factory=list)
    recent_insights: list[KnowledgeClaimOut] = Field(default_factory=list)
    reviews: list[dict[str, Any]] = Field(default_factory=list)
    categories: list[dict[str, str]] = Field(default_factory=list)
    counts_by_type: dict[str, int] = Field(default_factory=dict)
    totals: dict[str, int] = Field(default_factory=dict)
    health: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchIn(BaseModel):
    query: str = ""
    limit: int = Field(default=12, ge=1, le=40)
    categories: list[str] = Field(default_factory=list)
    node_types: list[str] = Field(default_factory=list)
    include_history: bool = False
    as_of: datetime | str | None = None


class KnowledgeSearchOut(BaseModel):
    query: str
    as_of: str | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    candidate_count: int = 0
    truncated: bool = False


class KnowledgeCaptureIn(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    title: str | None = None
    source_type: str = "user_provided"
    source_ref: str | None = None
    origin: str = "user"
    process_now: bool = False


class KnowledgeCaptureOut(BaseModel):
    source_id: str
    job_id: str | None = None


class KnowledgeImportIn(BaseModel):
    path: str
    content: str | None = None


class KnowledgePermissionIn(BaseModel):
    principal_type: str = "coworker"
    principal_id: str = "*"
    access_level: str = "personal"
    knowledge_type: str = "global"
    knowledge_id: str | None = None
    can_read: bool = True
    can_write: bool = False


class KnowledgeMigrationIn(BaseModel):
    dry_run: bool = False
    limit: int = Field(default=500, ge=1, le=2000)


class KnowledgeGraphOut(BaseModel):
    nodes: list[KnowledgeNodeOut] = Field(default_factory=list)
    relationships: list[KnowledgeRelationshipOut] = Field(default_factory=list)
    truncated: bool = False


class KnowledgeJobDrainIn(BaseModel):
    limit: int = Field(default=5, ge=1, le=25)
