# IRIS — Existing Vercel Deployment, Supabase Database & Implementation Compatibility Audit

**Audit Date:** November 1, 2026  
**Auditor:** Antigravity Autonomous Pair Programmer  
**Current Codebase Branch / Commit:** `main` (`ec72418`)  
**Deployment Target:** Vercel Hobby Tier (`sin1` Singapore Region)  
**Database Target:** Supabase PostgreSQL 17.6 (`aws-0-ap-southeast-1.pooler.supabase.com`)  
**Scope:** Milestones A–E Implementation vs Existing Production Deployment  

---

## 1. Executive Summary

A comprehensive compatibility audit was conducted on the IRIS repository to determine whether the latest implementation (spanning Milestones A through E) can safely replace the current production Vercel deployment without data loss, service interruption, or breaking existing functionality.

### Key Audit Findings:
1. **Safety & Non-Destructiveness:** The codebase is **safe to upgrade**. The database schema changes across Milestones A, B, and C are **100% additive**. Core tables (`users`, `conversations`, `messages`, `tasks`, `goals`, `projects`, `recurring_schedules`, `signals`, `ai_memories`, `personal_finance`, `routines`, `workouts`, `email_accounts`, `mesh_pairings`, `diary_entries`) are completely untouched. Zero columns have been deleted, renamed, or altered in ways that could invalidate existing data.
2. **Current Supabase Revision Status:** Live non-destructive inspection of the production Supabase database revealed that it is currently at Alembic revision **`i2a3b4c5d6e7`** (Milestone B), with 41 tables and 1 registered user actively preserved.
3. **Pending Database Migrations:** Only **one** migration is pending: **`j3b4c5d6e7f8`** (Milestone C: Shared UI Orchestrator), which creates two brand-new tables (`ui_workspace_configs` and `ui_change_proposals`).
4. **Vercel Serverless Architecture:** The codebase contains hardened serverless boundaries (`app/core/execution_provider.py`) ensuring background CLI processes (Antigravity CLI, coworker autonomous workers, desktop execution) cleanly return `503 Service Unavailable (EXECUTION_PROVIDER_UNAVAILABLE)` rather than stalling serverless invocations or consuming execution limits. The primary API, conversational chat, task management, UI layout engine, and database interactions are 100% serverless-ready.
5. **Readiness Verdict:** **`READY WITH ACTIONS`**. The upgrade is safe to deploy immediately following a single non-destructive pre-deployment step: applying Alembic migration `j3b4c5d6e7f8` via the Supabase Session Pooler (port `5432`).

---

## 2. Previous Deployment Configuration

The existing Vercel deployment was established during the Vercel Hobby deployment transition and was documented in `VERCEL.md` and `docs/implementation/vercel-hobby-deployment.md`.

* **Vercel Project Setup:**
  * Framework: Vite
  * Build Command: `cd frontend && npm ci && npm run build`
  * Output Directory: `frontend/dist`
  * Function Entry Point: `api/index.py` (FastAPI bridge)
  * Serverless Region: `sin1` (Singapore, co-located with Supabase in `ap-southeast-1`)
  * Serverless Function Timeout: `maxDuration: 300` seconds
  * Memory: 1024 MB
* **Database Connection Architecture:**
  * Supabase PostgreSQL version: PostgreSQL 17.6 on x86_64-pc-linux-gnu.
  * Transaction Pooler: Port `6543` (Supavisor) configured for application queries via `DATABASE_URL`.
  * Session Pooler: Port `5432` configured for DDL and migrations via `MIGRATION_DATABASE_URL`.
  * Pool Class: SQLAlchemy `NullPool` (stateless per request; zero persistent connection pool across serverless instances).
  * Prepared Statements: Disabled via `connect_args={"prepare_threshold": None}` to avoid duplicate prepared statement errors under Supavisor transaction routing.
* **Environment Variables in Vercel Production:**
  * `DATABASE_URL`: `postgresql+psycopg://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres`
  * `SECRET_KEY`: Production secret token for JWT auth
  * `ENVIRONMENT`: `production`
  * `SERVERLESS`: `true`
  * `AI_PROVIDER`: `gemini` (with Groq fallbacks)
  * `GEMINI_API_KEY`: Google Gemini API key
  * `GROQ_API_KEY`: Groq LPU inference key
  * `NVIDIA_API_KEY`: NVIDIA NIM fallback key

