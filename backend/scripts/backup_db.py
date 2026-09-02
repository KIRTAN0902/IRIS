"""IRIS Database Backup Utility.

Creates an online, WAL-aware, consistent snapshot backup of the SQLite database
using Python's native sqlite3.backup() API.

Usage:
    python scripts/backup_db.py [optional_output_path]
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add backend root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.core.config import settings  # noqa: E402


def resolve_sqlite_path(db_url: str) -> Path | None:
    """Extract filesystem path from a sqlite URL."""
    if not db_url.startswith("sqlite"):
        return None
    if ":memory:" in db_url or db_url == "sqlite://":
        return None
    if db_url.startswith("sqlite:////"):
        return Path("/" + db_url[len("sqlite:////"):])
    elif db_url.startswith("sqlite:///"):
        raw_path = db_url[len("sqlite:///"):]
        p = Path(raw_path)
        if not p.is_absolute():
            p = BASE_DIR / p
        return p
    return None


def backup_database(destination: str | Path | None = None) -> Path:
    """Perform a safe, online backup of the SQLite database.

    Returns the path to the backup file.
    """
    db_path = resolve_sqlite_path(settings.database_url)
    if db_path is None:
        raise ValueError(f"Cannot backup non-file database URL: {settings.database_url}")

    if not db_path.exists():
        raise FileNotFoundError(f"Source database file not found at: {db_path}")

    if destination is None:
        backup_dir = db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        dest_path = backup_dir / f"iris_backup_{timestamp}.db"
    else:
        dest_path = Path(destination)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[IRIS BACKUP] Source: {db_path}")
    print(f"[IRIS BACKUP] Target: {dest_path}")

    # Use SQLite Online Backup API
    source_conn = sqlite3.connect(str(db_path))
    dest_conn = sqlite3.connect(str(dest_path))

    try:
        with dest_conn:
            source_conn.backup(dest_conn, pages=100, sleep=0.01)
        print("[IRIS BACKUP] Backup completed successfully.")
    finally:
        dest_conn.close()
        source_conn.close()

    # Integrity verification
    verify_conn = sqlite3.connect(str(dest_path))
    try:
        cursor = verify_conn.cursor()
        cursor.execute("PRAGMA quick_check")
        status = cursor.fetchone()
        if status and status[0] == "ok":
            cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
            count = cursor.fetchone()[0]
            print(f"[IRIS BACKUP] Integrity check: OK ({count} tables found in backup).")
        else:
            raise RuntimeError(f"Integrity check failed: {status}")
    finally:
        verify_conn.close()

    return dest_path


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        out = backup_database(target)
        print(f"[IRIS BACKUP] Output file: {out}")
        sys.exit(0)
    except Exception as e:
        print(f"[IRIS BACKUP ERROR] {e}", file=sys.stderr)
        sys.exit(1)
