"""Shared route dependencies."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user


def current_user(db: Session = Depends(get_db)):
    """Resolve the acting user. v1: the single default user."""
    return get_current_user(db)


deps = {"db": Depends(get_db)}