---

## 3. Implementation Documentation Reviewed

All architectural and progress documentation across Milestones A through E was systematically reviewed:

| Document | Milestone Focus | Key Findings & Compatibility Relevance |
|:---|:---|:---|
| `docs/implementation/vercel-hobby-deployment.md` | Serverless baseline | Established `NullPool`, port `6543` handling, disabled prepared statements, and execution boundaries. |
| `docs/implementation/milestone-a-progress.md` | Milestone A (Coding Agent) | Replaced direct legacy SDK with reviewed coding task model (`coding_projects`, `coding_tasks`, `coding_sessions`). Implemented `410 Gone` guard for legacy direct executions. |
| `docs/implementation/milestone-b-progress.md` | Milestone B (Coworkers) | Created coworker governance, approvals, and event logging tables (`coworkers`, `coworker_tasks`, `coworker_sessions`, etc.). Mocked CUA for serverless safety. |
| `docs/implementation/milestone-c-progress.md` | Milestone C (UI Orchestrator) | Created adaptive widget system, layouts, preferences, and rollback snapshots (`ui_workspace_configs`, `ui_change_proposals`). |
| `docs/implementation/milestone-d.md` | Milestone D (Desktop & Android) | Integrated multi-surface shell, cross-device theme persistence, responsive breakpoints. |
| `docs/implementation/milestone-e.md` | Milestone E (Production Hardening) | Implemented unified `ApiError` hierarchy, request correlation IDs (`X-Request-ID`), provider resilience, health monitoring, and graceful database error mapping. |
| `docs/implementation/known-issues.md` | Operational Risks | Outlined ConPTY/CLI terminal limitations on headless environments; confirmed that headless execution routes require explicit host execution status checks. |

---

## 4. Current Vercel Configuration

The configuration files in repository root were validated:

### 1. `vercel.json`
```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": "vite",
  "buildCommand": "cd frontend && npm ci && npm run build",
  "outputDirectory": "frontend/dist",
  "regions": ["sin1"],
  "functions": {
    "api/index.py": {
      "runtime": "python@3.12",
      "maxDuration": 300,
      "memory": 1024
    }
  },
  "routes": [
    {
      "src": "/api/(.*)",
      "dest": "api/index.py"
    },
    {
      "handle": "filesystem"
    },
    {
      "src": "/(.*)",
      "dest": "/index.html"
    }
  ]
}
```
* **Validation Outcome:** Valid. Python runtime pinned to `python@3.12`. All `/api/*` traffic correctly rewrites to `api/index.py`. SPA client routing directs non-asset routes to `/index.html`.

### 2. `.python-version`
* Contains `3.12`, matching the `runtime: "python@3.12"` specified in `vercel.json`.

### 3. `requirements.txt`
* Includes all required serverless dependencies:
  * `fastapi>=0.115.0`, `uvicorn>=0.32.0`, `pydantic>=2.10.0`, `pydantic-settings>=2.6.0`
  * `sqlalchemy>=2.0.36`, `alembic>=1.14.0`, `psycopg[binary]>=3.2.0`
  * `google-genai>=1.0.0`, `groq>=0.11.0`, `httpx>=0.28.0`
  * `segno>=1.6.0`, `pillow>=10.4.0`

### 4. `api/index.py`
```python
import os
import sys
from pathlib import Path

# Insert backend directory into Python path so imports resolve cleanly
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.main import app  # ASGI entrypoint
```
* **Validation Outcome:** Clean ASGI bridge with correct relative path resolution.

---

## 5. Previous vs Current Deployment Comparison

