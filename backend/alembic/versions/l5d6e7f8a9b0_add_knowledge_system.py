"""Add the IRIS Knowledge System.

Revision ID: l5d6e7f8a9b0
Revises: k4c5d6e7f8a9
Create Date: 2026-11-07 10:00:00.000000

Additive migration. Existing memory, conversation and coworker tables are not
modified. On PostgreSQL the migration enables the pgvector column when the
extension is available and adds defence-in-depth row level security policies.
On SQLite the portable JSON/Text representation is used and both steps are
skipped.
"""

from alembic import op
import sqlalchemy as sa

revision = "l5d6e7f8a9b0"
down_revision = "k4c5d6e7f8a9"
branch_labels = None
depends_on = None

KNOWLEDGE_TABLES = [
    "knowledge_nodes",
    "knowledge_sources",
    "knowledge_claims",
    "knowledge_evidence",
    "knowledge_relationships",
    "knowledge_versions",
    "knowledge_permissions",
    "knowledge_embeddings",
    "knowledge_jobs",
    "knowledge_reviews",
    "knowledge_notes",
]


def upgrade() -> None:
    op.create_table(
        "knowledge_nodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_type", sa.String(40), nullable=False),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("sensitivity", sa.String(20), nullable=False, server_default="ordinary"),
        sa.Column("access_level", sa.String(20), nullable=False, server_default="shared"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "node_type", "normalized_name", name="uq_knowledge_node_identity"),
    )
    op.create_index("ix_knowledge_nodes_user_id", "knowledge_nodes", ["user_id"])
    op.create_index("ix_knowledge_nodes_node_type", "knowledge_nodes", ["node_type"])
    op.create_index("ix_knowledge_nodes_normalized_name", "knowledge_nodes", ["normalized_name"])
    op.create_index("ix_knowledge_nodes_status", "knowledge_nodes", ["status"])
    op.create_index("ix_knowledge_nodes_sensitivity", "knowledge_nodes", ["sensitivity"])
    op.create_index("ix_knowledge_nodes_access_level", "knowledge_nodes", ["access_level"])
    op.create_index("ix_knowledge_nodes_user_type", "knowledge_nodes", ["user_id", "node_type"])
    op.create_index("ix_knowledge_nodes_user_status", "knowledge_nodes", ["user_id", "status"])

    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("source_ref", sa.String(512), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("ai_conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("ai_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("sensitivity", sa.String(20), nullable=False, server_default="ordinary"),
        sa.Column("access_level", sa.String(20), nullable=False, server_default="shared"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "source_type", "source_ref", "content_hash", name="uq_knowledge_source_identity"
        ),
    )
    op.create_index("ix_knowledge_sources_user_id", "knowledge_sources", ["user_id"])
    op.create_index("ix_knowledge_sources_source_type", "knowledge_sources", ["source_type"])
    op.create_index("ix_knowledge_sources_content_hash", "knowledge_sources", ["content_hash"])
    op.create_index("ix_knowledge_sources_user_type", "knowledge_sources", ["user_id", "source_type"])

    op.create_table(
        "knowledge_claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("node_id", sa.String(36), sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("claim_type", sa.String(30), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("verification_status", sa.String(30), nullable=False, server_default="unverified"),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("knowledge_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_until", sa.DateTime(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("supersedes_claim_id", sa.String(36), sa.ForeignKey("knowledge_claims.id", ondelete="SET NULL"), nullable=True),
        sa.Column("superseded_by_claim_id", sa.String(36), sa.ForeignKey("knowledge_claims.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sensitivity", sa.String(20), nullable=False, server_default="ordinary"),
        sa.Column("access_level", sa.String(20), nullable=False, server_default="shared"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_knowledge_claims_user_id", "knowledge_claims", ["user_id"])
    op.create_index("ix_knowledge_claims_node_id", "knowledge_claims", ["node_id"])
    op.create_index("ix_knowledge_claims_fingerprint", "knowledge_claims", ["fingerprint"])
    op.create_index("ix_knowledge_claims_claim_type", "knowledge_claims", ["claim_type"])
    op.create_index("ix_knowledge_claims_category", "knowledge_claims", ["category"])
    op.create_index("ix_knowledge_claims_verification_status", "knowledge_claims", ["verification_status"])
    op.create_index("ix_knowledge_claims_source_id", "knowledge_claims", ["source_id"])
    op.create_index("ix_knowledge_claims_sensitivity", "knowledge_claims", ["sensitivity"])
    op.create_index("ix_knowledge_claims_access_level", "knowledge_claims", ["access_level"])
    op.create_index("ix_knowledge_claims_user_node", "knowledge_claims", ["user_id", "node_id"])
    op.create_index(
        "ix_knowledge_claims_user_current", "knowledge_claims", ["user_id", "valid_until", "archived_at"]
    )
    op.create_index(
        "ix_knowledge_claims_user_fingerprint", "knowledge_claims", ["user_id", "fingerprint"]
    )

    op.create_table(
        "knowledge_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("knowledge_claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("knowledge_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("context_excerpt", sa.Text(), nullable=True),
        sa.Column("extraction_method", sa.String(50), nullable=False, server_default="heuristic"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_knowledge_evidence_user_id", "knowledge_evidence", ["user_id"])
    op.create_index("ix_knowledge_evidence_claim_id", "knowledge_evidence", ["claim_id"])

    op.create_table(
        "knowledge_relationships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_node_id", sa.String(36), sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_node_id", sa.String(36), sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_type", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("knowledge_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_until", sa.DateTime(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "source_node_id",
            "target_node_id",
            "relationship_type",
            "valid_from",
            name="uq_knowledge_relationship_edge",
        ),
    )
    op.create_index("ix_knowledge_relationships_user_id", "knowledge_relationships", ["user_id"])
    op.create_index("ix_knowledge_relationships_source_node_id", "knowledge_relationships", ["source_node_id"])
    op.create_index("ix_knowledge_relationships_target_node_id", "knowledge_relationships", ["target_node_id"])
    op.create_index("ix_knowledge_relationships_relationship_type", "knowledge_relationships", ["relationship_type"])
    op.create_index(
        "ix_knowledge_relationships_user_source", "knowledge_relationships", ["user_id", "source_node_id"]
    )
    op.create_index(
        "ix_knowledge_relationships_user_target", "knowledge_relationships", ["user_id", "target_node_id"]
    )

    op.create_table(
        "knowledge_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("change_type", sa.String(30), nullable=False, server_default="update"),
        sa.Column("change_reason", sa.String(500), nullable=True),
        sa.Column("actor", sa.String(80), nullable=False, server_default="iris"),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_knowledge_versions_user_id", "knowledge_versions", ["user_id"])
    op.create_index("ix_knowledge_versions_entity_type", "knowledge_versions", ["entity_type"])
    op.create_index("ix_knowledge_versions_entity_id", "knowledge_versions", ["entity_id"])
    op.create_index(
        "ix_knowledge_versions_entity", "knowledge_versions", ["user_id", "entity_type", "entity_id"]
    )

    op.create_table(
        "knowledge_permissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("knowledge_type", sa.String(30), nullable=False, server_default="global"),
        sa.Column("knowledge_id", sa.String(36), nullable=True),
        sa.Column("principal_type", sa.String(30), nullable=False, server_default="coworker"),
        sa.Column("principal_id", sa.String(120), nullable=False, server_default="*"),
        sa.Column("access_level", sa.String(20), nullable=False, server_default="personal"),
        sa.Column("can_read", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("can_write", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_knowledge_permissions_user_id", "knowledge_permissions", ["user_id"])
    op.create_index(
        "ix_knowledge_permissions_principal", "knowledge_permissions", ["user_id", "principal_type", "principal_id"]
    )
    op.create_index(
        "ix_knowledge_permissions_item", "knowledge_permissions", ["user_id", "knowledge_type", "knowledge_id"]
    )

    op.create_table(
        "knowledge_embeddings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("knowledge_type", sa.String(30), nullable=False),
        sa.Column("knowledge_id", sa.String(36), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector_json", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "knowledge_type", "knowledge_id", "model", name="uq_knowledge_embedding_item"
        ),
    )
    op.create_index("ix_knowledge_embeddings_user_id", "knowledge_embeddings", ["user_id"])
    op.create_index("ix_knowledge_embeddings_knowledge_type", "knowledge_embeddings", ["knowledge_type"])
    op.create_index("ix_knowledge_embeddings_knowledge_id", "knowledge_embeddings", ["knowledge_id"])
    op.create_index("ix_knowledge_embeddings_content_hash", "knowledge_embeddings", ["content_hash"])
    op.create_index(
        "ix_knowledge_embeddings_lookup", "knowledge_embeddings", ["user_id", "knowledge_type", "model"]
    )

    op.create_table(
        "knowledge_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("available_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("locked_by", sa.String(120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_knowledge_job_idempotency"),
    )
    op.create_index("ix_knowledge_jobs_user_id", "knowledge_jobs", ["user_id"])
    op.create_index("ix_knowledge_jobs_job_type", "knowledge_jobs", ["job_type"])
    op.create_index("ix_knowledge_jobs_status", "knowledge_jobs", ["status"])
    op.create_index("ix_knowledge_jobs_priority", "knowledge_jobs", ["priority"])
    op.create_index("ix_knowledge_jobs_available_at", "knowledge_jobs", ["available_at"])
    op.create_index("ix_knowledge_jobs_lease_expires_at", "knowledge_jobs", ["lease_expires_at"])
    op.create_index(
        "ix_knowledge_jobs_claim", "knowledge_jobs", ["status", "available_at", "priority"]
    )

    op.create_table(
        "knowledge_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("review_type", sa.String(40), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_knowledge_reviews_user_id", "knowledge_reviews", ["user_id"])
    op.create_index("ix_knowledge_reviews_review_type", "knowledge_reviews", ["review_type"])
    op.create_index("ix_knowledge_reviews_target_id", "knowledge_reviews", ["target_id"])
    op.create_index("ix_knowledge_reviews_status", "knowledge_reviews", ["status"])

    op.create_table(
        "knowledge_notes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(36), sa.ForeignKey("knowledge_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("note_type", sa.String(40), nullable=False, server_default="note"),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("db_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("storage_version", sa.Integer(), nullable=True),
        sa.Column("last_source_version", sa.Integer(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("sync_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("conflict_path", sa.String(512), nullable=True),
        sa.Column("sensitivity", sa.String(20), nullable=False, server_default="ordinary"),
        sa.Column("access_level", sa.String(20), nullable=False, server_default="shared"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "storage_path", name="uq_knowledge_note_path"),
    )
    op.create_index("ix_knowledge_notes_user_id", "knowledge_notes", ["user_id"])
    op.create_index("ix_knowledge_notes_node_id", "knowledge_notes", ["node_id"])
    op.create_index("ix_knowledge_notes_note_type", "knowledge_notes", ["note_type"])
    op.create_index("ix_knowledge_notes_sync_status", "knowledge_notes", ["sync_status"])
    op.create_index("ix_knowledge_notes_user_status", "knowledge_notes", ["user_id", "sync_status"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # pgvector is optional. Never fail the migration because the extension is
        # unavailable on the project plan.
        try:
            op.execute("CREATE EXTENSION IF NOT EXISTS vector")
            dims = 256
            op.execute(
                f"ALTER TABLE knowledge_embeddings ADD COLUMN IF NOT EXISTS embedding vector({dims})"
            )
            op.execute(
                "CREATE INDEX IF NOT EXISTS ix_knowledge_embeddings_vector "
                "ON knowledge_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
            )
        except Exception:  # noqa: BLE001 - extension is optional
            pass

        # Defence in depth. The application service layer is the primary
        # boundary; these policies protect direct SQL access when a per-request
        # identity is set with SET LOCAL iris.user_id = '<id>'. The table owner
        # and Supabase service role bypass RLS by design (single-user runtime).
        for table in KNOWLEDGE_TABLES:
            try:
                op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
                op.execute(
                    f"CREATE POLICY {table}_owner_isolation ON {table} "
                    "USING (user_id = nullif(current_setting('iris.user_id', true), '')::int) "
                    "WITH CHECK (user_id = nullif(current_setting('iris.user_id', true), '')::int)"
                )
            except Exception:  # noqa: BLE001 - policy may already exist
                pass


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in KNOWLEDGE_TABLES:
            try:
                op.execute(f"DROP POLICY IF EXISTS {table}_owner_isolation ON {table}")
            except Exception:  # noqa: BLE001
                pass
    for table in reversed(KNOWLEDGE_TABLES):
        op.drop_table(table)
