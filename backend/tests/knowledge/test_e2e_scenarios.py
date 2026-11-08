"""End-to-End Scenarios specified in IRIS Knowledge Directive Section 11.4.

Scenarios:
- Scenario A — Conversation capture
- Scenario B — Knowledge connection
- Scenario C — Updated information
- Scenario D — Inference
- Scenario E — Markdown conflict
- Scenario F — Access control
- Scenario G — Restart recovery
"""

from __future__ import annotations

from datetime import datetime, timedelta
import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.knowledge.jobs import claim_job, complete_job, drain_jobs, enqueue_job, recover_stale_jobs
from app.knowledge.markdown_sync import MarkdownConflictError, MarkdownSyncService
from app.knowledge.permissions import build_permission_context
from app.knowledge.pipeline import capture_conversation_turn, capture_text
from app.knowledge.retrieval import knowledge_retrieval
from app.knowledge.service import knowledge_service
from app.knowledge.storage import LocalVaultStorage
from app.knowledge.types import (
    AccessLevel,
    ClaimType,
    JobStatus,
    JobType,
    NodeType,
    Sensitivity,
    VerificationStatus,
    utcnow,
)
from app.models.ai_conversation import AIConversation, AIMessage
from app.models.enums import AIRole
from app.models.knowledge import KnowledgeClaim, KnowledgeJob, KnowledgeNode, KnowledgeSource


@pytest.fixture()
def vault_sync(tmp_path):
    storage = LocalVaultStorage(root=tmp_path / "e2e_vault")
    return MarkdownSyncService(storage=storage)


def test_scenario_a_conversation_capture(db: Session, user_id: int, vault_sync, monkeypatch):
    """Scenario A — Conversation capture.
    1. User provides durable project information.
    2. IRIS captures it automatically without interrupting chat.
    3. The source is registered with provenance.
    4. A knowledge claim is created.
    5. The Markdown note is updated.
    6. The claim becomes retrievable later.
    """
    from app.knowledge import markdown_sync as sync_module

    monkeypatch.setattr(sync_module, "markdown_sync", vault_sync)

    conv = AIConversation(user_id=user_id, title="Architecture Discussion")
    db.add(conv)
    db.flush()

    user_row = AIMessage(conversation_id=conv.id, role=AIRole.USER.value, content="Project Apollo uses FastAPI.")
    db.add(user_row)
    db.flush()

    user_msg = "Project Apollo uses PostgreSQL and FastAPI for the backend architecture."
    result = capture_conversation_turn(
        db,
        user_id=user_id,
        user_message=user_msg,
        assistant_message="Got it! Apollo is configured with PostgreSQL and FastAPI.",
        conversation_id=conv.id,
        message_id=user_row.id,
    )
    assert result is not None
    source_id = result["source_id"]
    job_id = result["job_id"]

    # Source provenance is registered
    source = db.query(KnowledgeSource).filter_by(id=source_id, user_id=user_id).first()
    assert source is not None
    assert source.conversation_id == conv.id
    assert source.message_id == user_row.id

    # Execute durable background processing
    drained = drain_jobs(db, user_id=user_id, limit=5)
    assert drained["processed"] >= 1

    # Verify claim was created
    claims = db.query(KnowledgeClaim).filter_by(user_id=user_id).all()
    assert len(claims) >= 1
    apollo_claim = next(c for c in claims if "Apollo" in c.claim_text or "apollo" in c.node.normalized_name)
    assert apollo_claim.claim_type in {ClaimType.FACT.value, ClaimType.DECISION.value}
    assert apollo_claim.source_id == source_id

    # Verify note in markdown vault
    note = vault_sync._note_for_node(db, user_id, apollo_claim.node_id)
    assert note is not None
    content = vault_sync.storage.get(note.storage_path)
    assert content is not None
    assert "Apollo" in content

    # Verify retrieval
    search_res = knowledge_retrieval.search(
        db,
        user_id=user_id,
        query="Apollo backend architecture",
        principal="iris_core",
    )
    assert search_res["count"] >= 1
    found = [r["claim_text"] for r in search_res["results"]]
    assert any("Apollo" in text or "FastAPI" in text for text in found)


