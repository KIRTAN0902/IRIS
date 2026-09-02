"""SQLAlchemy engine/session setup and the declarative base.

Portability notes (SQLite v1 -> PostgreSQL later):

* The database is addressed exclusively through ``settings.database_url``.
  No module in the codebase hard-codes a path or dialect-specific type.
* All enum-like columns are stored as plain strings validated by Python enums,
  which works identically on SQLite and PostgreSQL.
* SQLite needs ``foreign_keys=ON`` per connection to enforce FK integrity.
* Datetimes are stored as **naive UTC** everywhere. Use :func:`app.utils.datetime
  .utcnow` to create them, and convert to the user's timezone only at the
  presentation/analytics boundary.
"""

import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _is_sqlite() -> bool:
    return settings.database_url.startswith("sqlite")


def _ensure_sqlite_dir() -> None:
    """Ensure parent directory for SQLite database file exists."""
    if not _is_sqlite():
        return
    url = settings.database_url
    if ":memory:" in url or url == "sqlite://":
        return
    # Strip sqlite:/// or sqlite:////
    if url.startswith("sqlite:////"):
        file_path = "/" + url[len("sqlite:////"):]
    elif url.startswith("sqlite:///"):
        file_path = url[len("sqlite:///"):]
    else:
        return
    parent = Path(file_path).parent
    if parent and not parent.exists():
        os.makedirs(parent, exist_ok=True)


_ensure_sqlite_dir()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _is_sqlite() else {},
    pool_pre_ping=True,
)

if _is_sqlite():

    @event.listens_for(Engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
