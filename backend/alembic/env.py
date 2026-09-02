"""Alembic environment.

Reads DATABASE_URL from app settings (single source of truth) and enables
batch mode so SQLite ALTER TABLE operations work.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.database import Base, is_sqlite_url, normalize_database_url
import app.models  # noqa: F401 -- register all models on Base.metadata

config = context.config

# Check for explicit migration connection URL or fallback to settings.database_url
raw_migration_url = (
    os.environ.get("MIGRATION_DATABASE_URL")
    or os.environ.get("DIRECT_DATABASE_URL")
    or os.environ.get("DATABASE_URL_UNPOOLED")
    or settings.database_url
)

db_url = normalize_database_url(raw_migration_url)

# Supabase Transaction Pooler (port 6543) does NOT support transactional DDL / Alembic locks.
# Automatically switch to Session Pooler (port 5432) on the same host if port 6543 was passed.
if ":6543" in db_url:
    print("[Alembic] Transaction pooler port (:6543) detected.")
    print("[Alembic] Automatically switching migration connection to Session Pooler (:5432)...")
    db_url = db_url.replace(":6543", ":5432")

config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
is_sqlite = is_sqlite_url(db_url)


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=is_sqlite,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=is_sqlite,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
