"""Markdown vault synchronisation.

PostgreSQL is authoritative for structured knowledge; the Markdown vault is a
durable, Obsidian-compatible projection that the user can also edit. This module
owns every transition between the two:

* database -> Markdown generation (per node and for indexes),
* Markdown -> database import (user notes and edited bullets),
* optimistic concurrency and conflict copies,
* create / read / rename / move / archive / restore / delete,
* bounded reconciliation and index rebuilding.

The storage backend is the existing Supabase Storage bucket in production and a
local directory in development/tests. It is never assumed to be writable on a
serverless filesystem.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.knowledge import markdown
from app.knowledge.storage import VaultStorage, get_vault_storage
from app.knowledge.types import (
    CATEGORY_FOLDERS,
    CATEGORY_LABELS,
    ClaimType,
    NODE_TYPE_CATEGORY,
    VerificationStatus,
    hash_bytes,
    slugify,
    utcnow,
)
from app.models.knowledge import (
    KnowledgeClaim,
    KnowledgeNode,
    KnowledgeNote,
    KnowledgeRelationship,
    KnowledgeSource,
    KnowledgeVersion,
)

logger = get_logger("iris.knowledge.markdown_sync")

ARCHIVE_PREFIX = "99-Archive"
USER_NOTE_FOLDER = "00-Index/Notes"
INDEX_PATH = "00-Index/Knowledge Index.md"

_CLAIM_LINE = re.compile(
    r"^-\s+\*\*(?P<kind>[A-Za-z]+)\*\*\s*\((?P<meta>[^)]*)\)\s*:\s*(?P<text>.+)$"
)


class MarkdownSyncError(RuntimeError):
    pass


class MarkdownConflictError(MarkdownSyncError):
    def __init__(self, message: str, *, conflict_path: str, current_content: str) -> None:
        super().__init__(message)
        self.conflict_path = conflict_path
        self.current_content = current_content


def _hash(content: str) -> str:
    return hash_bytes((content or "").encode("utf-8"))


def _unique_path(storage: VaultStorage, path: str) -> str:
    if not storage.exists(path):
        return path
    stem, _, suffix = path.rpartition(".")
    for index in range(1, 50):
        candidate = f"{stem}-{index}.{suffix}"
        if not storage.exists(candidate):
            return candidate
    raise MarkdownSyncError("Could not allocate a unique vault path.")


class MarkdownSyncService:
    def __init__(self, storage: VaultStorage | None = None) -> None:
        self._storage = storage

    @property
    def storage(self) -> VaultStorage:
        if self._storage is None:
            self._storage = get_vault_storage()
        return self._storage

    # --- note records --------------------------------------------------------

    def _note_for_node(
        self, db: Session, user_id: int, node_id: str
    ) -> KnowledgeNote | None:
        return (
            db.query(KnowledgeNote)
            .filter(KnowledgeNote.user_id == user_id, KnowledgeNote.node_id == node_id)
            .first()
        )

    def get_note(
        self, db: Session, user_id: int, note_id: str
    ) -> KnowledgeNote | None:
        return (
            db.query(KnowledgeNote)
            .filter(KnowledgeNote.id == note_id, KnowledgeNote.user_id == user_id)
            .first()
        )

    def list_notes(
        self,
        db: Session,
        user_id: int,
        *,
        note_type: str | None = None,
        query: str | None = None,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[KnowledgeNote]:
        q = db.query(KnowledgeNote).filter(KnowledgeNote.user_id == user_id)
        if note_type:
            q = q.filter(KnowledgeNote.note_type == note_type)
        if not include_archived:
            q = q.filter(KnowledgeNote.archived_at.is_(None))
        if query:
            q = q.filter(KnowledgeNote.title.ilike(f"%{query.strip()}%"))
        return (
            q.order_by(KnowledgeNote.updated_at.desc())
            .limit(min(max(limit, 1), 250))
            .offset(offset)
            .all()
        )

    def _record_version(
        self,
        db: Session,
        user_id: int,
        note: KnowledgeNote,
        change_type: str,
        *,
        actor: str = "iris",
        reason: str | None = None,
    ) -> None:
        latest = (
            db.query(func.max(KnowledgeVersion.version_number))
            .filter(
                KnowledgeVersion.user_id == user_id,
                KnowledgeVersion.entity_type == "note",
                KnowledgeVersion.entity_id == note.id,
            )
            .scalar()
        )
        db.add(
            KnowledgeVersion(
                user_id=user_id,
                entity_type="note",
                entity_id=note.id,
                version_number=int(latest or 0) + 1,
                change_type=change_type,
                change_reason=reason,
                actor=actor,
                snapshot={
                    "id": note.id,
                    "title": note.title,
                    "path": note.storage_path,
                    "content_hash": note.content_hash,
                    "sync_status": note.sync_status,
                    "archived_at": note.archived_at.isoformat() if note.archived_at else None,
                },
            )
        )

    # --- database -> Markdown ------------------------------------------------

    def sync_node(
        self, db: Session, *, user_id: int, node_id: str | None
    ) -> dict[str, Any]:
        if not node_id:
            return {"skipped": "missing_node_id"}
        node = (
            db.query(KnowledgeNode)
            .filter(KnowledgeNode.id == node_id, KnowledgeNode.user_id == user_id)
            .first()
        )
        if node is None:
            return {"skipped": "node_not_found"}
        if node.status == "deleted":
            return {"skipped": "node_deleted"}

        claims = (
            db.query(KnowledgeClaim)
            .filter(KnowledgeClaim.user_id == user_id, KnowledgeClaim.node_id == node.id)
            .order_by(KnowledgeClaim.recorded_at.asc())
            .limit(250)
            .all()
        )
        relationships = (
            db.query(KnowledgeRelationship)
            .filter(
                KnowledgeRelationship.user_id == user_id,
                KnowledgeRelationship.valid_until.is_(None),
                (
                    (KnowledgeRelationship.source_node_id == node.id)
                    | (KnowledgeRelationship.target_node_id == node.id)
                ),
            )
            .limit(120)
            .all()
        )
        other_ids = {
            edge.target_node_id if edge.source_node_id == node.id else edge.source_node_id
            for edge in relationships
        }
        node_names = {node.id: node.canonical_name}
        if other_ids:
            for other in (
                db.query(KnowledgeNode)
                .filter(KnowledgeNode.user_id == user_id, KnowledgeNode.id.in_(other_ids))
                .all()
            ):
                node_names[other.id] = other.canonical_name
        source_ids = {claim.source_id for claim in claims if claim.source_id}
        sources = {}
        if source_ids:
            sources = {
                source.id: source
                for source in db.query(KnowledgeSource)
                .filter(KnowledgeSource.user_id == user_id, KnowledgeSource.id.in_(source_ids))
                .all()
            }

        rendered = markdown.render_node_note(
            node=node,
            claims=claims,
            relationships=relationships,
            node_names=node_names,
            sources=sources,
            include_history=True,
        )
        note = self._note_for_node(db, user_id, node.id)
        if note and note.storage_path != rendered.path:
            rendered.path = note.storage_path if note.storage_path else rendered.path
        if note is None:
            rendered.path = _unique_path(self.storage, rendered.path)
        else:
            rendered.path = note.storage_path or _unique_path(self.storage, rendered.path)

        remote = self.storage.get(rendered.path)
        merged = rendered.content
        conflict_path: str | None = None
        if remote is not None:
            remote_hash = _hash(remote)
            if note is not None and note.last_synced_at and remote_hash != note.content_hash:
                # External edit: keep a copy of the user's version, merge their
                # Notes section into the regenerated note, and flag the record.
                conflict_path = self._write_conflict_copy(rendered.path, remote)
            merged = markdown.merge_user_section(remote, rendered.content) if remote else rendered.content

        merged_hash = _hash(merged)
        self.storage.put(rendered.path, merged)
        latest_version = (
            db.query(func.max(KnowledgeVersion.version_number))
            .filter(
                KnowledgeVersion.user_id == user_id,
                KnowledgeVersion.entity_type == "node",
                KnowledgeVersion.entity_id == node.id,
            )
            .scalar()
        )
        if note is None:
            note = KnowledgeNote(
                user_id=user_id,
                node_id=node.id,
                title=node.canonical_name[:255],
                note_type=node.node_type,
                storage_path=rendered.path,
                content_hash=merged_hash,
                db_version=1,
                last_source_version=int(latest_version or 1),
                last_synced_at=utcnow(),
                sync_status="conflict" if conflict_path else "synced",
                conflict_path=conflict_path,
                sensitivity=node.sensitivity,
                access_level=node.access_level,
                metadata_json={"storage_hash": merged_hash, "generated": True},
            )
            db.add(note)
            db.flush()
            self._record_version(db, user_id, note, "create")
        else:
            note.title = node.canonical_name[:255]
            note.note_type = node.node_type
            note.content_hash = merged_hash
            note.db_version = (note.db_version or 0) + 1
            note.last_source_version = int(latest_version or 1)
            note.last_synced_at = utcnow()
            note.sync_status = "conflict" if conflict_path else "synced"
            note.conflict_path = conflict_path or note.conflict_path
            note.sensitivity = node.sensitivity
            note.access_level = node.access_level
            note.metadata_json = {
                **dict(note.metadata_json or {}),
                "storage_hash": merged_hash,
                "generated": True,
            }
            self._record_version(db, user_id, note, "sync")
        db.flush()
        return {
            "node_id": node.id,
            "note_id": note.id,
            "path": rendered.path,
            "content_hash": merged_hash,
            "sync_status": note.sync_status,
            "conflict_path": conflict_path,
        }

    def _write_conflict_copy(self, path: str, content: str) -> str:
        stem = path[:-3] if path.endswith(".md") else path
        stamp = utcnow().strftime("%Y%m%d-%H%M%S")
        conflict_path = f"{stem}.conflict-{stamp}.md"
        self.storage.put(conflict_path, content)
        return conflict_path

    # --- user note CRUD ------------------------------------------------------

    def create_note(
        self,
        db: Session,
        *,
        user_id: int,
        title: str,
        content: str = "",
        category: str = "general",
        tags: Iterable[str] = (),
        node_id: str | None = None,
    ) -> KnowledgeNote:
        title = (title or "Untitled note").strip()[:255]
        folder = CATEGORY_FOLDERS.get(category, USER_NOTE_FOLDER)
        path = _unique_path(self.storage, f"{folder}/{slugify(title)}.md")
        now = utcnow()
        metadata = {
            "id": slugify(title),
            "title": title,
            "type": "note",
            "status": "active",
            "category": category,
            "tags": sorted({str(tag) for tag in tags if str(tag).strip()}),
            "created_at": now.date().isoformat(),
            "updated_at": now.date().isoformat(),
        }
        body = (content or "").strip()
        if not body.startswith("#"):
            body = f"# {title}\n\n{body}".rstrip() + "\n"
        rendered = markdown.render_frontmatter(metadata) + "\n" + body
        self.storage.put(path, rendered)
        note = KnowledgeNote(
            user_id=user_id,
            node_id=node_id,
            title=title,
            note_type="note",
            storage_path=path,
            content_hash=_hash(rendered),
            db_version=1,
            last_synced_at=now,
            sync_status="synced",
            metadata_json={"storage_hash": _hash(rendered), "generated": False},
        )
        db.add(note)
        db.flush()
        self._record_version(db, user_id, note, "create", actor="user")
        return note

    def read_note(
        self, db: Session, *, user_id: int, note_id: str
    ) -> dict[str, Any] | None:
        note = self.get_note(db, user_id, note_id)
        if note is None:
            return None
        content = self.storage.get(note.storage_path)
        if content is None and note.node_id:
            # A generated note vanished; regenerate it from authoritative data.
            self.sync_node(db, user_id=user_id, node_id=note.node_id)
            content = self.storage.get(note.storage_path)
        return {
            "note": note,
            "content": content or "",
            "content_hash": _hash(content or ""),
            "missing": content is None,
        }

    def update_note(
        self,
        db: Session,
        *,
        user_id: int,
        note_id: str,
        content: str,
        expected_hash: str | None = None,
        actor: str = "user",
    ) -> KnowledgeNote:
        note = self.get_note(db, user_id, note_id)
        if note is None:
            raise MarkdownSyncError("Note not found.")
        remote = self.storage.get(note.storage_path)
        current_hash = _hash(remote or "")
        if expected_hash and remote is not None and current_hash != expected_hash:
            conflict_path = self._write_conflict_copy(note.storage_path, remote)
            note.conflict_path = conflict_path
            note.sync_status = "conflict"
            db.flush()
            raise MarkdownConflictError(
                "The note changed in the vault after it was loaded.",
                conflict_path=conflict_path,
                current_content=remote,
            )
        if remote is None and note.node_id:
            self.sync_node(db, user_id=user_id, node_id=note.node_id)
            remote = self.storage.get(note.storage_path) or ""
        self.storage.put(note.storage_path, content)
        new_hash = _hash(content)
        note.content_hash = new_hash
        note.db_version = (note.db_version or 0) + 1
        note.last_synced_at = utcnow()
        note.sync_status = "synced"
        note.metadata_json = {
            **dict(note.metadata_json or {}),
            "storage_hash": new_hash,
            "generated": bool(note.node_id),
        }
        db.flush()
        self._record_version(db, user_id, note, "update", actor=actor)
        return note

    def rename_note(
        self,
        db: Session,
        *,
        user_id: int,
        note_id: str,
        title: str | None = None,
        category: str | None = None,
    ) -> KnowledgeNote:
        note = self.get_note(db, user_id, note_id)
        if note is None:
            raise MarkdownSyncError("Note not found.")
        content = self.storage.get(note.storage_path)
        if content is None:
            raise MarkdownSyncError("Note content is missing from storage.")
        new_title = (title or note.title).strip()[:255]
        folder = CATEGORY_FOLDERS.get(
            (category or dict(note.metadata_json or {}).get("category") or "general"),
            USER_NOTE_FOLDER,
        )
        new_path = _unique_path(self.storage, f"{folder}/{slugify(new_title)}.md")
        self.storage.put(new_path, content)
        if new_path != note.storage_path:
            self.storage.delete(note.storage_path)
        note.title = new_title
        note.storage_path = new_path
        note.metadata_json = {**dict(note.metadata_json or {}), "category": category or dict(note.metadata_json or {}).get("category", "general")}
        db.flush()
        self._record_version(db, user_id, note, "rename", actor="user")
        return note

    def archive_note(
        self, db: Session, *, user_id: int, note_id: str
    ) -> KnowledgeNote:
        note = self.get_note(db, user_id, note_id)
        if note is None:
            raise MarkdownSyncError("Note not found.")
        if note.archived_at is None:
            content = self.storage.get(note.storage_path)
            archive_path = f"{ARCHIVE_PREFIX}/{note.storage_path}"
            if content is not None:
                self.storage.put(archive_path, content)
                self.storage.delete(note.storage_path)
            note.metadata_json = {
                **dict(note.metadata_json or {}),
                "archived_from": note.storage_path,
            }
            note.storage_path = archive_path
            note.archived_at = utcnow()
            note.sync_status = "archived"
            db.flush()
            self._record_version(db, user_id, note, "archive", actor="user")
        return note

    def restore_note(
        self, db: Session, *, user_id: int, note_id: str
    ) -> KnowledgeNote:
        note = self.get_note(db, user_id, note_id)
        if note is None:
            raise MarkdownSyncError("Note not found.")
        if note.archived_at is not None:
            original = dict(note.metadata_json or {}).get("archived_from")
            content = self.storage.get(note.storage_path)
            target = original or note.storage_path.replace(f"{ARCHIVE_PREFIX}/", "", 1)
            if content is not None:
                self.storage.put(target, content)
                if target != note.storage_path:
                    self.storage.delete(note.storage_path)
            note.storage_path = target
            note.archived_at = None
            note.sync_status = "synced"
            db.flush()
            self._record_version(db, user_id, note, "restore", actor="user")
        return note

    def delete_note(self, db: Session, *, user_id: int, note_id: str) -> bool:
        note = self.get_note(db, user_id, note_id)
        if note is None:
            return False
        if note.node_id and note.archived_at is None:
            # Generated notes are projections; deleting them from the vault is
            # represented as an archive so the next sync cannot resurrect a
            # deleted user-visible note unexpectedly.
            self.archive_note(db, user_id=user_id, note_id=note_id)
            return True
        self._record_version(db, user_id, note, "delete", actor="user")
        self.storage.delete(note.storage_path)
        if note.conflict_path:
            self.storage.delete(note.conflict_path)
        db.delete(note)
        db.flush()
        return True

    # --- Markdown -> database ------------------------------------------------

    def import_markdown(
        self,
        db: Session,
        *,
        user_id: int,
        path: str,
        content: str | None = None,
        actor: str = "user",
    ) -> dict[str, Any]:
        safe_path = (path or "").replace("\\", "/").lstrip("/")
        if not safe_path:
            raise MarkdownSyncError("A vault path is required.")
        text = content if content is not None else self.storage.get(safe_path)
        if text is None:
            raise MarkdownSyncError("Markdown content was not found.")
        parsed = markdown.parse_frontmatter(text)
        title = str(parsed.frontmatter.get("title") or "").strip()
        if not title:
            heading = re.search(r"^#\s+(.+)$", parsed.body, re.MULTILINE)
            title = heading.group(1).strip() if heading else safe_path.rsplit("/", 1)[-1][:-3]
        frontmatter_id = str(parsed.frontmatter.get("id") or "").strip()

        note = (
            db.query(KnowledgeNote)
            .filter(KnowledgeNote.user_id == user_id, KnowledgeNote.storage_path == safe_path)
            .first()
        )
        if note and note.content_hash == _hash(text):
            return {"path": safe_path, "note_id": note.id, "changed": False, "imported_claims": 0}

        node = None
        if frontmatter_id:
            node = (
                db.query(KnowledgeNode)
                .filter(KnowledgeNode.id == frontmatter_id, KnowledgeNode.user_id == user_id)
                .first()
            )
        if node is None and title:
            node = (
                db.query(KnowledgeNode)
                .filter(
                    KnowledgeNode.user_id == user_id,
                    KnowledgeNode.canonical_name == title,
                    KnowledgeNode.status == "active",
                )
                .first()
            )
        if node and not node.description:
            body = parsed.body.strip()
            heading_removed = re.sub(r"^#\s+.+$", "", body, count=1, flags=re.MULTILINE).strip()
            if heading_removed:
                node.description = heading_removed[:2000]

        imported_claims = 0
        if node is not None:
            imported_claims = self._import_claim_bullets(
                db, user_id=user_id, node=node, body=parsed.body
            )
        note_type = str(parsed.frontmatter.get("type") or ("note" if node is None else node.node_type))
        now = utcnow()
        if note is None:
            note = KnowledgeNote(
                user_id=user_id,
                node_id=node.id if node else None,
                title=title[:255],
                note_type=note_type,
                storage_path=safe_path,
                content_hash=_hash(text),
                db_version=1,
                last_synced_at=now,
                sync_status="synced",
                metadata_json={"storage_hash": _hash(text), "generated": False, "imported": True},
            )
            db.add(note)
            db.flush()
            self._record_version(db, user_id, note, "import", actor=actor)
        else:
            note.title = title[:255]
            note.note_type = note_type
            note.node_id = node.id if node else note.node_id
            note.content_hash = _hash(text)
            note.db_version = (note.db_version or 0) + 1
            note.last_synced_at = now
            note.sync_status = "synced"
            note.metadata_json = {
                **dict(note.metadata_json or {}),
                "storage_hash": _hash(text),
                "imported": True,
            }
            db.flush()
            self._record_version(db, user_id, note, "import", actor=actor)
        db.flush()
        return {
            "path": safe_path,
            "note_id": note.id,
            "node_id": node.id if node else None,
            "title": note.title,
            "changed": True,
            "imported_claims": imported_claims,
        }

    def _import_claim_bullets(
        self, db: Session, *, user_id: int, node: KnowledgeNode, body: str
    ) -> int:
        imported = 0
        in_knowledge = False
        for line in (body or "").splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                in_knowledge = stripped[3:].strip().lower() == "knowledge"
                continue
            if not in_knowledge:
                continue
            match = _CLAIM_LINE.match(stripped)
            if not match:
                continue
            text = match.group("text").strip()
            if not text:
                continue
            claim_type = match.group("kind").strip().lower()
            if claim_type not in {item.value for item in ClaimType}:
                claim_type = ClaimType.FACT.value
            meta = match.group("meta")
            status = meta.split("·", 1)[0].strip().replace(" ", "_") or VerificationStatus.UNVERIFIED.value
            if status not in {item.value for item in VerificationStatus}:
                status = VerificationStatus.USER_STATED.value
            from app.knowledge.service import knowledge_service

            _, created = knowledge_service.create_claim(
                db,
                user_id=user_id,
                node=node,
                text=text,
                claim_type=claim_type,
                category=NODE_TYPE_CATEGORY.get(node.node_type, "general"),
                confidence=0.7,
                verification_status=status,
                extraction_method="markdown_import",
                evidence_text=text,
            )
            imported += int(created)
            if imported >= 40:
                break
        return imported

    # --- reconciliation and indexes -----------------------------------------

    def reconcile(self, db: Session, *, user_id: int, limit: int = 200) -> dict[str, Any]:
        """Bounded two-way reconciliation. Safe to run repeatedly."""
        notes = self.list_notes(db, user_id, include_archived=True, limit=min(limit, 250))
        regenerated = 0
        imported = 0
        missing = 0
        for note in notes:
            if note.archived_at is not None:
                continue
            if note.node_id:
                if note.sync_status in {"pending", "failed", "conflict"} or not self.storage.exists(note.storage_path):
                    self.sync_node(db, user_id=user_id, node_id=note.node_id)
                    regenerated += 1
            elif not self.storage.exists(note.storage_path):
                missing += 1

        tracked = {note.storage_path for note in notes}
        candidates: list[str] = []
        for folder in set(CATEGORY_FOLDERS.values()) | {USER_NOTE_FOLDER}:
            candidates.extend(self.storage.list(folder, limit=100))
        for path in dict.fromkeys(candidates):
            if path in tracked or path.startswith(ARCHIVE_PREFIX):
                continue
            if len(tracked) >= limit:
                break
            content = self.storage.get(path)
            if content is None:
                continue
            self.import_markdown(db, user_id=user_id, path=path, content=content)
            imported += 1

        index = self.rebuild_index(db, user_id=user_id)
        return {
            "notes_checked": len(notes),
            "regenerated": regenerated,
            "imported": imported,
            "missing_user_notes": missing,
            "index_path": index.get("path"),
        }

    def rebuild_index(self, db: Session, *, user_id: int) -> dict[str, Any]:
        nodes = (
            db.query(KnowledgeNode)
            .filter(KnowledgeNode.user_id == user_id, KnowledgeNode.status == "active")
            .order_by(KnowledgeNode.node_type.asc(), KnowledgeNode.canonical_name.asc())
            .limit(500)
            .all()
        )
        sections: dict[str, list[str]] = {}
        for node in nodes:
            category = NODE_TYPE_CATEGORY.get(node.node_type, "general")
            folder = CATEGORY_FOLDERS.get(category, "00-Index")
            label = f"{folder} · {CATEGORY_LABELS.get(category, category.title())}"
            sections.setdefault(label, []).append(node.canonical_name)
        rendered = markdown.render_index_note(
            title="Knowledge Index",
            path=INDEX_PATH,
            sections=sections,
            description=(
                "Generated by IRIS. Structured data is authoritative; notes are a durable "
                "human-readable projection and may be edited in Obsidian."
            ),
        )
        existing = self.storage.get(INDEX_PATH)
        if existing:
            rendered_content = markdown.merge_user_section(existing, rendered.content)
        else:
            rendered_content = rendered.content
        self.storage.put(INDEX_PATH, rendered_content)
        note = (
            db.query(KnowledgeNote)
            .filter(KnowledgeNote.user_id == user_id, KnowledgeNote.storage_path == INDEX_PATH)
            .first()
        )
        now = utcnow()
        if note is None:
            note = KnowledgeNote(
                user_id=user_id,
                node_id=None,
                title="Knowledge Index",
                note_type="index",
                storage_path=INDEX_PATH,
                content_hash=_hash(rendered_content),
                db_version=1,
                last_synced_at=now,
                sync_status="synced",
                metadata_json={"storage_hash": _hash(rendered_content), "generated": True},
            )
            db.add(note)
            db.flush()
        else:
            note.content_hash = _hash(rendered_content)
            note.db_version = (note.db_version or 0) + 1
            note.last_synced_at = now
            note.sync_status = "synced"
            note.metadata_json = {**dict(note.metadata_json or {}), "storage_hash": _hash(rendered_content)}
            db.flush()
        return {"path": INDEX_PATH, "nodes": len(nodes), "note_id": note.id}


markdown_sync = MarkdownSyncService()
