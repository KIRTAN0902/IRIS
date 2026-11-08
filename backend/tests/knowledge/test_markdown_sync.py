from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.knowledge.markdown_sync import (
    MarkdownConflictError,
    MarkdownSyncError,
    MarkdownSyncService,
)
from app.knowledge.service import knowledge_service
from app.knowledge.storage import LocalVaultStorage
from app.knowledge.types import VerificationStatus


@pytest.fixture()
def sync(tmp_path):
    return MarkdownSyncService(LocalVaultStorage(root=tmp_path / "vault"))


def test_sync_node_writes_obsidian_note_and_index(db: Session, user_id: int, sync):
    node, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="IRIS Project", node_type="project", description="Personal OS."
    )
    knowledge_service.create_claim(
        db,
        user_id=user_id,
        node=node,
        text="IRIS uses FastAPI.",
        verification_status=VerificationStatus.USER_STATED.value,
    )
    result = sync.sync_node(db, user_id=user_id, node_id=node.id)
    assert result["sync_status"] == "synced"
    content = sync.storage.get(result["path"])
    assert content is not None
    assert "# IRIS Project" in content
    assert "IRIS uses FastAPI." in content
    assert "user stated" in content
    assert result["path"].startswith("02-Projects/")

    index = sync.rebuild_index(db, user_id=user_id)
    assert sync.storage.exists(index["path"])
    assert "[[IRIS Project]]" in sync.storage.get(index["path"])


def test_external_edit_creates_conflict_copy_and_preserves_notes(db: Session, user_id: int, sync):
    node, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="Client App", node_type="project"
    )
    first = sync.sync_node(db, user_id=user_id, node_id=node.id)
    path = first["path"]
    external = sync.storage.get(path) + "\n## Notes\n\nMy personal annotation.\n"
    sync.storage.put(path, external)

    knowledge_service.create_claim(
        db, user_id=user_id, node=node, text="The client app targets Android."
    )
    second = sync.sync_node(db, user_id=user_id, node_id=node.id)
    assert second["sync_status"] == "conflict"
    assert second["conflict_path"]
    assert sync.storage.exists(second["conflict_path"])
    merged = sync.storage.get(path)
    assert "My personal annotation." in merged
    assert "targets Android" in merged


def test_user_note_crud_and_optimistic_conflict(db: Session, user_id: int, sync):
    note = sync.create_note(
        db,
        user_id=user_id,
        title="Reading list",
        content="Atomic Habits",
        category="learning",
        tags=["books"],
    )
    detail = sync.read_note(db, user_id=user_id, note_id=note.id)
    assert detail is not None
    assert "Atomic Habits" in detail["content"]
    first_hash = detail["content_hash"]

    sync.update_note(
        db,
        user_id=user_id,
        note_id=note.id,
        content=detail["content"] + "\nDeep Work\n",
        expected_hash=first_hash,
    )
    with pytest.raises(MarkdownConflictError) as exc:
        sync.update_note(
            db,
            user_id=user_id,
            note_id=note.id,
            content="stale overwrite",
            expected_hash=first_hash,
        )
    assert exc.value.conflict_path
    assert sync.storage.exists(exc.value.conflict_path)


def test_note_archive_restore_and_delete(db: Session, user_id: int, sync):
    note = sync.create_note(db, user_id=user_id, title="Scratch", content="text")
    original = note.storage_path
    archived = sync.archive_note(db, user_id=user_id, note_id=note.id)
    assert archived.archived_at is not None
    assert archived.storage_path.startswith("99-Archive/")
    restored = sync.restore_note(db, user_id=user_id, note_id=note.id)
    assert restored.storage_path == original
    assert sync.delete_note(db, user_id=user_id, note_id=note.id) is True
    assert sync.get_note(db, user_id, note.id) is None


def test_import_markdown_creates_claims_and_note_record(db: Session, user_id: int, sync):
    node, _ = knowledge_service.resolve_node(
        db, user_id=user_id, name="Knowledge Import", node_type="project"
    )
    path = "02-Projects/knowledge-import.md"
    content = (
        "---\n"
        f'id: "{node.id}"\n'
        'title: "Knowledge Import"\n'
        "type: project\n"
        "---\n\n"
        "# Knowledge Import\n\n"
        "## Knowledge\n\n"
        "- **Fact** (user stated): The import works.\n"
        "- **Decision** (verified): We keep PostgreSQL.\n"
    )
    sync.storage.put(path, content)
    result = sync.import_markdown(db, user_id=user_id, path=path)
    assert result["node_id"] == node.id
    assert result["imported_claims"] == 2
    claims = knowledge_service.list_claims(db, user_id, node_id=node.id, principal="user")
    texts = {claim.claim_text for claim in claims}
    assert "The import works." in texts
    assert "We keep PostgreSQL." in texts


def test_reconcile_imports_untracked_notes(db: Session, user_id: int, sync):
    sync.storage.put(
        "00-Index/Notes/loose.md",
        "---\ntitle: \"Loose note\"\ntype: note\n---\n\n# Loose note\n\nHello.\n",
    )
    result = sync.reconcile(db, user_id=user_id)
    assert result["imported"] >= 1
    notes = sync.list_notes(db, user_id)
    assert any(note.title == "Loose note" for note in notes)


def test_missing_note_raises(db: Session, user_id: int, sync):
    with pytest.raises(MarkdownSyncError):
        sync.update_note(db, user_id=user_id, note_id="does-not-exist", content="x")
