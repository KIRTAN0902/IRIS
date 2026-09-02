# IRIS — Production Migration Guide: SQLite to Supabase PostgreSQL

This document outlines the architecture, configuration, data migration, and deployment procedures for running IRIS on **Supabase PostgreSQL** and deploying via **Render** or **Coolify**.

---

## 1. Target Production Architecture

```text
       React / Vite SPA
              │ (HTTPS / REST)
              ▼
       FastAPI Backend (Render / Container)
              │
              │  SQLAlchemy 2.0 + psycopg 3
              │  (Connection Pool: size=5, max_overflow=10, pre_ping=True)
              ▼
       Supabase Session Pooler (Supavisor :5432)
              │
              ▼
       Supabase Managed PostgreSQL
```

---

## 2. Supabase Connection Strategy

Supabase offers three connection URIs in **Project Settings → Database → Connection String**:

| Connection Mode | Port | Supported Features | Use Case for IRIS |
|---|---|---|---|
| **Session Pooler (Supavisor)** *(Recommended)* | `5432` | IPv4 & IPv6, Alembic Migrations, Prepared Statements, Persistent Sessions | **Production Backend on Render / Coolify** |
| **Direct Connection** | `5432` | Full PostgreSQL features, requires IPv6 network | Local dev with IPv6 or VPC peering |
| **Transaction Pooler** | `6543` | Ephemeral serverless connections, no session state | Serverless Edge functions only (NOT recommended for FastAPI) |

### Recommended Connection String Format:
```dotenv
DATABASE_URL=postgresql+psycopg://postgres.[PROJECT_REF]:[YOUR_PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres
```
*Note: IRIS automatically normalizes `postgres://` and `postgresql://` to `postgresql+psycopg://` at runtime.*

---

## 3. Step-by-Step Migration Guide

### Step A: Create Supabase Project
1. Log into [supabase.com](https://supabase.com) and click **New Project**.
2. Name your project (e.g. `iris-db`), select your nearest region (e.g. `ap-south-1` / Mumbai or `us-east-1`), and set a strong database password.
3. Once provisioned, go to **Settings → Database → Connection String → URI** and select **Session** mode (`port: 5432`). Copy the URI.

### Step B: Apply Schema Migrations
From your terminal in `C:\kirtan\IRIS\backend`:
```powershell
# Set your Supabase connection string
$env:DATABASE_URL="postgresql+psycopg://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres"

# Apply all Alembic migrations to create the clean PostgreSQL schema
alembic upgrade head
```

### Step C: Migrate SQLite Data to Supabase PostgreSQL
Run the built-in migration script to transfer all existing tasks, goals, CRM leads, and user profile data:
```powershell
python scripts/migrate_sqlite_to_postgres.py `
  --source sqlite:///./iris.db `
  --target "postgresql+psycopg://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres" `
  --wipe-target
```
This utility:
- Preserves all explicit IDs, foreign-key relationships, and timestamps.
- Automatically resets PostgreSQL sequences (`pg_get_serial_sequence`) so future inserts increment without collision.
- Performs an automated verification check comparing source vs target row counts.

---

## 4. Deploying Backend to Render

### 1. Create Web Service for FastAPI Backend
1. In Render Dashboard, click **New + → Web Service**.
2. Connect your Git repository: `https://github.com/KIRTAN0902/IRIS`.
3. Configure settings:
   - **Name**: `iris-backend`
   - **Root Directory**: `backend`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers --forwarded-allow-ips "*"`
   - **Pre-Deploy Command**: `alembic upgrade head`

4. Add **Environment Variables** in Render:
   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | `postgresql+psycopg://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres` |
   | `ENVIRONMENT` | `production` |
   | `DEFAULT_TIMEZONE` | `Asia/Kolkata` |
   | `LOG_LEVEL` | `INFO` |
   | `SECRET_KEY` | *(Generate a 32+ character random secret)* |
   | `AI_PROVIDER` | `omniroute` *(or `gemini`)* |
   | `OMNIROUTE_BASE_URL` | `http://localhost:20128/v1` *(or your hosted OmniRoute gateway)* |
   | `OMNIROUTE_API_KEY` | *(Your OmniRoute API key)* |
   | `CORS_ORIGINS` | `["https://iris-frontend.onrender.com"]` *(Your frontend URL)* |

### 2. Deploy Frontend (Static Site)
1. In Render Dashboard, click **New + → Static Site**.
2. Configure settings:
   - **Name**: `iris-frontend`
   - **Root Directory**: `frontend`
   - **Build Command**: `npm install && npm run build`
   - **Publish Directory**: `dist`
   - **Rewrites / Redirects**: `/*` → `/index.html` (Rewrite, Status: 200)
3. Add **Environment Variable**:
   - `VITE_API_URL`: `https://iris-backend.onrender.com/api`

---

## 5. Backup & Disaster Recovery Strategy

### Automated Backups (Supabase Native)
- Supabase automatically takes daily backups of your PostgreSQL database (retained for 7 days on Free tier, up to 30 days on Pro tier with Point-in-Time Recovery).
- In case of accidental corruption, restore directly from the Supabase dashboard (**Settings → Database → Backups**).

### On-Demand Manual Logical Backup (`pg_dump`)
To take an immediate point-in-time snapshot before major updates:
```bash
# Export schema + data
pg_dump "postgresql://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres" \
  -F c -b -v -f "iris_backup_$(date +%Y%m%d_%H%M%S).dump"
```

### Restore from Dump
```bash
pg_restore -d "postgresql://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres" \
  -v --clean --if-exists "iris_backup_20260902.dump"
```

---

## 6. Verification Checklist

- [x] SQLAlchemy uses `psycopg 3` driver (`postgresql+psycopg://`).
- [x] Dialect-aware connection pooling configured (`pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`).
- [x] Alembic migrations verified against fresh PostgreSQL schema.
- [x] Cross-dialect boolean `server_default=sa.text('true')` active.
- [x] Data migration script resets PostgreSQL auto-increment sequences.
- [x] SQLite fallback preserved for ultra-fast local testing (`pytest`).
- [x] All 144 unit and integration tests pass without error.
