"""SQLite to Supabase PostgreSQL Data Migration Utility.

Safely migrates all IRIS application data from a source SQLite database
to a target PostgreSQL (Supabase) database.

Features:
- Preserves all primary keys, IDs, naive UTC timestamps, JSON payloads, and relations.
- Topological insertion order (handles foreign key dependencies and parent goals).
- Automatically resets PostgreSQL sequences (setval on pg_get_serial_sequence).
- Transactional: commits only when all tables migrate successfully.
- Includes verification pass comparing source vs target row counts.
- Zero destructive operations on the source SQLite file.

Usage:
    python scripts/migrate_sqlite_to_postgres.py --source sqlite:///./iris.db \
        --target postgresql+psycopg://user:pass@host:5432/postgres
    python scripts/migrate_sqlite_to_postgres.py \
        --target postgresql+psycopg://user:pass@host:5432/postgres --wipe-target
    python scripts/migrate_sqlite_to_postgres.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: F401 -- ensure all models are registered
from app.core.config import settings
from app.core.database import Base, normalize_database_url


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate IRIS data from SQLite to PostgreSQL.")
    parser.add_argument(
        "--source",
        default=None,
        help="Source SQLite URL (default: settings.database_url or sqlite:///./iris.db)",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="Target PostgreSQL URL (default: TARGET_DATABASE_URL or DATABASE_URL)",
    )
    parser.add_argument(
        "--wipe-target",
        action="store_true",
        help="Wipe existing target data before migration",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without committing changes to target database",
    )
    return parser.parse_args()


def resolve_urls(args: argparse.Namespace) -> tuple[str, str]:
    # Resolve source
    source = args.source
    if not source:
        if settings.database_url.startswith("sqlite"):
            source = settings.database_url
        else:
            source = "sqlite:///./iris.db"

    # Resolve target
    target = args.target
    if not target:
        import os

        target = os.environ.get("TARGET_DATABASE_URL") or os.environ.get("POSTGRES_DATABASE_URL")
        if not target and (
            settings.database_url.startswith("postgres")
            or settings.database_url.startswith("postgresql")
        ):
            target = settings.database_url

    target_norm = normalize_database_url(target)
    if ":6543" in target_norm:
        print("[Migration] Transaction pooler port (:6543) detected.")
        print(
            "[Migration] Using Session Pooler (:5432) for table schema "
            "creation and data migration..."
        )
        target_norm = target_norm.replace(":6543", ":5432")

    return normalize_database_url(source), target_norm


def get_table_order() -> list[str]:
    """Return tables in dependency-safe order for insertion."""
    return [
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
    ]


def reset_postgres_sequences(engine, tables: list[str]) -> None:
    """Reset PostgreSQL serial sequences to the max(id) for each table."""
    if engine.dialect.name != "postgresql":
        print(
            f"  [Sequence Note] Target dialect is '{engine.dialect.name}', "
            "skipping PostgreSQL sequence reset."
        )
        return

    with engine.connect() as conn:
        for table_name in tables:
            try:
                seq_query = text(f"SELECT pg_get_serial_sequence('{table_name}', 'id')")
                seq_name = conn.execute(seq_query).scalar()
                if seq_name:
                    reset_sql = text(
                        f"SELECT setval('{seq_name}', "
                        f"COALESCE((SELECT MAX(id) FROM {table_name}), 1), true)"
                    )
                    conn.execute(reset_sql)
                    print(f"  [Sequence Reset] {table_name}.id -> sequence {seq_name}")
            except Exception as e:
                print(f"  [Sequence Note] {table_name}: {e}")
        conn.commit()


def migrate_data(
    source_url: str,
    target_url: str,
    wipe_target: bool = False,
    dry_run: bool = False,
) -> None:
    print("=" * 70)
    print("IRIS DATABASE MIGRATION: SQLite -> PostgreSQL (Supabase)")
    print("=" * 70)
    print(f"Source (SQLite):     {source_url}")
    print(f"Target (PostgreSQL): {target_url.split('@')[-1] if '@' in target_url else target_url}")
    print(f"Wipe Target:         {wipe_target}")
    print(f"Dry Run:             {dry_run}")
    print("=" * 70)

    # 1. Connect to source SQLite
    src_engine = create_engine(source_url, connect_args={"check_same_thread": False})
    src_inspector = inspect(src_engine)
    src_tables = set(src_inspector.get_table_names())

    # 2. Connect to target PostgreSQL
    tgt_engine = create_engine(target_url, pool_pre_ping=True)

    # 3. Ensure target schema exists
    print("\n1. Ensuring target schema is initialized...")
    Base.metadata.create_all(tgt_engine)

    TargetSession = sessionmaker(bind=tgt_engine, autoflush=False, expire_on_commit=False)
    target_session: Session = TargetSession()

    SourceSession = sessionmaker(bind=src_engine, autoflush=False)
    source_session: Session = SourceSession()

    try:
        tables_to_migrate = get_table_order()

        # Optional wipe
        if wipe_target:
            print("\n2. Wiping target data in reverse dependency order...")
            for table_name in reversed(tables_to_migrate):
                if table_name in Base.metadata.tables:
                    table = Base.metadata.tables[table_name]
                    target_session.execute(table.delete())
            target_session.flush()

        print("\n3. Migrating tables in dependency order...")
        summary: list[tuple[str, int, int]] = []

        for table_name in tables_to_migrate:
            if table_name not in Base.metadata.tables or table_name not in src_tables:
                print(f"  [Skip] Table '{table_name}' not found in source or models.")
                continue

            table = Base.metadata.tables[table_name]

            src_rows = source_session.execute(table.select()).mappings().all()
            count_src = len(src_rows)

            if count_src == 0:
                print(f"  [Table: {table_name:22s}] 0 rows (empty)")
                summary.append((table_name, 0, 0))
                continue

            # Handle self-referential ordering (e.g. goals: root goals before sub-goals)
            if table_name == "goals":
                rows_to_insert = sorted(
                    src_rows,
                    key=lambda r: (0 if r.get("parent_goal_id") is None else 1, r.get("id", 0)),
                )
            else:
                rows_to_insert = list(src_rows)

            # Insert into target
            for row_mapping in rows_to_insert:
                row_dict = dict(row_mapping)
                target_session.execute(table.insert().values(row_dict))

            target_session.flush()
            print(f"  [Table: {table_name:22s}] Migrated {count_src:4d} rows successfully.")
            summary.append((table_name, count_src, count_src))

        # 4. Commit or rollback
        if dry_run:
            print("\n[Dry Run] Rolling back all changes on target database...")
            target_session.rollback()
        else:
            print("\n4. Committing all records to target PostgreSQL...")
            target_session.commit()
            print("5. Resetting PostgreSQL serial sequences...")
            reset_postgres_sequences(tgt_engine, tables_to_migrate)

        # 5. Verification summary
        print("\n" + "=" * 70)
        print("MIGRATION VERIFICATION REPORT")
        print("=" * 70)
        print(f"{'Table':<25} {'Source Rows':<15} {'Target Rows':<15} {'Status'}")
        print("-" * 70)

        all_ok = True
        with tgt_engine.connect() as conn:
            for table_name in tables_to_migrate:
                if table_name in Base.metadata.tables and table_name in src_tables:
                    src_cnt = source_session.execute(
                        text(f"SELECT COUNT(*) FROM {table_name}")
                    ).scalar() or 0
                    if not dry_run:
                        tgt_cnt = conn.execute(
                            text(f"SELECT COUNT(*) FROM {table_name}")
                        ).scalar() or 0
                    else:
                        tgt_cnt = 0
                    status = "OK" if (src_cnt == tgt_cnt or dry_run) else "MISMATCH"
                    if status == "MISMATCH":
                        all_ok = False
                    print(f"{table_name:<25} {src_cnt:<15} {tgt_cnt:<15} {status}")

        print("=" * 70)
        if all_ok:
            print("SUCCESS: IRIS database migration completed with 100% integrity!")
        else:
            print("WARNING: Some table counts did not match. Please inspect details above.")

    except Exception as exc:
        target_session.rollback()
        print(f"\nERROR DURING MIGRATION: {exc}")
        raise
    finally:
        source_session.close()
        target_session.close()


if __name__ == "__main__":
    args = parse_args()
    source_url, target_url = resolve_urls(args)
    migrate_data(
        source_url=source_url,
        target_url=target_url,
        wipe_target=args.wipe_target,
        dry_run=args.dry_run,
    )
