"""Knowledge service: the single authorised boundary for all knowledge writes.

Coworkers and tools must call this service (or the retrieval service built on
it); they must never query knowledge tables directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Sequence
from uuid import uuid4

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.knowledge import resolution
from app.knowledge.embeddings import embedding_service
from app.knowledge.observability import knowledge_metrics
from app.knowledge.permissions import (
    PermissionContext,
    build_permission_context,
    record_denial,
)
from app.knowledge.types import (
    AccessLevel,
    CATEGORY_LABELS,
    ClaimType,
    JobType,
    NodeType,
    Sensitivity,
    VerificationStatus,
    access_for_sensitivity,
    classify_sensitivity,
    contains_credential,
    content_fingerprint,
    hash_bytes,
    max_sensitivity,
    normalize_entity_name,
    redact_credentials,
    utcnow,
)
from app.models.knowledge import (
    KnowledgeClaim,
    KnowledgeEvidence,
    KnowledgeJob,
    KnowledgeNode,
    KnowledgePermission,
    KnowledgeRelationship,
    KnowledgeReview,
    KnowledgeSource,
    KnowledgeVersion,
)

logger = get_logger("iris.knowledge.service")


class KnowledgeError(RuntimeError):
    pass


class KnowledgePermissionError(KnowledgeError):
    pass


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def claim_snapshot(claim: KnowledgeClaim) -> dict[str, Any]:
    return {
        "id": claim.id,
        "node_id": claim.node_id,
        "claim_text": claim.claim_text,
        "claim_type": claim.claim_type,
        "category": claim.category,
        "confidence": claim.confidence,
        "verification_status": claim.verification_status,
        "source_id": claim.source_id,
        "valid_from": _iso(claim.valid_from),
        "valid_until": _iso(claim.valid_until),
        "observed_at": _iso(claim.observed_at),
        "recorded_at": _iso(claim.recorded_at),
        "supersedes_claim_id": claim.supersedes_claim_id,
        "superseded_by_claim_id": claim.superseded_by_claim_id,
        "sensitivity": claim.sensitivity,
        "access_level": claim.access_level,
        "archived_at": _iso(claim.archived_at),
    }


def node_snapshot(node: KnowledgeNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "node_type": node.node_type,
        "canonical_name": node.canonical_name,
        "description": node.description,
        "aliases": list(node.aliases or []),
        "status": node.status,
        "sensitivity": node.sensitivity,
        "access_level": node.access_level,
        "metadata": dict(node.metadata_json or {}),
        "created_at": _iso(node.created_at),
        "updated_at": _iso(node.updated_at),
        "archived_at": _iso(node.archived_at),
    }


class KnowledgeService:
    # --- sources -------------------------------------------------------------

    def register_source(
        self,
        db: Session,
        *,
        user_id: int,
        source_type: str,
        source_ref: str,
        title: str | None = None,
        content: str | None = None,
        conversation_id: int | None = None,
        message_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        sensitivity: str | None = None,
    ) -> KnowledgeSource:
        content_hash = hash_bytes((content or source_ref).encode("utf-8"))
        existing = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.user_id == user_id,
                KnowledgeSource.source_type == source_type,
                KnowledgeSource.source_ref == source_ref,
                KnowledgeSource.content_hash == content_hash,
            )
            .first()
        )
        if existing:
            return existing
        sensitivity = sensitivity or classify_sensitivity(content or source_ref)
        source = KnowledgeSource(
            user_id=user_id,
            source_type=source_type,
            source_ref=source_ref[:512],
            title=(title or "")[:255] or None,
            conversation_id=conversation_id,
            message_id=message_id,
            content_hash=content_hash,
            sensitivity=sensitivity,
            access_level=access_for_sensitivity(sensitivity),
            metadata_json=metadata or {},
        )
        db.add(source)
        db.flush()
        return source

    # --- nodes ---------------------------------------------------------------

    def find_node(
        self, db: Session, user_id: int, name: str, node_type: str | None = None
    ) -> KnowledgeNode | None:
        normalized = normalize_entity_name(name)
        if not normalized:
            return None
        query = db.query(KnowledgeNode).filter(
            KnowledgeNode.user_id == user_id,
            KnowledgeNode.normalized_name == normalized,
            KnowledgeNode.status == "active",
        )
        if node_type:
            query = query.filter(KnowledgeNode.node_type == node_type)
        return query.first()

    def resolve_node(
        self,
        db: Session,
        *,
        user_id: int,
        name: str,
        node_type: str,
        description: str | None = None,
        sensitivity: str | None = None,
        access_level: str | None = None,
        aliases: Iterable[str] | None = None,
    ) -> tuple[KnowledgeNode, bool]:
        normalized = normalize_entity_name(name)
        if not normalized:
            raise KnowledgeError("A knowledge node needs a non-empty name.")
        existing = self.find_node(db, user_id, name, node_type)
        if existing:
            changed = False
            for alias in aliases or []:
                if alias and alias not in existing.aliases:
                    existing.aliases = [*(existing.aliases or []), alias]
                    changed = True
            if description and not existing.description:
                existing.description = description
                changed = True
            if sensitivity:
                merged = max_sensitivity(existing.sensitivity, sensitivity)
                if merged != existing.sensitivity:
                    existing.sensitivity = merged
                    existing.access_level = access_for_sensitivity(merged)
                    changed = True
            if changed:
                db.flush()
            return existing, False

        sensitivity = sensitivity or classify_sensitivity(name, node_type)
        node = KnowledgeNode(
            user_id=user_id,
            node_type=node_type,
            canonical_name=name.strip()[:255],
            normalized_name=normalized,
            description=description,
            aliases=list(dict.fromkeys(aliases or [])),
            sensitivity=sensitivity,
            access_level=access_level or access_for_sensitivity(sensitivity),
            metadata_json={},
        )
        db.add(node)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            existing = self.find_node(db, user_id, name, node_type)
            if not existing:
                raise
            return existing, False
        self._record_version(db, user_id, "node", node.id, "create", node_snapshot(node))
        knowledge_metrics.increment("nodes_created")
        return node, True

    def list_nodes(
        self,
        db: Session,
        user_id: int,
        *,
        node_type: str | None = None,
        query: str | None = None,
        principal: str = "iris_core",
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[KnowledgeNode]:
        q = db.query(KnowledgeNode).filter(KnowledgeNode.user_id == user_id)
        if node_type:
            q = q.filter(KnowledgeNode.node_type == node_type)
        if not include_archived:
            q = q.filter(KnowledgeNode.status == "active")
        if query:
            like = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    KnowledgeNode.canonical_name.ilike(like),
                    KnowledgeNode.description.ilike(like),
                )
            )
        nodes = q.order_by(KnowledgeNode.updated_at.desc()).limit(min(limit, 200)).offset(offset).all()
        permission = build_permission_context(db, user_id, principal)
        return [node for node in nodes if self._node_visible(permission, node)]

    def get_node(
        self, db: Session, user_id: int, node_id: str, principal: str = "iris_core"
    ) -> KnowledgeNode | None:
        node = (
            db.query(KnowledgeNode)
            .filter(KnowledgeNode.id == node_id, KnowledgeNode.user_id == user_id)
            .first()
        )
        if not node:
            return None
        permission = build_permission_context(db, user_id, principal)
        if not self._node_visible(permission, node):
            record_denial(principal, "node_read")
            return None
        return node

    def update_node(
        self,
        db: Session,
        user_id: int,
        node_id: str,
        *,
        updates: dict[str, Any],
        actor: str = "user",
    ) -> KnowledgeNode:
        node = self.get_node(db, user_id, node_id, principal="user")
        if not node:
            raise KnowledgeError("Knowledge node not found.")
        permission = build_permission_context(db, user_id, "user")
        if not permission.can_write(node_id=node.id):
            raise KnowledgePermissionError("Write access denied.")
        for field in ("description", "status", "sensitivity", "access_level"):
            if field in updates and updates[field] is not None:
                setattr(node, field, updates[field])
        if updates.get("canonical_name"):
            node.canonical_name = str(updates["canonical_name"])[:255]
            node.normalized_name = normalize_entity_name(node.canonical_name)
        if updates.get("aliases") is not None:
            node.aliases = list(dict.fromkeys(str(a) for a in updates["aliases"] if str(a).strip()))
        node.updated_at = utcnow()
        db.flush()
        self._record_version(
            db, user_id, "node", node.id, "update", node_snapshot(node), actor=actor
        )
        db.flush()
        self.mark_node_dirty(db, user_id, node.id)
        return node

    def archive_node(self, db: Session, user_id: int, node_id: str) -> KnowledgeNode:
        node = self.get_node(db, user_id, node_id, principal="user")
        if not node:
            raise KnowledgeError("Knowledge node not found.")
        node.status = "archived"
        node.archived_at = utcnow()
        for claim in node.claims:
            claim.archived_at = claim.archived_at or utcnow()
        self._record_version(db, user_id, "node", node.id, "archive", node_snapshot(node), actor="user")
        self.mark_node_dirty(db, user_id, node.id)
        db.flush()
        return node

    def delete_node(self, db: Session, user_id: int, node_id: str) -> bool:
        node = self.get_node(db, user_id, node_id, principal="user")
        if not node:
            return False
        snapshot = node_snapshot(node)
        node.status = "deleted"
        node.archived_at = utcnow()
        self._record_version(db, user_id, "node", node.id, "delete", snapshot, actor="user")
        db.delete(node)
        db.flush()
        return True

    # --- claims --------------------------------------------------------------

    def create_claim(
        self,
        db: Session,
        *,
        user_id: int,
        node: KnowledgeNode,
        text: str,
        claim_type: str = ClaimType.FACT.value,
        category: str = "general",
        confidence: float = 0.6,
        verification_status: str = VerificationStatus.UNVERIFIED.value,
        source_id: str | None = None,
        observed_at: datetime | None = None,
        valid_from: datetime | None = None,
        sensitivity: str | None = None,
        access_level: str | None = None,
        metadata: dict[str, Any] | None = None,
        extraction_method: str = "heuristic",
        evidence_text: str | None = None,
        context_excerpt: str | None = None,
    ) -> tuple[KnowledgeClaim, bool]:
        clean_text = redact_credentials((text or "").strip())
        if not clean_text:
            raise KnowledgeError("A knowledge claim needs text.")
        if contains_credential(text):
            knowledge_metrics.increment("credentials_rejected")
            raise KnowledgeError("Credential material is excluded from knowledge storage.")

        sensitivity = max_sensitivity(
            sensitivity or classify_sensitivity(clean_text, node.node_type),
            node.sensitivity,
        )
        access_level = access_level or access_for_sensitivity(sensitivity)
        fingerprint = content_fingerprint(clean_text)

        active_claims = (
            db.query(KnowledgeClaim)
            .filter(
                KnowledgeClaim.user_id == user_id,
                KnowledgeClaim.node_id == node.id,
                KnowledgeClaim.archived_at.is_(None),
                KnowledgeClaim.valid_until.is_(None),
            )
            .order_by(KnowledgeClaim.recorded_at.desc())
            .limit(80)
            .all()
        )
        for existing in active_claims:
            if existing.fingerprint == fingerprint:
                if (
                    existing.verification_status == VerificationStatus.INFERRED.value
                    and verification_status
                    in {
                        VerificationStatus.USER_STATED.value,
                        VerificationStatus.SOURCE_SUPPORTED.value,
                        VerificationStatus.VERIFIED.value,
                    }
                ):
                    # Promotion is explicit: the old inference is retained and
                    # superseded by a new, stronger claim.
                    claim = self._insert_claim(
                        db,
                        user_id=user_id,
                        node=node,
                        clean_text=clean_text,
                        fingerprint=fingerprint,
                        claim_type=claim_type,
                        category=category,
                        confidence=confidence,
                        verification_status=verification_status,
                        source_id=source_id,
                        observed_at=observed_at,
                        valid_from=valid_from,
                        sensitivity=sensitivity,
                        access_level=access_level,
                        metadata=metadata,
                        extraction_method=extraction_method,
                        evidence_text=evidence_text,
                        context_excerpt=context_excerpt,
                    )
                    self.supersede_claim(
                        db,
                        user_id,
                        existing.id,
                        claim.id,
                        reason="verification_promoted",
                        actor="iris",
                    )
                    return claim, True
                self._add_evidence(
                    db,
                    user_id=user_id,
                    claim=existing,
                    source_id=source_id,
                    evidence_text=evidence_text or clean_text,
                    context_excerpt=context_excerpt,
                    extraction_method=extraction_method,
                )
                knowledge_metrics.increment("claims_deduplicated")
                return existing, False

            if (
                existing.claim_type == claim_type
                and existing.verification_status == verification_status
                and resolution.is_near_duplicate(existing.claim_text, clean_text, threshold=0.93)
            ):
                self._add_evidence(
                    db,
                    user_id=user_id,
                    claim=existing,
                    source_id=source_id,
                    evidence_text=evidence_text or clean_text,
                    context_excerpt=context_excerpt,
                    extraction_method=extraction_method,
                )
                knowledge_metrics.increment("claims_deduplicated")
                return existing, False

            contradiction, reason = resolution.detect_contradiction(existing.claim_text, clean_text)
            if contradiction:
                claim = self._insert_claim(
                    db,
                    user_id=user_id,
                    node=node,
                    clean_text=clean_text,
                    fingerprint=fingerprint,
                    claim_type=claim_type,
                    category=category,
                    confidence=confidence,
                    verification_status=verification_status,
                    source_id=source_id,
                    observed_at=observed_at,
                    valid_from=valid_from,
                    sensitivity=sensitivity,
                    access_level=access_level,
                    metadata=metadata,
                    extraction_method=extraction_method,
                    evidence_text=evidence_text,
                    context_excerpt=context_excerpt,
                )
                self.supersede_claim(
                    db,
                    user_id,
                    existing.id,
                    claim.id,
                    reason=f"contradiction:{reason}",
                    actor="iris",
                )
                return claim, True

        claim = self._insert_claim(
            db,
            user_id=user_id,
            node=node,
            clean_text=clean_text,
            fingerprint=fingerprint,
            claim_type=claim_type,
            category=category,
            confidence=confidence,
            verification_status=verification_status,
            source_id=source_id,
            observed_at=observed_at,
            valid_from=valid_from,
            sensitivity=sensitivity,
            access_level=access_level,
            metadata=metadata,
            extraction_method=extraction_method,
            evidence_text=evidence_text,
            context_excerpt=context_excerpt,
        )
        knowledge_metrics.increment("claims_created")
        return claim, True

    def _insert_claim(self, db: Session, *, user_id: int, node: KnowledgeNode, **kwargs: Any) -> KnowledgeClaim:
        claim = KnowledgeClaim(
            user_id=user_id,
            node_id=node.id,
            claim_text=kwargs["clean_text"],
            fingerprint=kwargs["fingerprint"],
            claim_type=kwargs["claim_type"],
            category=kwargs["category"],
            confidence=max(0.0, min(1.0, float(kwargs["confidence"]))),
            verification_status=kwargs["verification_status"],
            source_id=kwargs["source_id"],
            observed_at=kwargs["observed_at"] or utcnow(),
            valid_from=kwargs["valid_from"] or kwargs["observed_at"] or utcnow(),
            sensitivity=kwargs["sensitivity"],
            access_level=kwargs["access_level"],
            metadata_json={
                **(kwargs.get("metadata") or {}),
                "extraction_method": kwargs["extraction_method"],
            },
        )
        db.add(claim)
        db.flush()
        self._add_evidence(
            db,
            user_id=user_id,
            claim=claim,
            source_id=kwargs["source_id"],
            evidence_text=kwargs.get("evidence_text") or kwargs["clean_text"],
            context_excerpt=kwargs.get("context_excerpt"),
            extraction_method=kwargs["extraction_method"],
        )
        self._record_version(db, user_id, "claim", claim.id, "create", claim_snapshot(claim))
        return claim

    def _add_evidence(
        self,
        db: Session,
        *,
        user_id: int,
        claim: KnowledgeClaim,
        source_id: str | None,
        evidence_text: str | None,
        context_excerpt: str | None,
        extraction_method: str,
    ) -> None:
        safe_text = redact_credentials(evidence_text or "")[:4000]
        existing = (
            db.query(KnowledgeEvidence)
            .filter(
                KnowledgeEvidence.claim_id == claim.id,
                KnowledgeEvidence.source_id == source_id,
                KnowledgeEvidence.evidence_text == safe_text,
            )
            .first()
        )
        if existing:
            return
        db.add(
            KnowledgeEvidence(
                user_id=user_id,
                claim_id=claim.id,
                source_id=source_id,
                evidence_text=safe_text or None,
                context_excerpt=redact_credentials(context_excerpt or "")[:4000] or None,
                extraction_method=extraction_method,
                confidence=claim.confidence,
            )
        )
        db.flush()

    def update_claim(
        self,
        db: Session,
        user_id: int,
        claim_id: str,
        *,
        claim_text: str | None = None,
        verification_status: str | None = None,
        confidence: float | None = None,
        sensitivity: str | None = None,
        actor: str = "user",
    ) -> KnowledgeClaim:
        claim = self.get_claim(db, user_id, claim_id, principal="user")
        if not claim:
            raise KnowledgeError("Knowledge claim not found.")
        permission = build_permission_context(db, user_id, "user")
        if not permission.can_write(node_id=claim.node_id, claim_id=claim.id):
            raise KnowledgePermissionError("Write access denied.")
        before = claim_snapshot(claim)
        if claim_text:
            claim.claim_text = redact_credentials(claim_text.strip())
            claim.fingerprint = content_fingerprint(claim.claim_text)
        if verification_status:
            claim.verification_status = verification_status
        if confidence is not None:
            claim.confidence = max(0.0, min(1.0, confidence))
        if sensitivity:
            claim.sensitivity = sensitivity
            claim.access_level = access_for_sensitivity(sensitivity)
        claim.updated_at = utcnow()
        db.flush()
        self._record_version(
            db,
            user_id,
            "claim",
            claim.id,
            "correction",
            {"before": before, "after": claim_snapshot(claim)},
            actor=actor,
        )
        self.mark_claim_dirty(db, user_id, claim)
        return claim

    def supersede_claim(
        self,
        db: Session,
        user_id: int,
        old_claim_id: str,
        new_claim_id: str,
        *,
        reason: str,
        actor: str = "iris",
    ) -> KnowledgeClaim | None:
        old = (
            db.query(KnowledgeClaim)
            .filter(KnowledgeClaim.id == old_claim_id, KnowledgeClaim.user_id == user_id)
            .first()
        )
        new = (
            db.query(KnowledgeClaim)
            .filter(KnowledgeClaim.id == new_claim_id, KnowledgeClaim.user_id == user_id)
            .first()
        )
        if not old or not new:
            return None
        now = utcnow()
        before = claim_snapshot(old)
        old.valid_until = old.valid_until or now
        old.verification_status = VerificationStatus.SUPERSEDED.value
        old.superseded_by_claim_id = new.id
        new.supersedes_claim_id = old.id
        new.valid_from = new.valid_from or now
        db.add(
            KnowledgeReview(
                user_id=user_id,
                review_type="supersession",
                target_type="claim",
                target_id=old.id,
                status="resolved",
                reason=reason[:500],
                details={"new_claim_id": new.id, "reason": reason},
                resolved_at=now,
            )
        )
        self._record_version(
            db,
            user_id,
            "claim",
            old.id,
            "supersede",
            {"before": before, "after": claim_snapshot(old), "new_claim_id": new.id},
            actor=actor,
            reason=reason,
        )
        db.flush()
        self.mark_claim_dirty(db, user_id, old)
        self.mark_claim_dirty(db, user_id, new)
        knowledge_metrics.increment("claims_superseded")
        return old

    def archive_claim(self, db: Session, user_id: int, claim_id: str) -> KnowledgeClaim:
        claim = self.get_claim(db, user_id, claim_id, principal="user")
        if not claim:
            raise KnowledgeError("Knowledge claim not found.")
        claim.archived_at = utcnow()
        claim.valid_until = claim.valid_until or utcnow()
        self._record_version(
            db, user_id, "claim", claim.id, "archive", claim_snapshot(claim), actor="user"
        )
        self.mark_claim_dirty(db, user_id, claim)
        db.flush()
        return claim

    def delete_claim(self, db: Session, user_id: int, claim_id: str) -> bool:
        claim = self.get_claim(db, user_id, claim_id, principal="user")
        if not claim:
            return False
        self._record_version(
            db, user_id, "claim", claim.id, "delete", claim_snapshot(claim), actor="user"
        )
        db.delete(claim)
        db.flush()
        return True

    def get_claim(
        self, db: Session, user_id: int, claim_id: str, principal: str = "iris_core"
    ) -> KnowledgeClaim | None:
        claim = (
            db.query(KnowledgeClaim)
            .filter(KnowledgeClaim.id == claim_id, KnowledgeClaim.user_id == user_id)
            .first()
        )
        if not claim:
            return None
        node = claim.node
        permission = build_permission_context(db, user_id, principal)
        if node is None or not permission.can_read(
            sensitivity=max_sensitivity(claim.sensitivity, node.sensitivity),
            access_level=claim.access_level,
            node_type=node.node_type,
            category=claim.category,
            node_id=node.id,
            claim_id=claim.id,
        ):
            record_denial(principal, "claim_read")
            return None
        return claim

    def list_claims(
        self,
        db: Session,
        user_id: int,
        *,
        node_id: str | None = None,
        claim_type: str | None = None,
        category: str | None = None,
        include_history: bool = False,
        principal: str = "iris_core",
        limit: int = 100,
        offset: int = 0,
    ) -> list[KnowledgeClaim]:
        q = db.query(KnowledgeClaim).filter(
            KnowledgeClaim.user_id == user_id, KnowledgeClaim.archived_at.is_(None)
        )
        if node_id:
            q = q.filter(KnowledgeClaim.node_id == node_id)
        if claim_type:
            q = q.filter(KnowledgeClaim.claim_type == claim_type)
        if category:
            q = q.filter(KnowledgeClaim.category == category)
        if not include_history:
            q = q.filter(KnowledgeClaim.valid_until.is_(None))
        claims = (
            q.order_by(KnowledgeClaim.recorded_at.desc())
            .limit(min(limit, 300))
            .offset(offset)
            .all()
        )
        permission = build_permission_context(db, user_id, principal)
        visible = []
        for claim in claims:
            node = claim.node
            if node is None:
                continue
            if permission.can_read(
                sensitivity=max_sensitivity(claim.sensitivity, node.sensitivity),
                access_level=claim.access_level,
                node_type=node.node_type,
                category=claim.category,
                node_id=node.id,
                claim_id=claim.id,
            ):
                visible.append(claim)
            else:
                record_denial(principal, "claim_list")
        return visible

    # --- relationships -------------------------------------------------------

    def upsert_relationship(
        self,
        db: Session,
        *,
        user_id: int,
        source_node_id: str,
        target_node_id: str,
        relationship_type: str,
        confidence: float = 0.5,
        source_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[KnowledgeRelationship, bool]:
        if source_node_id == target_node_id:
            raise KnowledgeError("A relationship needs two distinct nodes.")
        existing = (
            db.query(KnowledgeRelationship)
            .filter(
                KnowledgeRelationship.user_id == user_id,
                KnowledgeRelationship.source_node_id == source_node_id,
                KnowledgeRelationship.target_node_id == target_node_id,
                KnowledgeRelationship.relationship_type == relationship_type,
                KnowledgeRelationship.valid_until.is_(None),
            )
            .first()
        )
        if existing:
            existing.confidence = max(existing.confidence, confidence)
            return existing, False
        relationship = KnowledgeRelationship(
            user_id=user_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relationship_type=relationship_type[:50],
            confidence=confidence,
            source_id=source_id,
            valid_from=utcnow(),
            metadata_json=metadata or {},
        )
        db.add(relationship)
        db.flush()
        knowledge_metrics.increment("relationships_created")
        return relationship, True

    def delete_relationship(self, db: Session, user_id: int, relationship_id: str) -> bool:
        relationship = (
            db.query(KnowledgeRelationship)
            .filter(
                KnowledgeRelationship.id == relationship_id,
                KnowledgeRelationship.user_id == user_id,
            )
            .first()
        )
        if not relationship:
            return False
        relationship.valid_until = utcnow()
        db.flush()
        return True

    def list_relationships(
        self,
        db: Session,
        user_id: int,
        *,
        source_node_id: str | None = None,
        target_node_id: str | None = None,
        relationship_type: str | None = None,
        include_history: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[KnowledgeRelationship]:
        query = db.query(KnowledgeRelationship).filter(
            KnowledgeRelationship.user_id == user_id
        )
        if not include_history:
            query = query.filter(KnowledgeRelationship.valid_until.is_(None))
        if source_node_id:
            query = query.filter(KnowledgeRelationship.source_node_id == source_node_id)
        if target_node_id:
            query = query.filter(KnowledgeRelationship.target_node_id == target_node_id)
        if relationship_type:
            query = query.filter(KnowledgeRelationship.relationship_type == relationship_type)
        return query.order_by(KnowledgeRelationship.created_at.desc()).offset(offset).limit(limit).all()

    def export_knowledge(
        self,
        db: Session,
        user_id: int,
        *,
        principal: str = "iris_core",
    ) -> dict[str, Any]:
        """Export all authorised knowledge for the user."""
        nodes = self.list_nodes(db, user_id, limit=1000, principal=principal)
        claims = self.list_claims(db, user_id, limit=2000, principal=principal)
        relationships = self.list_relationships(db, user_id, limit=2000)
        from app.models.knowledge import KnowledgeNote, KnowledgeSource

        sources = (
            db.query(KnowledgeSource)
            .filter(KnowledgeSource.user_id == user_id)
            .limit(1000)
            .all()
        )
        notes = (
            db.query(KnowledgeNote)
            .filter(KnowledgeNote.user_id == user_id, KnowledgeNote.archived_at.is_(None))
            .limit(1000)
            .all()
        )
        return {
            "exported_at": utcnow().isoformat(),
            "user_id": user_id,
            "counts": {
                "nodes": len(nodes),
                "claims": len(claims),
                "relationships": len(relationships),
                "sources": len(sources),
                "notes": len(notes),
            },
            "nodes": [node_snapshot(n) for n in nodes],
            "claims": [claim_snapshot(c) for c in claims],
            "relationships": [
                {
                    "id": r.id,
                    "source_node_id": r.source_node_id,
                    "target_node_id": r.target_node_id,
                    "relationship_type": r.relationship_type,
                    "confidence": r.confidence,
                    "valid_from": _iso(r.valid_from),
                    "valid_until": _iso(r.valid_until),
                    "metadata": r.metadata_json,
                }
                for r in relationships
            ],
            "sources": [
                {
                    "id": s.id,
                    "source_type": s.source_type,
                    "source_ref": s.source_ref,
                    "title": s.title,
                    "created_at": _iso(s.created_at),
                }
                for s in sources
            ],
            "notes": [
                {
                    "id": n.id,
                    "title": n.title,
                    "storage_path": n.storage_path,
                    "sync_status": n.sync_status,
                }
                for n in notes
            ],
        }

    def traverse(
        self,
        db: Session,
        user_id: int,
        start_node_id: str,
        *,
        depth: int = 1,
        limit: int = 40,
        principal: str = "iris_core",
    ) -> dict[str, Any]:
        """Bounded breadth-first graph traversal."""
        depth = max(0, min(int(depth), 3))
        limit = max(1, min(int(limit), 100))
        permission = build_permission_context(db, user_id, principal)
        root = (
            db.query(KnowledgeNode)
            .filter(KnowledgeNode.id == start_node_id, KnowledgeNode.user_id == user_id)
            .first()
        )
        if not root or not self._node_visible(permission, root):
            return {"nodes": [], "relationships": [], "truncated": False}
        nodes: dict[str, KnowledgeNode] = {root.id: root}
        edges: dict[str, KnowledgeRelationship] = {}
        frontier = [root.id]
        truncated = False
        for _ in range(depth):
            if not frontier or len(nodes) >= limit:
                break
            rows = (
                db.query(KnowledgeRelationship)
                .filter(
                    KnowledgeRelationship.user_id == user_id,
                    KnowledgeRelationship.valid_until.is_(None),
                    or_(
                        KnowledgeRelationship.source_node_id.in_(frontier),
                        KnowledgeRelationship.target_node_id.in_(frontier),
                    ),
                )
                .limit(limit * 3)
                .all()
            )
            next_frontier: list[str] = []
            for edge in rows:
                other_id = (
                    edge.target_node_id
                    if edge.source_node_id in nodes
                    else edge.source_node_id
                )
                if other_id in nodes:
                    edges[edge.id] = edge
                    continue
                other = (
                    db.query(KnowledgeNode)
                    .filter(KnowledgeNode.id == other_id, KnowledgeNode.user_id == user_id)
                    .first()
                )
                if not other or not self._node_visible(permission, other):
                    continue
                if len(nodes) >= limit:
                    truncated = True
                    break
                nodes[other.id] = other
                edges[edge.id] = edge
                next_frontier.append(other.id)
            frontier = next_frontier
        return {
            "nodes": list(nodes.values()),
            "relationships": list(edges.values()),
            "truncated": truncated,
        }

    # --- extraction persistence ---------------------------------------------

    def persist_extraction(
        self,
        db: Session,
        *,
        user_id: int,
        source: KnowledgeSource,
        items: Sequence[dict[str, Any]],
    ) -> dict[str, Any]:
        created_claims = 0
        duplicate_claims = 0
        created_nodes = 0
        relationships = 0
        claims: list[KnowledgeClaim] = []
        for item in items:
            node_name = (item.get("node_name") or "").strip()
            if not node_name:
                continue
            node_type = item.get("node_type") or NodeType.TOPIC.value
            node, node_created = self.resolve_node(
                db,
                user_id=user_id,
                name=node_name,
                node_type=node_type,
                sensitivity=item.get("sensitivity"),
                aliases=item.get("aliases") or [],
            )
            created_nodes += int(node_created)
            claim, was_created = self.create_claim(
                db,
                user_id=user_id,
                node=node,
                text=item.get("text", ""),
                claim_type=item.get("claim_type", ClaimType.FACT.value),
                category=item.get("category") or "general",
                confidence=float(item.get("confidence", 0.6)),
                verification_status=item.get(
                    "verification_status", VerificationStatus.UNVERIFIED.value
                ),
                source_id=source.id,
                observed_at=item.get("observed_at"),
                sensitivity=item.get("sensitivity"),
                metadata=item.get("metadata") or {},
                extraction_method=item.get("extraction_method", "heuristic"),
                evidence_text=item.get("evidence_text"),
                context_excerpt=item.get("context_excerpt"),
            )
            claims.append(claim)
            created_claims += int(was_created)
            duplicate_claims += int(not was_created)
            if was_created:
                if claim.claim_type == ClaimType.DECISION.value and node.node_type != NodeType.DECISION.value:
                    decision_node, decision_created = self.resolve_node(
                        db,
                        user_id=user_id,
                        name=item.get("decision_name") or item.get("text", "")[:120],
                        node_type=NodeType.DECISION.value,
                        sensitivity=claim.sensitivity,
                    )
                    created_nodes += int(decision_created)
                    if decision_node.id != node.id:
                        self.upsert_relationship(
                            db,
                            user_id=user_id,
                            source_node_id=decision_node.id,
                            target_node_id=node.id,
                            relationship_type="AFFECTS",
                            confidence=claim.confidence,
                            source_id=source.id,
                        )
                        relationships += 1
                for relation in item.get("relationships") or []:
                    target_name = (relation.get("target_name") or "").strip()
                    if not target_name:
                        continue
                    target_type = relation.get("target_type") or NodeType.TOPIC.value
                    target, target_created = self.resolve_node(
                        db,
                        user_id=user_id,
                        name=target_name,
                        node_type=target_type,
                        sensitivity=item.get("sensitivity"),
                    )
                    created_nodes += int(target_created)
                    if target.id == node.id:
                        continue
                    relationship_type = relation.get("relationship_type") or (
                        resolution.relationship_type_for(node.node_type, target.node_type, relation.get("context", ""))
                    )
                    _, relation_created = self.upsert_relationship(
                        db,
                        user_id=user_id,
                        source_node_id=node.id,
                        target_node_id=target.id,
                        relationship_type=relationship_type,
                        confidence=float(relation.get("confidence", claim.confidence)),
                        source_id=source.id,
                    )
                    relationships += int(relation_created)
        # Bounded follow-up work: one Markdown job per affected node and one
        # embedding job per genuinely new claim (duplicates reuse the existing
        # claim's embedding and do not enqueue another job).
        from app.knowledge.jobs import enqueue_job

        for node_id in dict.fromkeys(claim.node_id for claim in claims):
            self.mark_node_dirty(db, user_id, node_id)
        for claim_id in dict.fromkeys(claim.id for claim in claims if claim.id):
            enqueue_job(
                db,
                user_id=user_id,
                job_type=JobType.GENERATE_EMBEDDINGS.value,
                payload={"knowledge_type": "claim", "knowledge_id": claim_id},
                idempotency_key=f"embed:claim:{claim_id}",
                priority=60,
            )
        db.flush()
        return {
            "source_id": source.id,
            "created_claims": created_claims,
            "duplicate_claims": duplicate_claims,
            "created_nodes": created_nodes,
            "relationships": relationships,
            "claims": [claim.id for claim in claims],
        }

    # --- markdown bookkeeping ------------------------------------------------

    def mark_node_dirty(self, db: Session, user_id: int, node_id: str) -> None:
        from app.knowledge.jobs import enqueue_job

        enqueue_job(
            db,
            user_id=user_id,
            job_type=JobType.UPDATE_MARKDOWN.value,
            payload={"node_id": node_id},
            idempotency_key=f"markdown:node:{node_id}:{utcnow().isoformat(timespec='seconds')}",
            priority=80,
        )

    def mark_claim_dirty(
        self, db: Session, user_id: int, claim: KnowledgeClaim, *, enqueue: bool = True
    ) -> None:
        if enqueue:
            self.mark_node_dirty(db, user_id, claim.node_id)

    # --- versions, overview, history ----------------------------------------

    def _record_version(
        self,
        db: Session,
        user_id: int,
        entity_type: str,
        entity_id: str,
        change_type: str,
        snapshot: dict[str, Any],
        *,
        actor: str = "iris",
        reason: str | None = None,
    ) -> KnowledgeVersion:
        latest = (
            db.query(func.max(KnowledgeVersion.version_number))
            .filter(
                KnowledgeVersion.user_id == user_id,
                KnowledgeVersion.entity_type == entity_type,
                KnowledgeVersion.entity_id == entity_id,
            )
            .scalar()
        )
        version = KnowledgeVersion(
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            version_number=int(latest or 0) + 1,
            change_type=change_type,
            change_reason=reason,
            actor=actor,
            snapshot=snapshot,
        )
        db.add(version)
        db.flush()
        return version

    def history(
        self,
        db: Session,
        user_id: int,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[KnowledgeVersion]:
        q = db.query(KnowledgeVersion).filter(KnowledgeVersion.user_id == user_id)
        if entity_type:
            q = q.filter(KnowledgeVersion.entity_type == entity_type)
        if entity_id:
            q = q.filter(KnowledgeVersion.entity_id == entity_id)
        return (
            q.order_by(KnowledgeVersion.created_at.desc())
            .limit(min(limit, 300))
            .offset(offset)
            .all()
        )

    def overview(self, db: Session, user_id: int, principal: str = "user") -> dict[str, Any]:
        permission = build_permission_context(db, user_id, principal)
        nodes = (
            db.query(KnowledgeNode)
            .filter(KnowledgeNode.user_id == user_id, KnowledgeNode.status == "active")
            .order_by(KnowledgeNode.updated_at.desc())
            .limit(200)
            .all()
        )
        visible_nodes = [node for node in nodes if self._node_visible(permission, node)]
        node_ids = {node.id for node in visible_nodes}
        claims = (
            db.query(KnowledgeClaim)
            .filter(
                KnowledgeClaim.user_id == user_id,
                KnowledgeClaim.archived_at.is_(None),
                KnowledgeClaim.valid_until.is_(None),
            )
            .order_by(KnowledgeClaim.recorded_at.desc())
            .limit(300)
            .all()
        )
        visible_claims = []
        for claim in claims:
            node = claim.node
            if node and node.id in node_ids and permission.can_read(
                sensitivity=max_sensitivity(claim.sensitivity, node.sensitivity),
                access_level=claim.access_level,
                node_type=node.node_type,
                category=claim.category,
                node_id=node.id,
                claim_id=claim.id,
            ):
                visible_claims.append(claim)
        recent_insights = [
            claim for claim in visible_claims
            if claim.claim_type in {ClaimType.INFERENCE.value, ClaimType.UNDERSTANDING.value}
        ][:6]
        by_type = (
            db.query(KnowledgeNode.node_type, func.count(KnowledgeNode.id))
            .filter(KnowledgeNode.user_id == user_id, KnowledgeNode.status == "active")
            .group_by(KnowledgeNode.node_type)
            .all()
        )
        reviews = (
            db.query(KnowledgeReview)
            .filter(KnowledgeReview.user_id == user_id, KnowledgeReview.status == "open")
            .order_by(KnowledgeReview.created_at.desc())
            .limit(10)
            .all()
        )
        categories = sorted({claim.category for claim in visible_claims})
        return {
            "recent_nodes": visible_nodes[:8],
            "recent_claims": visible_claims[:12],
            "important_projects": [n for n in visible_nodes if n.node_type == NodeType.PROJECT.value][:6],
            "recent_insights": recent_insights,
            "reviews": reviews,
            "categories": [
                {"key": key, "label": CATEGORY_LABELS.get(key, key.title())} for key in categories
            ],
            "counts_by_type": {node_type: count for node_type, count in by_type},
            "totals": {
                "nodes": len(visible_nodes),
                "claims": len(visible_claims),
            },
        }

    # --- helpers -------------------------------------------------------------

    def _node_visible(self, permission: PermissionContext, node: KnowledgeNode) -> bool:
        return permission.can_read(
            sensitivity=node.sensitivity,
            access_level=node.access_level,
            node_type=node.node_type,
            node_id=node.id,
        )

    def grant_permission(
        self,
        db: Session,
        *,
        user_id: int,
        principal_type: str,
        principal_id: str,
        access_level: str = AccessLevel.PERSONAL.value,
        knowledge_type: str = "global",
        knowledge_id: str | None = None,
        can_read: bool = True,
        can_write: bool = False,
    ) -> KnowledgePermission:
        grant = KnowledgePermission(
            user_id=user_id,
            knowledge_type=knowledge_type,
            knowledge_id=knowledge_id,
            principal_type=principal_type,
            principal_id=principal_id,
            access_level=access_level,
            can_read=can_read,
            can_write=can_write,
        )
        db.add(grant)
        db.flush()
        return grant


knowledge_service = KnowledgeService()
