"""SQLAlchemy engine/session setup and the declarative base.

Supports both Supabase PostgreSQL (production/staging) and SQLite (local testing/dev).
- Database connection string is fully environment-driven via ``settings.database_url``.
- Automatically normalizes postgres:// and postgresql:// to postgresql+psycopg://.
- Configures sensible connection pooling for PostgreSQL (Supabase).
- Sets SQLite PRAGMAs and threading connect_args ONLY when SQLite is in use.
"""

import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def normalize_database_url(url: str) -> str:
    """Normalize database URL to use psycopg 3 driver for PostgreSQL."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def is_sqlite_url(url: str) -> bool:
    """Check if the provided database URL is SQLite."""
    return url.startswith("sqlite")


def is_serverless_or_transaction_pooler(url: str) -> bool:
    """Detect if running in serverless (Vercel/Lambda) or using transaction pooler (port 6543)."""
    return bool(
        os.environ.get("VERCEL")
        or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
        or os.environ.get("SERVERLESS") == "true"
        or ":6543" in url
    )


def _ensure_sqlite_dir(url: str) -> None:
    """Ensure parent directory for SQLite database file exists."""
    if not is_sqlite_url(url):
        return
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


resolved_db_url = normalize_database_url(settings.database_url)
_is_sqlite = is_sqlite_url(resolved_db_url)

if _is_sqlite:
    _ensure_sqlite_dir(resolved_db_url)
    engine_kwargs: dict[str, Any] = {
        "connect_args": {"check_same_thread": False},
        "pool_pre_ping": True,
    }
elif is_serverless_or_transaction_pooler(resolved_db_url):
    # Vercel Serverless / Supabase Transaction Pooler (:6543) -> NullPool
    # Ephemeral serverless lambdas must not maintain idle connection pools.
    from sqlalchemy.pool import NullPool

    engine_kwargs = {
        "poolclass": NullPool,
        "pool_pre_ping": True,
    }
else:
    # Production / Long-running Session Pooler (:5432)
    engine_kwargs = {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    }

engine = create_engine(resolved_db_url, **engine_kwargs)

if _is_sqlite:
    @event.listens_for(Engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):  # noqa: ANN001
        # Apply SQLite PRAGMAs only for sqlite3 connections
        if dbapi_connection.__class__.__module__.startswith("sqlite3"):
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