def test_scenario_b_knowledge_connection(db: Session, user_id: int):
    """Scenario B — Knowledge connection.
    1. Two related project facts are captured.
    2. Entities are resolved.
    3. A relationship is created.
    4. The knowledge graph reflects the connection.
    5. Retrieval can discover the relationship.
    """
    node_proj, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="Project Hermes", node_type=NodeType.PROJECT.value
    )
    node_tech, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="PostgreSQL", node_type=NodeType.TECHNOLOGY.value
    )

    claim1, _ = knowledge_service.create_claim(
        db,
        user_id=user_id,
        node=node_proj,
        text="Project Hermes is an analytics platform.",
        claim_type=ClaimType.FACT.value,
        category="projects",
        verification_status=VerificationStatus.USER_STATED.value,
    )
    claim2, _ = knowledge_service.create_claim(
        db,
        user_id=user_id,
        node=node_tech,
        text="PostgreSQL 16 handles relational storage.",
        claim_type=ClaimType.FACT.value,
        category="learning",
        verification_status=VerificationStatus.USER_STATED.value,
    )

    # Create directed edge
    rel, created = knowledge_service.upsert_relationship(
        db,
        user_id=user_id,
        source_node_id=node_proj.id,
        target_node_id=node_tech.id,
        relationship_type="USES",
        confidence=0.9,
    )
    assert created is True

    # Graph traversal discovers the connection
    graph = knowledge_service.traverse(
        db, user_id=user_id, start_node_id=node_proj.id, depth=1
    )
    node_ids = {n.id for n in graph["nodes"]}
    assert node_proj.id in node_ids
    assert node_tech.id in node_ids
    assert any(e.relationship_type == "USES" for e in graph["relationships"])

    # Graph-aware hybrid retrieval surfaces related entity context
    search = knowledge_retrieval.search(
        db,
        user_id=user_id,
        query="Project Hermes",
        principal="iris_core",
    )
    texts = [r["claim_text"] for r in search["results"]]
    assert any("Project Hermes" in t for t in texts)


def test_scenario_c_updated_information(db: Session, user_id: int):
    """Scenario C — Updated information.
    1. An older claim exists.
    2. New evidence changes it.
    3. The old claim is preserved.
    4. The new claim is recorded.
    5. Current retrieval prioritises the current claim.
    6. Historical retrieval still finds the older state.
    """
    node, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="Deployment Architecture", node_type=NodeType.DECISION.value
    )

    # Older claim recorded at t0
    past = utcnow() - timedelta(days=30)
    old_claim, _ = knowledge_service.create_claim(
        db,
        user_id=user_id,
        node=node,
        text="IRIS uses architecture A for deployments.",
        claim_type=ClaimType.DECISION.value,
        category="decisions",
        verification_status=VerificationStatus.USER_STATED.value,
        valid_from=past,
    )

    # Superseding claim recorded today
    new_claim, _ = knowledge_service.create_claim(
        db,
        user_id=user_id,
        node=node,
        text="IRIS migrated to architecture B for deployments.",
        claim_type=ClaimType.DECISION.value,
        category="decisions",
        verification_status=VerificationStatus.USER_STATED.value,
    )

    knowledge_service.supersede_claim(
        db,
        user_id=user_id,
        old_claim_id=old_claim.id,
        new_claim_id=new_claim.id,
        reason="Architecture migration completed.",
    )

    assert new_claim.supersedes_claim_id == old_claim.id
    db.refresh(old_claim)
    assert old_claim.valid_until is not None  # Old claim validity expired
    assert old_claim.superseded_by_claim_id == new_claim.id

    # Current retrieval returns current state
    current_search = knowledge_retrieval.search(
        db,
        user_id=user_id,
        query="architecture deployments",
        include_history=False,
    )
    claim_texts = [r["claim_text"] for r in current_search["results"]]
    assert "IRIS migrated to architecture B for deployments." in claim_texts
    assert "IRIS uses architecture A for deployments." not in claim_texts

    # Historical retrieval with as_of finds older state
    historical_search = knowledge_retrieval.search(
        db,
        user_id=user_id,
        query="architecture deployments",
        as_of=past + timedelta(days=1),
    )
    hist_texts = [r["claim_text"] for r in historical_search["results"]]
    assert "IRIS uses architecture A for deployments." in hist_texts


