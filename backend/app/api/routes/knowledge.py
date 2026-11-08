"""IRIS Knowledge API.

Every read and write goes through ``KnowledgeService``, the retrieval service or
the Markdown synchronisation service. Routes never query knowledge tables for
model-facing content directly, so permissions, sensitivity and provenance are
enforced at one boundary.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.knowledge.consolidation import consolidate_user_knowledge
from app.knowledge.jobs import drain_jobs, job_stats
from app.knowledge.markdown_sync import (
    MarkdownConflictError,
    MarkdownSyncError,
    markdown_sync,
)
from app.knowledge.migration import migrate_memories_to_knowledge
from app.knowledge.observability import knowledge_health
from app.knowledge.permissions import build_permission_context
from app.knowledge.pipeline import capture_text
from app.knowledge.retrieval import knowledge_retrieval
from app.knowledge.service import KnowledgeError, knowledge_service
from app.knowledge.types import ClaimType, VerificationStatus
from app.models.knowledge import (
    KnowledgeClaim,
    KnowledgeJob,
    KnowledgeNode,
    KnowledgePermission,
    KnowledgeRelationship,
    KnowledgeReview,
    KnowledgeSource,
    KnowledgeVersion,
)
from app.models.user import User
from app.schemas.knowledge import (
    KnowledgeCaptureIn,
    KnowledgeCaptureOut,
    KnowledgeClaimCreate,
    KnowledgeClaimOut,
    KnowledgeClaimUpdate,
    KnowledgeGraphOut,
    KnowledgeImportIn,
    KnowledgeJobDrainIn,
    KnowledgeMigrationIn,
    KnowledgeNodeCreate,
    KnowledgeNodeOut,
    KnowledgeNodeUpdate,
    KnowledgeNoteCreate,
    KnowledgeNoteDetail,
    KnowledgeNoteOut,
    KnowledgeNoteRename,
    KnowledgeNoteUpdate,
    KnowledgeOverviewOut,
    KnowledgePermissionIn,
    KnowledgeRelationshipCreate,
    KnowledgeRelationshipOut,
    KnowledgeSearchIn,
    KnowledgeSearchOut,
    KnowledgeSourceOut,
    KnowledgeVersionOut,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# --- serialisers -------------------------------------------------------------


def _node_out(node: KnowledgeNode, claim_count: int | None = None) -> KnowledgeNodeOut:
    return KnowledgeNodeOut(
        id=node.id,
        node_type=node.node_type,
        canonical_name=node.canonical_name,
        normalized_name=node.normalized_name,
        description=node.description,
        aliases=list(node.aliases or []),
        metadata=dict(node.metadata_json or {}),
        status=node.status,
        sensitivity=node.sensitivity,
        access_level=node.access_level,
        claim_count=claim_count or 0,
        created_at=node.created_at,
        updated_at=node.updated_at,
        archived_at=node.archived_at,
    )


def _claim_out(claim: KnowledgeClaim) -> KnowledgeClaimOut:
    node = claim.node
    return KnowledgeClaimOut(
        id=claim.id,
        node_id=claim.node_id,
        node_name=node.canonical_name if node else None,
        node_type=node.node_type if node else None,
        claim_text=claim.claim_text,
        claim_type=claim.claim_type,
        category=claim.category,
        confidence=claim.confidence,
        verification_status=claim.verification_status,
        source_id=claim.source_id,
        valid_from=claim.valid_from,
        valid_until=claim.valid_until,
        observed_at=claim.observed_at,
        recorded_at=claim.recorded_at,
        supersedes_claim_id=claim.supersedes_claim_id,
        superseded_by_claim_id=claim.superseded_by_claim_id,
        sensitivity=claim.sensitivity,
        access_level=claim.access_level,
        metadata=dict(claim.metadata_json or {}),
        archived_at=claim.archived_at,
    )


def _source_out(source: KnowledgeSource) -> KnowledgeSourceOut:
    return KnowledgeSourceOut(
        id=source.id,
        source_type=source.source_type,
        source_ref=source.source_ref,
        title=source.title,
        conversation_id=source.conversation_id,
        message_id=source.message_id,
        sensitivity=source.sensitivity,
        access_level=source.access_level,
        metadata=dict(source.metadata_json or {}),
        created_at=source.created_at,
    )


def _relationship_out(edge: KnowledgeRelationship) -> KnowledgeRelationshipOut:
    return KnowledgeRelationshipOut(
        id=edge.id,
        source_node_id=edge.source_node_id,
        target_node_id=edge.target_node_id,
        relationship_type=edge.relationship_type,
        confidence=edge.confidence,
        valid_from=edge.valid_from,
        valid_until=edge.valid_until,
        metadata=dict(edge.metadata_json or {}),
    )


def _note_out(note: Any) -> KnowledgeNoteOut:
    return KnowledgeNoteOut(
        id=note.id,
        node_id=note.node_id,
        title=note.title,
        note_type=note.note_type,
        storage_path=note.storage_path,
        content_hash=note.content_hash,
        db_version=note.db_version,
        sync_status=note.sync_status,
        conflict_path=note.conflict_path,
        sensitivity=note.sensitivity,
        access_level=note.access_level,
        metadata=dict(note.metadata_json or {}),
        last_synced_at=note.last_synced_at,
        archived_at=note.archived_at,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _version_out(version: KnowledgeVersion) -> KnowledgeVersionOut:
    return KnowledgeVersionOut(
        id=version.id,
        entity_type=version.entity_type,
        entity_id=version.entity_id,
        version_number=version.version_number,
        change_type=version.change_type,
        change_reason=version.change_reason,
        actor=version.actor,
        snapshot=dict(version.snapshot or {}),
        created_at=version.created_at,
    )


def _not_found(message: str = "Knowledge item not found.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


# --- health / overview -------------------------------------------------------


@router.get("/health")
def get_health(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return knowledge_health(db)


@router.get("/overview", response_model=KnowledgeOverviewOut)
def get_overview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = knowledge_service.overview(db, user.id, principal="user")
    counts = (
        db.query(KnowledgeClaim.node_id, func.count(KnowledgeClaim.id))
        .filter(KnowledgeClaim.user_id == user.id, KnowledgeClaim.archived_at.is_(None))
        .group_by(KnowledgeClaim.node_id)
        .all()
    )
    claim_counts = {node_id: count for node_id, count in counts}
    return KnowledgeOverviewOut(
        recent_nodes=[_node_out(n, claim_counts.get(n.id, 0)) for n in data["recent_nodes"]],
        recent_claims=[_claim_out(c) for c in data["recent_claims"]],
        important_projects=[
            _node_out(n, claim_counts.get(n.id, 0)) for n in data["important_projects"]
        ],
        recent_insights=[_claim_out(c) for c in data["recent_insights"]],
        reviews=[
            {
                "id": review.id,
                "review_type": review.review_type,
                "target_type": review.target_type,
                "target_id": review.target_id,
                "status": review.status,
                "reason": review.reason,
                "details": review.details or {},
                "created_at": review.created_at,
            }
            for review in data["reviews"]
        ],
        categories=data["categories"],
        counts_by_type=data["counts_by_type"],
        totals=data["totals"],
        health=knowledge_health(db),
    )


# --- nodes -------------------------------------------------------------------


@router.get("/nodes", response_model=list[KnowledgeNodeOut])
def list_nodes(
    node_type: str | None = None,
    query: str | None = None,
    include_archived: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    nodes = knowledge_service.list_nodes(
        db,
        user.id,
        node_type=node_type,
        query=query,
        principal="user",
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    counts = dict(
        db.query(KnowledgeClaim.node_id, func.count(KnowledgeClaim.id))
        .filter(
            KnowledgeClaim.user_id == user.id,
            KnowledgeClaim.node_id.in_([node.id for node in nodes]) if nodes else False,
        )
        .group_by(KnowledgeClaim.node_id)
        .all()
    )
    return [_node_out(node, counts.get(node.id, 0)) for node in nodes]


@router.post("/nodes", response_model=KnowledgeNodeOut, status_code=status.HTTP_201_CREATED)
def create_node(
    data: KnowledgeNodeCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    node, _ = knowledge_service.resolve_node(
        db,
        user_id=user.id,
        name=data.name,
        node_type=data.node_type,
        description=data.description,
        sensitivity=data.sensitivity,
        access_level=data.access_level,
        aliases=data.aliases,
    )
    db.commit()
    db.refresh(node)
    return _node_out(node)


@router.get("/nodes/{node_id}", response_model=KnowledgeNodeOut)
def get_node(
    node_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    node = knowledge_service.get_node(db, user.id, node_id, principal="user")
    if node is None:
        raise _not_found("Knowledge node not found.")
    count = (
        db.query(func.count(KnowledgeClaim.id))
        .filter(KnowledgeClaim.user_id == user.id, KnowledgeClaim.node_id == node.id)
        .scalar()
        or 0
    )
    return _node_out(node, count)


@router.patch("/nodes/{node_id}", response_model=KnowledgeNodeOut)
def update_node(
    node_id: str,
    data: KnowledgeNodeUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        node = knowledge_service.update_node(
            db, user.id, node_id, updates=data.model_dump(exclude_none=True), actor="user"
        )
    except KnowledgeError as exc:
        raise _not_found(str(exc)) from exc
    db.commit()
    return _node_out(node)


@router.post("/nodes/{node_id}/archive", response_model=KnowledgeNodeOut)
def archive_node(
    node_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    try:
        node = knowledge_service.archive_node(db, user.id, node_id)
    except KnowledgeError as exc:
        raise _not_found(str(exc)) from exc
    db.commit()
    return _node_out(node)


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(
    node_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if not knowledge_service.delete_node(db, user.id, node_id):
        raise _not_found("Knowledge node not found.")
    db.commit()
    return None


@router.get("/nodes/{node_id}/graph", response_model=KnowledgeGraphOut)
def get_node_graph(
    node_id: str,
    depth: int = Query(1, ge=0, le=3),
    limit: int = Query(40, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    data = knowledge_service.traverse(
        db, user.id, node_id, depth=depth, limit=limit, principal="user"
    )
    return KnowledgeGraphOut(
        nodes=[_node_out(node) for node in data["nodes"]],
        relationships=[_relationship_out(edge) for edge in data["relationships"]],
        truncated=data["truncated"],
    )


@router.get("/graph", response_model=KnowledgeGraphOut)
def get_knowledge_graph(
    node_id: str | None = Query(None),
    query: str | None = Query(None),
    depth: int = Query(1, ge=0, le=3),
    limit: int = Query(40, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if node_id:
        data = knowledge_service.traverse(
            db, user.id, node_id, depth=depth, limit=limit, principal="user"
        )
        return KnowledgeGraphOut(
            nodes=[_node_out(node) for node in data["nodes"]],
            relationships=[_relationship_out(edge) for edge in data["relationships"]],
            truncated=data["truncated"],
        )

    # Progressive expansion / global view
    if query:
        nodes = knowledge_service.list_nodes(db, user.id, query=query, limit=limit, principal="user")
    else:
        nodes = knowledge_service.list_nodes(db, user.id, limit=min(limit, 25), principal="user")
    if not nodes:
        return KnowledgeGraphOut(nodes=[], relationships=[], truncated=False)

    seed_ids = [n.id for n in nodes]
    relationships = (
        db.query(KnowledgeRelationship)
        .filter(
            KnowledgeRelationship.user_id == user.id,
            KnowledgeRelationship.valid_until.is_(None),
            or_(
                KnowledgeRelationship.source_node_id.in_(seed_ids),
                KnowledgeRelationship.target_node_id.in_(seed_ids),
            ),
        )
        .limit(limit * 2)
        .all()
    )

    all_node_ids = set(seed_ids)
    for r in relationships:
        all_node_ids.add(r.source_node_id)
        all_node_ids.add(r.target_node_id)

    all_nodes = {n.id: n for n in nodes}
    missing_ids = all_node_ids - set(all_nodes.keys())
    if missing_ids:
        extra_nodes = (
            db.query(KnowledgeNode)
            .filter(
                KnowledgeNode.id.in_(missing_ids),
                KnowledgeNode.user_id == user.id,
                KnowledgeNode.status == "active",
            )
            .all()
        )
        for extra in extra_nodes:
            all_nodes[extra.id] = extra

    return KnowledgeGraphOut(
        nodes=[_node_out(n) for n in list(all_nodes.values())[:limit]],
        relationships=[_relationship_out(r) for r in relationships],
        truncated=len(all_nodes) >= limit,
    )


@router.get("/relationships", response_model=list[KnowledgeRelationshipOut])
def list_relationships(
    source_node_id: str | None = Query(None),
    target_node_id: str | None = Query(None),
    relationship_type: str | None = Query(None),
    include_history: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    items = knowledge_service.list_relationships(
        db,
        user.id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        relationship_type=relationship_type,
        include_history=include_history,
        limit=limit,
        offset=offset,
    )
    return [_relationship_out(r) for r in items]


@router.post("/relationships", response_model=KnowledgeRelationshipOut, status_code=status.HTTP_201_CREATED)
def create_relationship(
    payload: KnowledgeRelationshipCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rel, _ = knowledge_service.upsert_relationship(
        db,
        user_id=user.id,
        source_node_id=payload.source_node_id,
        target_node_id=payload.target_node_id,
        relationship_type=payload.relationship_type,
        confidence=payload.confidence,
        metadata=payload.metadata,
    )
    db.commit()
    db.refresh(rel)
    return _relationship_out(rel)


@router.delete("/relationships/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_relationship(
    relationship_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not knowledge_service.delete_relationship(db, user.id, relationship_id):
        raise _not_found("Relationship not found.")
    db.commit()
    return None


@router.get("/nodes/{node_id}/note", response_model=KnowledgeNoteDetail)
def get_node_note(
    node_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    note = markdown_sync._note_for_node(db, user.id, node_id)
    if note is None:
        try:
            markdown_sync.sync_node(db, user_id=user.id, node_id=node_id)
            db.commit()
        except MarkdownSyncError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        note = markdown_sync._note_for_node(db, user.id, node_id)
    if note is None:
        raise _not_found("Markdown note not found for this node.")
    detail = markdown_sync.read_note(db, user_id=user.id, note_id=note.id)
    if detail is None:
        raise _not_found("Markdown note not found.")
    return KnowledgeNoteDetail(
        note=_note_out(detail["note"]),
        content=detail["content"],
        content_hash=detail["content_hash"],
        missing=detail["missing"],
    )


# --- claims ------------------------------------------------------------------


@router.get("/claims", response_model=list[KnowledgeClaimOut])
def list_claims(
    node_id: str | None = None,
    claim_type: str | None = None,
    category: str | None = None,
    include_history: bool = False,
    limit: int = Query(100, ge=1, le=300),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    claims = knowledge_service.list_claims(
        db,
        user.id,
        node_id=node_id,
        claim_type=claim_type,
        category=category,
        include_history=include_history,
        principal="user",
        limit=limit,
        offset=offset,
    )
    return [_claim_out(claim) for claim in claims]


@router.post("/claims", response_model=KnowledgeClaimOut, status_code=status.HTTP_201_CREATED)
def create_claim(
    data: KnowledgeClaimCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    node = knowledge_service.get_node(db, user.id, data.node_id, principal="user")
    if node is None:
        raise _not_found("Knowledge node not found.")
    try:
        claim, _ = knowledge_service.create_claim(
            db,
            user_id=user.id,
            node=node,
            text=data.text,
            claim_type=data.claim_type,
            category=data.category,
            confidence=data.confidence,
            verification_status=data.verification_status,
            sensitivity=data.sensitivity,
            evidence_text=data.evidence_text,
            extraction_method="user_entry",
        )
    except KnowledgeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    knowledge_service.mark_node_dirty(db, user.id, node.id)
    db.commit()
    db.refresh(claim)
    return _claim_out(claim)


@router.get("/claims/{claim_id}", response_model=KnowledgeClaimOut)
def get_claim(
    claim_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    claim = knowledge_service.get_claim(db, user.id, claim_id, principal="user")
    if claim is None:
        raise _not_found("Knowledge claim not found.")
    return _claim_out(claim)


@router.patch("/claims/{claim_id}", response_model=KnowledgeClaimOut)
def update_claim(
    claim_id: str,
    data: KnowledgeClaimUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        claim = knowledge_service.update_claim(
            db, user.id, claim_id, **data.model_dump(exclude_none=True), actor="user"
        )
    except KnowledgeError as exc:
        raise _not_found(str(exc)) from exc
    db.commit()
    return _claim_out(claim)


@router.post("/claims/{claim_id}/archive", response_model=KnowledgeClaimOut)
def archive_claim(
    claim_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    try:
        claim = knowledge_service.archive_claim(db, user.id, claim_id)
    except KnowledgeError as exc:
        raise _not_found(str(exc)) from exc
    db.commit()
    return _claim_out(claim)


@router.delete("/claims/{claim_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_claim(
    claim_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if not knowledge_service.delete_claim(db, user.id, claim_id):
        raise _not_found("Knowledge claim not found.")
    db.commit()
    return None


@router.get("/claims/{claim_id}/evidence")
def get_claim_evidence(
    claim_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    claim = knowledge_service.get_claim(db, user.id, claim_id, principal="user")
    if claim is None:
        raise _not_found("Knowledge claim not found.")
    return [
        {
            "id": evidence.id,
            "source_id": evidence.source_id,
            "evidence_text": evidence.evidence_text,
            "context_excerpt": evidence.context_excerpt,
            "extraction_method": evidence.extraction_method,
            "confidence": evidence.confidence,
            "created_at": evidence.created_at,
        }
        for evidence in claim.evidence
    ]


# --- sources, search, capture ------------------------------------------------


@router.get("/sources", response_model=list[KnowledgeSourceOut])
def list_sources(
    source_type: str | None = None,
    limit: int = Query(100, ge=1, le=300),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    q = db.query(KnowledgeSource).filter(KnowledgeSource.user_id == user.id)
    if source_type:
        q = q.filter(KnowledgeSource.source_type == source_type)
    sources = q.order_by(KnowledgeSource.created_at.desc()).limit(limit).offset(offset).all()
    return [_source_out(source) for source in sources]


@router.get("/search", response_model=KnowledgeSearchOut)
def search_knowledge_get(
    query: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(10, ge=1, le=50),
    include_history: bool = Query(False),
    as_of: datetime | None = Query(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    result = knowledge_retrieval.search(
        db,
        user_id=user.id,
        query=query,
        principal="user",
        limit=limit,
        include_history=include_history,
        as_of=as_of,
    )
    return KnowledgeSearchOut(**result)


@router.post("/search", response_model=KnowledgeSearchOut)
def search_knowledge(
    data: KnowledgeSearchIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    result = knowledge_retrieval.search(
        db,
        user_id=user.id,
        query=data.query,
        principal="user",
        limit=data.limit,
        categories=data.categories or None,
        node_types=data.node_types or None,
        include_history=data.include_history,
        as_of=data.as_of,
    )
    return KnowledgeSearchOut(**result)


@router.post("/capture", response_model=KnowledgeCaptureOut, status_code=status.HTTP_202_ACCEPTED)
def capture_knowledge(
    data: KnowledgeCaptureIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    result = capture_text(
        db,
        user_id=user.id,
        text=data.text,
        source_type=data.source_type,
        source_ref=data.source_ref,
        title=data.title,
        origin=data.origin,
        process_now=data.process_now,
    )
    return KnowledgeCaptureOut(**result)


# --- Markdown vault ----------------------------------------------------------


@router.get("/notes", response_model=list[KnowledgeNoteOut])
def list_notes(
    note_type: str | None = None,
    query: str | None = None,
    include_archived: bool = False,
    limit: int = Query(100, ge=1, le=250),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    notes = markdown_sync.list_notes(
        db,
        user.id,
        note_type=note_type,
        query=query,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return [_note_out(note) for note in notes]


@router.post("/notes", response_model=KnowledgeNoteOut, status_code=status.HTTP_201_CREATED)
def create_note(
    data: KnowledgeNoteCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        note = markdown_sync.create_note(
            db,
            user_id=user.id,
            title=data.title,
            content=data.content,
            category=data.category,
            tags=data.tags,
            node_id=data.node_id,
        )
    except MarkdownSyncError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.commit()
    return _note_out(note)


@router.get("/notes/{note_id}", response_model=KnowledgeNoteDetail)
def read_note(
    note_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    detail = markdown_sync.read_note(db, user_id=user.id, note_id=note_id)
    if detail is None:
        raise _not_found("Knowledge note not found.")
    db.commit()
    return KnowledgeNoteDetail(
        note=_note_out(detail["note"]),
        content=detail["content"],
        content_hash=detail["content_hash"],
        missing=detail["missing"],
    )


@router.patch("/notes/{note_id}", response_model=KnowledgeNoteOut)
def update_note(
    note_id: str,
    data: KnowledgeNoteUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        note = markdown_sync.update_note(
            db,
            user_id=user.id,
            note_id=note_id,
            content=data.content,
            expected_hash=data.expected_hash,
            actor="user",
        )
    except MarkdownConflictError as exc:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "conflict_path": exc.conflict_path,
                "current_content": exc.current_content,
            },
        ) from exc
    except MarkdownSyncError as exc:
        raise _not_found(str(exc)) from exc
    db.commit()
    return _note_out(note)


@router.post("/notes/{note_id}/rename", response_model=KnowledgeNoteOut)
def rename_note(
    note_id: str,
    data: KnowledgeNoteRename,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        note = markdown_sync.rename_note(
            db, user_id=user.id, note_id=note_id, title=data.title, category=data.category
        )
    except MarkdownSyncError as exc:
        raise _not_found(str(exc)) from exc
    db.commit()
    return _note_out(note)


@router.post("/notes/{note_id}/archive", response_model=KnowledgeNoteOut)
def archive_note(
    note_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    try:
        note = markdown_sync.archive_note(db, user_id=user.id, note_id=note_id)
    except MarkdownSyncError as exc:
        raise _not_found(str(exc)) from exc
    db.commit()
    return _note_out(note)


@router.post("/notes/{note_id}/restore", response_model=KnowledgeNoteOut)
def restore_note(
    note_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    try:
        note = markdown_sync.restore_note(db, user_id=user.id, note_id=note_id)
    except MarkdownSyncError as exc:
        raise _not_found(str(exc)) from exc
    db.commit()
    return _note_out(note)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if not markdown_sync.delete_note(db, user_id=user.id, note_id=note_id):
        raise _not_found("Knowledge note not found.")
    db.commit()
    return None


@router.post("/notes/import")
def import_note(
    data: KnowledgeImportIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        result = markdown_sync.import_markdown(
            db, user_id=user.id, path=data.path, content=data.content, actor="user"
        )
    except MarkdownSyncError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return result


@router.post("/import")
def import_knowledge(
    data: KnowledgeImportIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        result = markdown_sync.import_markdown(
            db, user_id=user.id, path=data.path, content=data.content, actor="user"
        )
    except MarkdownSyncError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return result


@router.get("/export")
def export_knowledge(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return knowledge_service.export_knowledge(db, user.id, principal="user")


@router.post("/vault/reconcile")
def reconcile_vault(
    limit: int = Query(200, ge=1, le=250),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        result = markdown_sync.reconcile(db, user_id=user.id, limit=limit)
    except MarkdownSyncError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.commit()
    return result


@router.post("/vault/rebuild-index")
def rebuild_index(user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        result = markdown_sync.rebuild_index(db, user_id=user.id)
    except MarkdownSyncError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.commit()
    return result


# --- history, insights, jobs, permissions, migration -------------------------


@router.get("/history", response_model=list[KnowledgeVersionOut])
def get_history(
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = Query(100, ge=1, le=300),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    versions = knowledge_service.history(
        db,
        user.id,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        offset=offset,
    )
    return [_version_out(version) for version in versions]


@router.get("/insights")
def get_insights(
    limit: int = Query(40, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    claim_types = [
        ClaimType.INFERENCE.value,
        ClaimType.UNDERSTANDING.value,
        "insight",
    ]
    claims = knowledge_service.list_claims(
        db, user.id, principal="user", limit=limit * 2, include_history=False
    )
    insights = [claim for claim in claims if claim.claim_type in claim_types][:limit]
    reviews = (
        db.query(KnowledgeReview)
        .filter(KnowledgeReview.user_id == user.id, KnowledgeReview.status == "open")
        .order_by(KnowledgeReview.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "insights": [_claim_out(claim) for claim in insights],
        "reviews": [
            {
                "id": review.id,
                "review_type": review.review_type,
                "target_type": review.target_type,
                "target_id": review.target_id,
                "status": review.status,
                "reason": review.reason,
                "details": review.details or {},
                "created_at": review.created_at,
            }
            for review in reviews
        ],
        "counts": {
            "inferences": sum(1 for c in claims if c.claim_type == ClaimType.INFERENCE.value),
            "understanding": sum(1 for c in claims if c.claim_type == ClaimType.UNDERSTANDING.value),
            "open_reviews": len(reviews),
        },
    }


@router.get("/jobs")
def get_jobs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    recent = (
        db.query(KnowledgeJob)
        .filter(KnowledgeJob.user_id == user.id)
        .order_by(KnowledgeJob.created_at.desc())
        .limit(25)
        .all()
    )
    return {
        **job_stats(db, user_id=user.id),
        "recent": [
            {
                "id": job.id,
                "job_type": job.job_type,
                "status": job.status,
                "attempts": job.attempts,
                "max_attempts": job.max_attempts,
                "last_error": job.last_error,
                "result": job.result,
                "created_at": job.created_at,
                "completed_at": job.completed_at,
            }
            for job in recent
        ],
    }


@router.post("/jobs/drain")
def drain_knowledge_jobs(
    data: KnowledgeJobDrainIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Bounded, serverless-safe job drain for the authenticated user only."""
    return drain_jobs(db, user_id=user.id, limit=data.limit)