| Dimension | Previous Deployed Version (Pre-Milestone A) | Current Repository Version (Milestones A–E) | Impact / Risk Assessment |
|:---|:---|:---|:---|
| **Alembic Revision** | `g2c3d4e5f6a7` | `j3b4c5d6e7f8` (DB currently at `i2a3b4c5d6e7`) | Low. Fully additive schema. |
| **Total DB Tables** | 33 tables | 43 tables (41 existing in Supabase + 2 pending) | Low. Only adds tables; zero alters. |
| **UI Orchestrator** | Static dashboard widgets | Dynamic layout engine, preferences & rollback | Zero impact on legacy views; additive. |
| **Coworkers & Coding** | Unpersisted in-memory CLI bridges | Persisted tasks, sessions, approvals, events | Zero impact on standard tasks; backward compatible. |
| **Desktop / Shell** | Web-only | Multi-platform client shell (Web, Desktop, Android) | Web interface remains 100% responsive and default. |
| **Execution Boundary**| Unhandled subprocess failures | `ExecutionProviderUnavailableError` (HTTP 503) | Significant improvement. Serverless safe. |
| **Error Handling** | Generic HTTP 500 exceptions | Structured `ApiError` with correlation IDs | Significant improvement for client debugging. |
| **Python Runtime** | 3.12 | 3.12 (pinned in `vercel.json` & `.python-version`) | Exact match. |
| **Frontend Bundle** | Vite / React single bundle | Vite code-split chunks (2367 modules, 432 KB core) | Build verified; zero errors in 26.46s. |

---

## 6. Supabase Database Compatibility

Supabase PostgreSQL connectivity was verified non-destructively:
* **DNS Resolution:** `aws-0-ap-southeast-1.pooler.supabase.com` resolved to `['52.74.252.201', '54.255.219.82', '52.77.146.31']`.
* **TCP Port 6543 (Transaction Pooler):** Connected successfully.
* **TCP Port 5432 (Session Pooler):** Connected successfully.
* **SQLAlchemy App Connection (`:6543`):** Verified on `PostgreSQL 17.6 on x86_64-pc-linux-gnu`.
* **SQLAlchemy Migration Connection (`:5432`):** Verified on `PostgreSQL 17.6 on x86_64-pc-linux-gnu`.

### Connection Configuration Safeguards:
In `backend/app/core/database.py`:
1. If `:6543` or `SERVERLESS=true` is detected:
   * Sets `poolclass=NullPool` (avoids stale connections across lambda invocations).
   * Sets `connect_args={"prepare_threshold": None}` (prevents Supavisor prepared-statement collision errors).
2. In `backend/alembic/env.py`:
   * If URL specifies port `:6543`, it automatically rewrites to `:5432` for running migrations because DDL statements and migration locks require the Session Pooler.

---

## 7. Alembic Migration Comparison

The full migration history was audited:

```
g2c3d4e5f6a7 (Previous Baseline: "Add diary entries table")
   │
   ▼
h1a2b3c4d5e6 (Milestone A: "Add coding_projects, coding_tasks, coding_sessions") [APPLIED IN SUPABASE]
   │
   ▼
i2a3b4c5d6e7 (Milestone B: "Add coworker ecosystem tables") [APPLIED IN SUPABASE - CURRENT DB HEAD]
   │
   ▼
j3b4c5d6e7f8 (Milestone C: "Shared UI Orchestrator tables") [PENDING UPGRADE]
```

### Detailed Migration Inspection:
1. **`h1a2b3c4d5e6` (Applied):**
   * Creates `coding_projects`, `coding_tasks`, `coding_sessions`.
   * Foreign keys reference `users.id` with `CASCADE` or `SET NULL`.
   * **Result:** Strictly additive.
2. **`i2a3b4c5d6e7` (Applied):**
   * Creates `coworkers`, `coworker_tasks`, `coworker_sessions`, `coworker_events`, `coworker_approvals`.
   * Foreign keys reference `users.id` and `coding_projects.id`.
   * **Result:** Strictly additive.
3. **`j3b4c5d6e7f8` (Pending):**
   * Creates `ui_workspace_configs` (PK `user_id` -> `users.id`) and `ui_change_proposals`.
   * **Result:** Strictly additive. No existing columns or tables touched.

---

## 8. Existing Data Preservation Assessment

A live query against Supabase confirmed:
* **Active User Count:** `1` user record exists and is intact.
* **Core Tables Audited:**
  * `users`
  * `tasks`
  * `goals`
  * `projects`
  * `habits` & `habit_logs`
  * `workouts`, `workout_exercises`, `workout_logs`
  * `finance_transactions`, `finance_budgets`, `finance_bills`, `savings_goals`
  * `ai_conversations`, `ai_messages`, `ai_memories`, `ai_recommendations`
  * `diary_entries`
  * `mesh_pairings`, `mesh_relay_messages`