def test_scenario_d_inference_handling(db: Session, user_id: int):
    """Scenario D — Inference.
    1. IRIS detects a potential pattern.
    2. Stores the result as an inference.
    3. Supporting evidence is retained.
    4. It is not presented as a verified fact.
    """
    node, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="Work Habits", node_type=NodeType.INSIGHT.value
    )

    inference_claim, _ = knowledge_service.create_claim(
        db,
        user_id=user_id,
        node=node,
        text="User seems most productive during early morning coding sessions.",
        claim_type=ClaimType.INFERENCE.value,
        category="insights",
        verification_status=VerificationStatus.INFERRED.value,
        confidence=0.48,
        evidence_text="Observed commit timestamps clustering between 6am and 9am across 3 weeks.",
        extraction_method="pattern_analysis",
    )

    assert inference_claim.claim_type == ClaimType.INFERENCE.value
    assert inference_claim.verification_status == VerificationStatus.INFERRED.value
    assert inference_claim.confidence <= 0.55

    # Check that evidence was persisted
    assert len(inference_claim.evidence) >= 1
    assert "commit timestamps" in inference_claim.evidence[0].evidence_text

    # Prompt context rendering clearly marks it as inference, never verified fact
    ctx = knowledge_retrieval.build_context(
        db,
        user_id=user_id,
        query="productive morning habits",
        principal="iris_core",
    )
    assert "[inference · inferred" in ctx
    assert "User seems most productive" in ctx


def test_scenario_e_markdown_conflict(db: Session, user_id: int, vault_sync):
    """Scenario E — Markdown conflict.
    1. A note is created and synced.
    2. An external edit occurs in storage with a different hash.
    3. A concurrent update attempts to write.
    4. The system detects the conflict, writes a conflict copy, and raises without overwriting.
    """
    node, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="Roadmap 2027", node_type=NodeType.PROJECT.value
    )
    knowledge_service.create_claim(
        db,
        user_id=user_id,
        node=node,
        text="Phase 1 launches in Q1.",
        category="projects",
    )
    note_info = vault_sync.sync_node(db, user_id=user_id, node_id=node.id)
    note_rec = vault_sync._note_for_node(db, user_id, node.id)
    assert note_rec is not None

    # Simulate an external user edit in the vault file
    initial_content = vault_sync.storage.get(note_info["path"])
    externally_edited = initial_content + "\n## Notes\n- User added manual roadmap notes.\n"
    vault_sync.storage.put(note_info["path"], externally_edited)

    # Attempting to update the note with an outdated hash raises MarkdownConflictError
    with pytest.raises(MarkdownConflictError) as exc_info:
        vault_sync.update_note(
            db,
            user_id=user_id,
            note_id=note_rec.id,
            content="Overwriting content from an old client session.",
            expected_hash=note_rec.content_hash,  # stale hash
        )

    # A conflict copy was safely created, and the user's edit was preserved
    conflict_path = exc_info.value.conflict_path
    assert conflict_path is not None
    assert vault_sync.storage.exists(conflict_path)
    assert "User added manual roadmap notes" in vault_sync.storage.get(note_info["path"])