@router.post("/consolidate")
def consolidate_knowledge(
    limit: int = Query(100, ge=10, le=400),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    result = consolidate_user_knowledge(db, user_id=user.id, limit=limit)
    db.commit()
    return result


@router.get("/permissions")
def list_permissions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    grants = (
        db.query(KnowledgePermission)
        .filter(KnowledgePermission.user_id == user.id)
        .order_by(KnowledgePermission.created_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": grant.id,
            "knowledge_type": grant.knowledge_type,
            "knowledge_id": grant.knowledge_id,
            "principal_type": grant.principal_type,
            "principal_id": grant.principal_id,
            "access_level": grant.access_level,
            "can_read": grant.can_read,
            "can_write": grant.can_write,
            "expires_at": grant.expires_at,
            "created_at": grant.created_at,
        }
        for grant in grants
    ]


@router.post("/permissions", status_code=status.HTTP_201_CREATED)
def grant_permission(
    data: KnowledgePermissionIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    grant = knowledge_service.grant_permission(
        db,
        user_id=user.id,
        principal_type=data.principal_type,
        principal_id=data.principal_id,
        access_level=data.access_level,
        knowledge_type=data.knowledge_type,
        knowledge_id=data.knowledge_id,
        can_read=data.can_read,
        can_write=data.can_write,
    )
    db.commit()
    return {
        "id": grant.id,
        "principal_type": grant.principal_type,
        "principal_id": grant.principal_id,
        "access_level": grant.access_level,
        "knowledge_type": grant.knowledge_type,
        "knowledge_id": grant.knowledge_id,
        "can_read": grant.can_read,
        "can_write": grant.can_write,
    }


@router.post("/migrate-memory")
def migrate_memory(
    data: KnowledgeMigrationIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return migrate_memories_to_knowledge(
        db, user_id=user.id, dry_run=data.dry_run, limit=data.limit
    )
