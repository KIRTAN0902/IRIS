from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.knowledge.retrieval import knowledge_retrieval
from app.knowledge.service import knowledge_service
from app.knowledge.types import VerificationStatus, utcnow


def _node_claim(db, user_id, name, node_type, text, **kwargs):
    node, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name=name, node_type=node_type
    )
    claim, _ = knowledge_service.create_claim(
        db, user_id=user_id, node=node, text=text, **kwargs
    )
    return node, claim


def test_hybrid_retrieval_finds_lexical_and_semantic_matches(db: Session, user_id: int):
    _node_claim(
        db, user_id, "IRIS", "project",
        "IRIS uses FastAPI for the backend and PostgreSQL for storage.",
        verification_status=VerificationStatus.USER_STATED.value,
    )
    _node_claim(
        db, user_id, "Gym", "topic",
        "The user prefers morning workouts.",
        verification_status=VerificationStatus.USER_STATED.value,
    )
    result = knowledge_retrieval.search(
        db, user_id=user_id, query="FastAPI backend", principal="user", limit=5
    )
    assert result["count"] >= 1
    top = result["results"][0]
    assert "FastAPI" in top["claim_text"]
    assert top["source"] is None
    assert top["score"] > 0


def test_graph_expansion_includes_related_node_claims(db: Session, user_id: int):
    project, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="IRIS", node_type="project"
    )
    tech, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="FastAPI", node_type="technology"
    )
    knowledge_service.create_claim(
        db, user_id=user_id, node=project, text="IRIS is the main project."
    )
    knowledge_service.create_claim(
        db, user_id=user_id, node=tech, text="FastAPI is an ASGI framework."
    )
    knowledge_service.upsert_relationship(
        db,
        user_id=user_id,
        source_node_id=project.id,
        target_node_id=tech.id,
        relationship_type="USES",
        confidence=0.9,
    )
    result = knowledge_retrieval.search(
        db, user_id=user_id, query="IRIS", principal="user", limit=10
    )
    node_names = {item["node_name"] for item in result["results"]}
    assert "FastAPI" in node_names
    assert any("graph" in item["signals"] for item in result["results"])


def test_permissions_filter_retrieval_results(db: Session, user_id: int):
    _node_claim(
        db, user_id, "IRIS", "project", "IRIS is built with Python.",
        verification_status=VerificationStatus.USER_STATED.value,
    )
    _node_claim(
        db, user_id, "Family", "person", "My sister is visiting in December.",
        verification_status=VerificationStatus.USER_STATED.value,
    )
    developer = knowledge_retrieval.search(
        db, user_id=user_id, query="visiting December", principal="coworker:developer"
    )
    assert all(item["node_type"] != "person" for item in developer["results"])
    owner = knowledge_retrieval.search(
        db, user_id=user_id, query="visiting December", principal="user"
    )
    assert any(item["node_type"] == "person" for item in owner["results"])


def test_temporal_as_of_returns_historical_claim(db: Session, user_id: int):
    old_time = utcnow() - timedelta(days=40)
    node, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="IRIS", node_type="project"
    )
    old, _ = knowledge_service.create_claim(
        db,
        user_id=user_id,
        node=node,
        text="IRIS uses PostgreSQL",
        observed_at=old_time,
        valid_from=old_time,
        verification_status=VerificationStatus.USER_STATED.value,
    )
    knowledge_service.create_claim(
        db,
        user_id=user_id,
        node=node,
        text="IRIS uses MySQL",
        verification_status=VerificationStatus.USER_STATED.value,
    )
    historical = knowledge_retrieval.search(
        db,
        user_id=user_id,
        query="IRIS database",
        principal="user",
        as_of=old_time + timedelta(days=1),
    )
    assert any(item["claim_id"] == old.id for item in historical["results"])
    current = knowledge_retrieval.search(
        db, user_id=user_id, query="IRIS database", principal="user"
    )
    assert all(item["claim_id"] != old.id for item in current["results"])


def test_context_is_bounded_and_preserves_provenance(db: Session, user_id: int):
    source = knowledge_service.register_source(
        db,
        user_id=user_id,
        source_type="conversation",
        source_ref="conversation:1:message:2",
        content="IRIS uses FastAPI.",
    )
    node, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="IRIS", node_type="project"
    )
    knowledge_service.create_claim(
        db,
        user_id=user_id,
        node=node,
        text="IRIS uses FastAPI.",
        verification_status=VerificationStatus.USER_STATED.value,
        source_id=source.id,
    )
    context = knowledge_retrieval.build_context(
        db, user_id=user_id, query="FastAPI", principal="user", budget_chars=500
    )
    assert len(context) <= 500
    assert "AUTHORISED KNOWLEDGE" in context
    assert "fact" in context
    assert "user_stated" in context
    assert "conversation:conversation:1:message:2" in context