def test_scenario_f_access_control(db: Session, user_id: int):
    """Scenario F — Access control.
    1. Restricted knowledge exists.
    2. An unauthorised coworker requests it.
    3. The service refuses to return the information.
    4. No restricted content is passed to an AI provider or coworker.
    """
    node_personal, _ = knowledge_service.resolve_node(
        db,
        user_id=user_id,
        name="Private Health Notes",
        node_type=NodeType.PERSON.value,
        sensitivity=Sensitivity.RESTRICTED.value,
        access_level=AccessLevel.RESTRICTED.value,
    )

    restricted_claim, _ = knowledge_service.create_claim(
        db,
        user_id=user_id,
        node=node_personal,
        text="Confidential personal medical treatment schedule.",
        claim_type=ClaimType.FACT.value,
        category="personal",
        sensitivity=Sensitivity.RESTRICTED.value,
        access_level=AccessLevel.RESTRICTED.value,
    )

    node_tech, _ = knowledge_service.resolve_node(
        db,
        user_id=user_id,
        name="IRIS Architecture",
        node_type=NodeType.PROJECT.value,
        sensitivity=Sensitivity.ORDINARY.value,
        access_level=AccessLevel.SHARED.value,
    )
    public_claim, _ = knowledge_service.create_claim(
        db,
        user_id=user_id,
        node=node_tech,
        text="IRIS uses FastAPI with SQLAlchemy.",
        claim_type=ClaimType.FACT.value,
        category="projects",
        sensitivity=Sensitivity.ORDINARY.value,
        access_level=AccessLevel.SHARED.value,
    )

    # Developer Coworker searches
    dev_results = knowledge_retrieval.search(
        db,
        user_id=user_id,
        query="medical treatment architecture",
        principal="coworker:developer",
    )
    dev_claim_ids = [r["claim_id"] for r in dev_results["results"]]
    assert restricted_claim.id not in dev_claim_ids
    assert public_claim.id in dev_claim_ids

    # Context construction for Developer coworker never leaks restricted text
    dev_context = knowledge_retrieval.build_context(
        db,
        user_id=user_id,
        query="medical treatment schedule",
        principal="coworker:developer",
    )
    assert "Confidential personal medical" not in dev_context


def test_scenario_g_restart_recovery(db: Session, user_id: int):
    """Scenario G — Restart recovery.
    1. A processing job is claimed by worker A.
    2. Worker crashes (lease expires).
    3. Restart recovery restores stale jobs safely without duplication.
    4. Worker B claims and finishes the job cleanly.
    """
    job = enqueue_job(
        db,
        user_id=user_id,
        job_type=JobType.EXTRACT_KNOWLEDGE.value,
        payload={"text": "Durable fact for restart recovery test.", "origin": "user"},
        idempotency_key="restart-test-job-001",
    )
    db.commit()

    # Worker A claims the job with a short lease
    claimed = claim_job(db, worker_id="worker-crash-A", lease_seconds=1, user_id=user_id)
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == JobStatus.RUNNING.value

    # Simulate worker crash and time passing beyond lease
    claimed.lease_expires_at = utcnow() - timedelta(seconds=10)
    db.commit()

    # Recovery process runs upon backend restart
    recovered_count = recover_stale_jobs(db)
    assert recovered_count >= 1

    db.refresh(job)
    assert job.status == JobStatus.QUEUED.value
    assert job.locked_at is None

    # Re-enqueuing with the same idempotency key does NOT create duplicates
    dup_job = enqueue_job(
        db,
        user_id=user_id,
        job_type=JobType.EXTRACT_KNOWLEDGE.value,
        payload={"text": "Durable fact for restart recovery test.", "origin": "user"},
        idempotency_key="restart-test-job-001",
    )
    assert dup_job.id == job.id

    # Worker B claims and completes it
    claimed_b = claim_job(db, worker_id="worker-live-B", lease_seconds=30, user_id=user_id)
    assert claimed_b is not None
    assert claimed_b.id == job.id

    complete_job(db, claimed_b, result={"status": "recovered_and_done"})
    db.refresh(job)
    assert job.status == JobStatus.SUCCEEDED.value
    assert job.result["status"] == "recovered_and_done"
