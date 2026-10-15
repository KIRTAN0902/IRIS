"""Diary service -- notes, ideas, reflections, journaling CRUD and search."""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.diary_entry import DiaryEntry
from app.schemas.diary import DiaryEntryCreate, DiaryEntryUpdate


def list_diary_entries(
    db: Session,
    user_id: int,
    *,
    category: str | None = None,
    tag: str | None = None,
    search: str | None = None,
    is_pinned: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[DiaryEntry]:
    """Retrieve diary entries with optional category, tag, search, and pin filters."""
    q = db.query(DiaryEntry).filter(DiaryEntry.user_id == user_id)

    if category and category.upper() != "ALL":
        q = q.filter(DiaryEntry.category == category.upper())

    if is_pinned is not None:
        q = q.filter(DiaryEntry.is_pinned == is_pinned)

    if search and search.strip():
        term = f"%{search.strip()}%"
        q = q.filter(or_(DiaryEntry.title.ilike(term), DiaryEntry.content.ilike(term)))

    # Order pinned first, then newest updated_at/created_at
    q = q.order_by(DiaryEntry.is_pinned.desc(), DiaryEntry.updated_at.desc())

    entries = q.offset(offset).limit(limit).all()

    # Filter tag in python if requested (since tags is stored as JSON array)
    if tag and tag.strip():
        target = tag.strip().lower()
        entries = [e for e in entries if e.tags and any(t.lower() == target for t in e.tags)]

    return entries


def count_diary_entries(db: Session, user_id: int, *, category: str | None = None) -> int:
    q = db.query(DiaryEntry).filter(DiaryEntry.user_id == user_id)
    if category and category.upper() != "ALL":
        q = q.filter(DiaryEntry.category == category.upper())
    return q.count()


def get_diary_entry(db: Session, user_id: int, entry_id: int) -> DiaryEntry:
    entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id, DiaryEntry.user_id == user_id).first()
    if not entry:
        raise NotFoundError("Diary entry not found.", code="DIARY_ENTRY_NOT_FOUND")
    return entry


def create_diary_entry(db: Session, user_id: int, data: DiaryEntryCreate) -> DiaryEntry:
    entry_dict = data.model_dump()
    if entry_dict.get("category"):
        entry_dict["category"] = entry_dict["category"].upper()
    entry = DiaryEntry(user_id=user_id, **entry_dict)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def update_diary_entry(
    db: Session, user_id: int, entry_id: int, data: DiaryEntryUpdate
) -> DiaryEntry:
    entry = get_diary_entry(db, user_id, entry_id)
    updates = data.model_dump(exclude_unset=True)
    if "category" in updates and updates["category"]:
        updates["category"] = updates["category"].upper()

    for key, value in updates.items():
        setattr(entry, key, value)

    db.commit()
    db.refresh(entry)
    return entry


def delete_diary_entry(db: Session, user_id: int, entry_id: int) -> None:
    entry = get_diary_entry(db, user_id, entry_id)
    db.delete(entry)
    db.commit()


def get_diary_summary(db: Session, user_id: int) -> dict:
    entries = db.query(DiaryEntry).filter(DiaryEntry.user_id == user_id).all()
    categories = set()
    all_tags = set()
    for e in entries:
        if e.category:
            categories.add(e.category)
        if e.tags:
            for t in e.tags:
                all_tags.add(t)

    # Standard default categories if empty
    default_categories = ["NOTE", "IDEA", "REFLECTION", "JOURNAL", "MEETING", "LEARNING"]
    for cat in default_categories:
        categories.add(cat)

    return {
        "total": len(entries),
        "categories": sorted(list(categories)),
        "all_tags": sorted(list(all_tags)),
    }
