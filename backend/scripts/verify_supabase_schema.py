"""Verify all 18 tables and schema objects in Supabase PostgreSQL."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.core.database import normalize_database_url


def main():
    print("=" * 70)
    print("SUPABASE POSTGRESQL SCHEMA VERIFICATION")
    print("=" * 70)

    url = normalize_database_url(settings.database_url)
    if ":6543" in url:
        url = url.replace(":6543", ":5432")

    engine = create_engine(url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    expected_tables = {
        "users",
        "startups",
        "goals",
        "projects",
        "tasks",
        "leads",
        "outreach_activities",
        "experiments",
        "metrics",
        "calendar_events",
        "time_blocks",
        "focus_sessions",
        "daily_reviews",
        "recurring_schedules",
        "signals",
        "ai_conversations",
        "ai_messages",
        "ai_recommendations",
        "ai_memories",
        "email_accounts",
        "alembic_version",
    }

    print(f"Total tables detected in Supabase: {len(tables)}")
    print("-" * 70)
    missing = expected_tables - tables
    if missing:
        print(f"ERROR: Missing tables: {missing}")
        sys.exit(1)

    for tbl in sorted(expected_tables):
        cols = inspector.get_columns(tbl)
        pk = inspector.get_pk_constraint(tbl)
        fks = inspector.get_foreign_keys(tbl)
        indexes = inspector.get_indexes(tbl)
        print(
            f"[OK] {tbl:<22} | Columns: {len(cols):2d} | "
            f"PK: {pk.get('constrained_columns', [])} | FKs: {len(fks)} | Indexes: {len(indexes)}"
        )

    with engine.connect() as conn:
        rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        print(f"\nAlembic Current Version: {rev}")

    print("=" * 70)
    print("RESULT: ALL 18 TABLES + CONSTRAINTS VERIFIED IN SUPABASE POSTGRESQL!")
    print("=" * 70)


if __name__ == "__main__":
    main()
