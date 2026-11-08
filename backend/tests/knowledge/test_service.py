from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.knowledge.permissions import build_permission_context
from app.knowledge.service import knowledge_service
from app.knowledge.types import ClaimType, VerificationStatus, utcnow


def _source(db: Session, user_id: int, text: str = "test source"):
    return knowledge_service.register_source(
        db,
        user_id=user_id,
        source_type="user_provided",
        source_ref=f"test:{text}",
        content=text,
    )


def test_node_identity_is_deduplicated(db: Session, user_id: int):
    first, created = knowledge_service.resolve_node(
        db, user_id=user_id, name="IRIS Project", node_type="project"
    )
    second, created_again = knowledge_service.resolve_node(
        db, user_id=user_id, name="the IRIS project", node_type="project"
    )
    assert created is True
    assert created_again is False
    assert first.id == second.id
    assert second.aliases == []


def test_claim_deduplication_adds_evidence(db: Session, user_id: int):
    node, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="PostgreSQL", node_type="technology"
    )
    source = _source(db, user_id)
    claim, created = knowledge_service.create_claim(
        db,
        user_id=user_id,
        node=node,
        text="PostgreSQL is the primary database.",
        source_id=source.id,
    )
    same, created_again = knowledge_service.create_claim(
        db,
        user_id=user_id,
        node=node,
        text="PostgreSQL is the primary database.",
        source_id=source.id,
    )
    assert created is True
    assert created_again is False
    assert same.id == claim.id


def test_contradiction_supersedes_and_retains_history(db: Session, user_id: int):
    node, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="IRIS", node_type="project"
    )
    old_time = utcnow() - timedelta(days=30)
    old, _ = knowledge_service.create_claim(
        db,
        user_id=user_id,
        node=node,
        text="IRIS uses PostgreSQL",
        observed_at=old_time,
        valid_from=old_time,
        verification_status=VerificationStatus.USER_STATED.value,
    )
    new, created = knowledge_service.create_claim(
        db,
        user_id=user_id,
        node=node,
        text="IRIS uses MySQL",
        verification_status=VerificationStatus.USER_STATED.value,
    )
    assert created is True
    assert new.id != old.id
    assert old.verification_status == VerificationStatus.SUPERSEDED.value
    assert old.superseded_by_claim_id == new.id
    assert new.supersedes_claim_id == old.id
    assert old.valid_until is not None

    current = knowledge_service.list_claims(db, user_id, node_id=node.id)
    assert [claim.id for claim in current] == [new.id]
    history = knowledge_service.list_claims(db, user_id, node_id=node.id, include_history=True)
    assert {claim.id for claim in history} == {old.id, new.id}
    versions = knowledge_service.history(db, user_id, entity_type="claim", entity_id=old.id)
    assert any(version.change_type == "supersede" for version in versions)


def test_relationships_and_bounded_traversal(db: Session, user_id: int):
    project, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="IRIS", node_type="project"
    )
    tech, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="FastAPI", node_type="technology"
    )
    knowledge_service.upsert_relationship(
        db,
        user_id=user_id,
        source_node_id=project.id,
        target_node_id=tech.id,
        relationship_type="USES",
        confidence=0.9,
    )
    graph = knowledge_service.traverse(db, user_id, project.id, depth=1, principal="user")
    assert {node.id for node in graph["nodes"]} == {project.id, tech.id}
    assert len(graph["relationships"]) == 1
    assert graph["truncated"] is False


def test_extraction_persistence_creates_claims_and_bounded_jobs(db: Session, user_id: int):
    source = _source(db, user_id, "persistence")
    summary = knowledge_service.persist_extraction(
        db,
        user_id=user_id,
        source=source,
        items=[
            {
                "text": "We decided to use PostgreSQL.",
                "node_name": "IRIS",
                "node_type": "project",
                "claim_type": ClaimType.DECISION.value,
                "category": "projects",
                "verification_status": VerificationStatus.USER_STATED.value,
                "confidence": 0.9,
            },
            {
                "text": "IRIS supports offline mode.",
                "node_name": "IRIS",
                "node_type": "project",
                "claim_type": ClaimType.FACT.value,
                "category": "projects",
                "verification_status": VerificationStatus.USER_STATED.value,
            },
        ],
    )
    assert summary["created_claims"] == 2
    assert summary["created_nodes"] >= 1
    from app.models.knowledge import KnowledgeJob

    jobs = db.query(KnowledgeJob).filter(KnowledgeJob.user_id == user_id).all()
    markdown_jobs = [job for job in jobs if job.job_type == "update_markdown"]
    embedding_jobs = [job for job in jobs if job.job_type == "generate_embeddings"]
    # One Markdown job per affected node, one embedding job per unique claim.
    assert len(markdown_jobs) == 1
    assert len(embedding_jobs) == 2


def test_permission_context_blocks_private_types_and_honours_grants(db: Session, user_id: int):
    person, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="My Sister", node_type="person"
    )
    developer = build_permission_context(db, user_id, "coworker:developer")
    assert developer.can_read(
        sensitivity="personal",
        access_level="personal",
        node_type="person",
        category="personal",
        node_id=person.id,
    ) is False

    knowledge_service.grant_permission(
        db,
        user_id=user_id,
        principal_type="coworker",
        principal_id="developer",
        knowledge_type="node",
        knowledge_id=person.id,
        access_level="personal",
    )
    db.flush()
    granted = build_permission_context(db, user_id, "coworker:developer")
    assert granted.can_read(
        sensitivity="personal",
        access_level="personal",
        node_type="person",
        category="personal",
        node_id=person.id,
    ) is True
    assert granted.can_write(node_id=person.id) is False