* **Assessment:** Zero risk of data loss. None of the migrations drop tables, drop columns, modify column data types, or enforce restrictive non-null constraints on existing records. Existing user sessions, credentials, tokens, and conversational context remain 100% intact.

---

## 9. API and Feature Compatibility Matrix

| Endpoint Group | Route Prefix | Vercel Serverless Ready? | Behavior on Vercel | Persistent Host Required? |
|:---|:---|:---:|:---|:---:|
| **Authentication & Users** | `/api/auth`, `/api/users` | **YES** | Full JWT login, profile management, and sessions | No |
| **Tasks & Planning** | `/api/tasks`, `/api/goals` | **YES** | CRUD operations, prioritization, subtasks | No |
| **Habits & Routines** | `/api/habits`, `/api/workouts` | **YES** | Logging, streaks, completion history | No |
| **Finance & Diary** | `/api/finance`, `/api/diary` | **YES** | Expense tracking, budget calculations, encrypted diary | No |
| **AI Chat & Reasoning** | `/api/chat`, `/api/ai` | **YES** | Gemini Live & Groq inference, tool calling, memory recall | No |
| **Intelligence Situation**| `/api/intelligence` | **YES** | Real-time daily context synthesis | No |
| **UI Orchestrator** | `/api/ui-orchestrator` | **YES** | Layout preferences, widget proposals, rollback | No |
| **Mesh Signaling & Relay**| `/api/mesh` | **YES** | WebRTC signaling, pairing codes, relay store | No |
| **Coworker Management** | `/api/coworkers` | **YES** | Config, task definition, approval workflows | No |
| **Autonomous Coworkers** | `/api/coworkers/execute` | **PARTIAL** | Spec/mock evaluation works; real subprocess loop disabled | **YES** (Worker host) |
| **Headless Coding Tasks** | `/api/coding/execution` | **PARTIAL** | Task status/history query works; headless CLI disabled | **YES** (Desktop host) |
| **Interactive ConPTY** | `/api/agy/*` | **NO** | Returns `503 EXECUTION_PROVIDER_UNAVAILABLE` | **YES** (Windows host) |
| **Desktop CLI Control** | `/api/desktop/*` | **NO** | Returns `503 EXECUTION_PROVIDER_UNAVAILABLE` | **YES** (Windows host) |

---

## 10. Serverless vs Persistent Execution Requirements

Vercel functions operate under strict serverless constraints:
* **Stateless Lifespan:** Maximum duration is 300 seconds. Process memory is terminated upon completion.
* **No Persistent Subprocesses:** Spawning background long-running Daemons (such as interactive terminal ConPTYs or continuous LLM autonomous loops) will cause lambdas to freeze or be killed abruptly.
* **Architecture Solution Implemented:**
  * `backend/app/core/execution_provider.py` automatically detects serverless environments (`VERCEL=1` or `SERVERLESS=true`).
  * When invoked on Vercel, requests for local coding agent execution or desktop CLI actions fail cleanly with HTTP 503 and the exact structured payload:
    ```json
    {
      "code": "EXECUTION_PROVIDER_UNAVAILABLE",
      "message": "Coding agent requires a persistent IRIS execution host. Configure a persistent worker/API host and retry.",
      "request_id": "req-..."
    }
    ```
  * All cloud-capable features (Conversational AI, intelligence synthesis, full task/calendar/finance management, UI customization, and WebRTC mesh relay) execute natively on Vercel with zero external worker requirements.

---

## 11. Security and Authentication Assessment

1. **Database Secrets:**
   * Passwords and credentials are fully isolated in environment variables.
   * `backend/scripts/test_db_connection.py` and application logging enforce automatic regex credential masking (`:*****@`).
2. **CORS & Network Boundaries:**
   * Standard CORS policies configured via `CORS_ORIGINS` setting.
   * In production, default origins are constrained to the production frontend domain.
3. **Database Injection & DDL Security:**
   * All SQLAlchemy queries use parameterized statements (`text(...)` with bind params or ORM queries).
   * Migrations are strictly separated from application queries and restricted to the session pooler.
4. **Token Security:**
   * User passwords hashed using bcrypt.
   * JWT tokens signed using `SECRET_KEY`.

