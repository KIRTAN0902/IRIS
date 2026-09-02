"""Security primitives and the current-user dependency.

IRIS v1 is single-user: authentication is intentionally simple. The
``get_current_user`` dependency is the single seam where real authentication
(JWT/OAuth) will be introduced later -- routes never resolve users directly.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import NotFoundError
from app.models.user import User

DEFAULT_USER_EMAIL = "owner@iris.local"


def get_current_user(db: Session = None, email: str | None = None) -> User:
    """Resolve the acting user.

    v1: returns the default (single) user, creating it on first use.
    Future: replace with JWT/session-based resolution; call sites stay intact.
    """
    from app.core.database import SessionLocal  # local import to avoid cycles in tooling

    db = db or SessionLocal()
    target_email = email or DEFAULT_USER_EMAIL
    user = db.query(User).filter(User.email == target_email).first()
    if user is None:
        user = User(
            name="Kirtan",
            email=target_email,
            timezone=settings.default_timezone,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def require_user(db: Session) -> User:
    """Dependency-style variant used by routes (raises 404 if absent)."""
    user = db.query(User).filter(User.email == DEFAULT_USER_EMAIL).first()
    if user is None:
        raise NotFoundError("User not found. Run scripts/seed.py or restart the API.")
    return user


__all__ = ["get_current_user", "require_user", "DEFAULT_USER_EMAIL", "get_db"]
