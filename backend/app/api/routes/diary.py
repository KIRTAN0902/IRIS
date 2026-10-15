"""Diary API endpoints for notes, ideas, reflections, and journaling."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.diary import DiaryEntryCreate, DiaryEntryOut, DiaryEntryUpdate
from app.services import diary_service

router = APIRouter(prefix="/diary", tags=["diary"])


@router.get("/entries", response_model=list[DiaryEntryOut])
def list_entries(
    category: str | None = Query(None, description="Filter by category (e.g. NOTE, IDEA, REFLECTION)"),
    tag: str | None = Query(None, description="Filter by tag"),
    search: str | None = Query(None, description="Search keyword in title or content"),
    is_pinned: bool | None = Query(None, description="Filter by pinned status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    entries = diary_service.list_diary_entries(
        db,
        user.id,
        category=category,
        tag=tag,
        search=search,
        is_pinned=is_pinned,
        limit=limit,
        offset=offset,
    )
    return [DiaryEntryOut.model_validate(e) for e in entries]


@router.get("/summary")
def get_summary(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return diary_service.get_diary_summary(db, user.id)


@router.post("/entries", response_model=DiaryEntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(
    data: DiaryEntryCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    entry = diary_service.create_diary_entry(db, user.id, data)
    return DiaryEntryOut.model_validate(entry)


@router.get("/entries/{entry_id}", response_model=DiaryEntryOut)
def get_entry(
    entry_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    entry = diary_service.get_diary_entry(db, user.id, entry_id)
    return DiaryEntryOut.model_validate(entry)


@router.patch("/entries/{entry_id}", response_model=DiaryEntryOut)
def update_entry(
    entry_id: int,
    data: DiaryEntryUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    entry = diary_service.update_diary_entry(db, user.id, entry_id, data)
    return DiaryEntryOut.model_validate(entry)


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    entry_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    diary_service.delete_entry = diary_service.delete_diary_entry(db, user.id, entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
