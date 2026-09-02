"""Non-destructive PostgreSQL / Supabase Connectivity Verification Script.

Tests:
1. DNS resolution of Supabase host.
2. TCP socket connection to Transaction Pooler (6543) and Session Pooler (5432).
3. SQLAlchemy + psycopg 3 engine connection.
4. Reads PostgreSQL version and current database name via `SELECT version()`.
5. Masks all passwords and sensitive tokens in output.
6. ZERO DDL, ZERO table creation, ZERO queries against application tables.
"""

from __future__ import annotations

import os
import re
import socket
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.core.database import normalize_database_url


def mask_url(url: str) -> str:
    """Mask password in connection URL for safe logging."""
    if not url:
        return "<not-set>"
    return re.sub(r":([^@/]+)@", r":*****@", url)


def test_dns(host: str) -> bool:
    print(f"\n1. Testing DNS resolution for host '{host}'...")
    try:
        ip_addresses = socket.gethostbyname_ex(host)[2]
        print(f"   [DNS OK] Resolved to {ip_addresses}")
        return True
    except Exception as exc:
        print(f"   [DNS FAILED] Could not resolve host '{host}': {exc}")
        return False


def test_socket(host: str, port: int) -> bool:
    print(f"\n2. Testing TCP connection to {host}:{port}...")
    try:
        sock = socket.create_connection((host, port), timeout=8.0)
        sock.close()
        print(f"   [TCP OK] Connected to port {port}")
        return True
    except Exception as exc:
        print(f"   [TCP FAILED] Connection to {host}:{port} failed: {exc}")
        return False


def test_sqlalchemy_connection(url: str, label: str) -> bool:
    masked = mask_url(url)
    print(f"\n3. Testing SQLAlchemy connection ({label})...")
    print(f"   Target: {masked}")

    if (
        "[YOUR_SUPABASE_PASSWORD]" in url
        or "INSERT_YOUR_PASSWORD" in url
        or "YOUR_PASSWORD" in url
    ):
        print(f"   [ABORTED] Placeholder password detected in {label}.")
        print("   Please replace '[YOUR_SUPABASE_PASSWORD]' in backend/.env with your password.")
        return False

    normalized = normalize_database_url(url)
    try:
        # Create lightweight engine with NullPool
        from sqlalchemy.pool import NullPool

        engine = create_engine(normalized, poolclass=NullPool, pool_pre_ping=True)
        with engine.connect() as conn:
            version_res = conn.execute(text("SELECT version()")).scalar()
            db_res = conn.execute(text("SELECT current_database()")).scalar()
            ver_short = version_res.split(",")[0] if version_res else "unknown"
            print("   [SQLAlchemy OK] Connected successfully!")
            print(f"   [Database] {db_res}")
            print(f"   [PostgreSQL Version] {ver_short}")
        return True
    except Exception as exc:
        err_str = str(exc)
        # Mask any leaked credential in error string
        err_masked = re.sub(r":([^@/]+)@", r":*****@", err_str)
        print(f"   [SQLAlchemy FAILED] {err_masked}")
        return False


def extract_host(url: str) -> str:
    """Extract hostname safely from connection string."""
    if "@" in url:
        after_at = url.split("@", 1)[1]
        host_port = after_at.split("/", 1)[0]
        return host_port.split(":", 1)[0]
    return "aws-0-ap-southeast-1.pooler.supabase.com"


def main() -> None:
    print("=" * 70)
    print("IRIS -- SUPABASE POSTGRESQL CONNECTIVITY TEST (NON-DESTRUCTIVE)")
    print("=" * 70)

    # 1. Resolve URLs
    app_db_url = os.environ.get("DATABASE_URL") or settings.database_url
    mig_db_url = (
        os.environ.get("MIGRATION_DATABASE_URL")
        or os.environ.get("DIRECT_DATABASE_URL")
        or app_db_url.replace(":6543", ":5432")
    )

    print(f"App DATABASE_URL:       {mask_url(app_db_url)}")
    print(f"MIGRATION_DATABASE_URL: {mask_url(mig_db_url)}")

    host = extract_host(app_db_url)

    # 2. DNS Test
    dns_ok = test_dns(host)
    if not dns_ok:
        print("\nRESULT: FAILED (DNS resolution error)")
        sys.exit(1)

    # 3. Port Tests
    sock_6543_ok = test_socket(host, 6543)
    sock_5432_ok = test_socket(host, 5432)

    # 4. SQLAlchemy Connection Tests
    app_ok = test_sqlalchemy_connection(
        app_db_url, "DATABASE_URL (Port 6543 - Transaction Pooler)"
    )
    mig_ok = test_sqlalchemy_connection(
        mig_db_url, "MIGRATION_DATABASE_URL (Port 5432 - Session Pooler)"
    )

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"DNS Resolution:                         {'PASS' if dns_ok else 'FAIL'}")
    print(f"TCP Port 6543 (Transaction Pooler):     {'PASS' if sock_6543_ok else 'FAIL'}")
    print(f"TCP Port 5432 (Session Pooler):         {'PASS' if sock_5432_ok else 'FAIL'}")
    print(f"SQLAlchemy App Connection (:6543):      {'PASS' if app_ok else 'FAIL / PLACEHOLDER'}")
    print(f"SQLAlchemy Migration Connection (:5432): {'PASS' if mig_ok else 'FAIL / PLACEHOLDER'}")
    print("=" * 70)

    if app_ok and mig_ok:
        print("RESULT: PASS — PostgreSQL connection verified with 100% success!")
        sys.exit(0)
    else:
        print(
            "RESULT: PENDING PASSWORD CONFIGURATION — "
            "Enter your Supabase password in backend/.env to complete test."
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