---

## 12. Tests and Verification Results

All non-destructive verification suites were executed against the current repository state:

1. **Python Compilation Suite:**
   * Command: `python -m compileall -q app`
   * Result: **PASS** (Zero syntax errors, zero circular import issues).
2. **Deployment Runtime Tests:**
   * Command: `pytest tests/api/test_deployment_runtime.py`
   * Result: **10 passed in 3.62s** (Verified health endpoint, execution provider unavailable guards, NullPool initialization).
3. **PostgreSQL Compatibility Tests:**
   * Command: `pytest tests/integration/test_postgres_compatibility.py`
   * Result: **4 passed in 0.26s** (Verified connection parameter normalization and pool configuration).
4. **Migrations & UI Orchestrator Flow:**
   * Command: `pytest tests/integration/test_migrations_and_flow.py tests/api/test_ui_orchestrator.py`
   * Result: **12 passed in 6.23s** (Verified full Alembic migration forward/backward flow and UI preferences persistence).
5. **Frontend Production Build:**
   * Command: `npm --prefix frontend run build` (`tsc --noEmit && vite build`)
   * Result: **PASS in 26.46s** (2367 modules transformed into `frontend/dist`, zero TypeScript or bundling errors).

---

## 13. Outstanding Issues

| Issue | Severity | Status | Impact & Workaround |
|:---|:---:|:---:|:---|
| **Pending Migration `j3b4c5d6e7f8`** | Medium | Action Required | UI Orchestrator endpoints will fail until this single migration is run. Solved by running `alembic upgrade head` before or immediately upon deployment. |
| **Headless ConPTY on Serverless** | Low | By Design | The interactive `/agy` terminal cannot run inside Vercel lambdas. Correctly returns structured HTTP 503; users must use desktop companion for direct terminal control. |
| **Vercel Hobby 4.5MB Payload Limit** | Low | Monitored | Large ephemeral vision image uploads (>4.5MB) will be rejected by Vercel's edge gateway. The frontend compresses images before transmission. |

---

## 14. Recommended Deployment Procedure

Follow these sequential, non-destructive steps to upgrade the deployment:

### Step 1 — Database Migration (Pre-Deployment)
Run the single pending migration from your local developer machine (where `backend/.env` has verified access to Supabase):
```powershell
cd backend
.venv\Scripts\python.exe -m alembic upgrade head
```
*Note: `backend/alembic/env.py` automatically routes this through port `5432` (Session Pooler).*

### Step 2 — Verify Alembic Head
Verify that the Supabase database revision has advanced to `j3b4c5d6e7f8`:
```powershell
.venv\Scripts\python.exe -m alembic current
```

### Step 3 — Git Push to Production
Push the tested commit to GitHub (which triggers Vercel's production deployment):
```powershell
git push origin main
```

### Step 4 — Post-Deployment Health Check
Query the production Vercel health endpoint:
```powershell
curl -s https://[YOUR-VERCEL-DOMAIN]/api/health
```
Verify the response contains:
```json
{
  "status": "ok",
  "database": "ok",
  "ai": "enabled"
}
```

---

## 15. Rollback and Recovery Plan

In the unlikely event of an issue following deployment:

### Fast Rollback (Vercel Instant Rollback)
1. Navigate to the **Vercel Dashboard** -> **Deployments**.
2. Select the previous stable deployment (commit `ec72418` or earlier).
3. Click **"Instant Rollback"** (promotes the previous frontend and serverless function bundle immediately with zero build wait time).

### Database Rollback (Zero Data Loss)
Because migration `j3b4c5d6e7f8` only created new tables (`ui_workspace_configs` and `ui_change_proposals`), downgrading it will **not** affect any existing user data, tasks, notes, or memories:
```powershell
cd backend
.venv\Scripts\python.exe -m alembic downgrade i2a3b4c5d6e7
```

---

## 16. Final Deployment Readiness Decision

### **Verdict: READY WITH ACTIONS**

The current IRIS codebase is thoroughly tested, structurally sound, serverless-compatible, and safe to replace the existing Vercel deployment. 

**Required Action Prior to / Concurrently with Deployment:**
* Execute `alembic upgrade head` to apply the single pending additive migration (`j3b4c5d6e7f8`) to Supabase.
