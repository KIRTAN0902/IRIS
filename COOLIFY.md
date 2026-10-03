# IRIS — Production Deployment Guide (Coolify + Single URL + SQLite)

This guide provides step-by-step instructions for deploying **IRIS (Intelligent Responsive Information System)** to production using **Coolify**.

---

## 1. Architecture Overview

IRIS is engineered as a **Single-Domain, Zero-CORS, Multi-Service Architecture**:

```text
                              USER (Phone & Desktop)
                                        │
                                        ▼
                            https://iris.example.com
                                        │
                           Coolify Reverse Proxy (SSL)
                                        │
               ┌────────────────────────┴────────────────────────┐
               │                                                 │
               ▼ (Port 80)                                       ▼ (/api/*, /health)
       Frontend Container                                Backend Container
    (React 18 SPA + Nginx)                              (FastAPI + Uvicorn)
               │                                                 │
               │ (SPA Routing & Static Assets)                   ├── Persistent SQLite
               │                                                 │   (/app/data/iris.db)
               │                                                 │
               └─────────────────────────────────────────────────┼── Alembic Migrations
                                                                 │
                                                                  └── AIProvider
                                                                          │
                                                                          ▼
                                                                     NVIDIA NIM
```

### Key Highlights
- **Single Public URL**: All traffic goes through `https://iris.example.com`. Frontend at `/`, API requests at `/api/...`, health checks at `/health`.
- **Zero CORS Issues**: Browser requests are same-origin (`/api/...`).
- **Persistent SQLite**: SQLite database resides in a Docker persistent volume (`/app/data/iris.db`) that survives container restarts, redeployments, and image updates.
- **Automated Safe Migrations**: Container startup automatically executes `alembic upgrade head` before launching Uvicorn.
- **Zero Dev Seed in Production**: Development seeds (`scripts/seed.py`) are never run automatically in production.
- **Provider-Agnostic AI Layer**: Configured for NVIDIA NIM gateway with automated fallback to deterministic reasoning or Gemini.

---

## 2. Prerequisites

1. A running **Coolify (v4+)** server on a VPS.
2. A registered domain or subdomain (e.g. `iris.yourdomain.com`).
3. DNS **A** or **AAAA** record pointing `iris.yourdomain.com` to your Coolify server's public IP.
4. (Optional) NVIDIA API key (from build.nvidia.com) or Gemini API key.

---

## 3. Coolify Deployment Steps

### Step 1: Create a New Resource in Coolify
1. In your Coolify dashboard, select your **Project** and **Environment** (e.g. `Production`).
2. Click **+ New Resource** and choose **Docker Compose**.
3. Select **Git Repository** (Private or Public) and connect your repository: `https://github.com/your-username/IRIS`.

### Step 2: Configure General Settings
- **Build Pack**: `Docker Compose`
- **Base Directory**: `/` (repository root)
- **Docker Compose Location**: `/docker-compose.yml`

### Step 3: Configure Domain & Routing
- In the **Domains** section, enter your production domain:
  ```text
  https://iris.example.com
  ```
- Coolify will automatically provision and renew a **Let's Encrypt SSL certificate** and route all traffic to the `frontend` service on port `80`.

### Step 4: Configure Persistent Storage (Volume)
- Verify that the persistent volume `iris_data` is mounted to `/app/data` on the backend container:
  - **Volume Name**: `iris_data`
  - **Mount Path**: `/app/data`
- *Note:* The Docker Compose file defines `iris_data:/app/data` automatically.

### Step 5: Configure Environment Variables & Secrets
In the **Environment Variables** tab in Coolify, configure the following:

#### Required Variables
```dotenv
# Environment
ENVIRONMENT=production
LOG_LEVEL=INFO
DEFAULT_TIMEZONE=Asia/Kolkata

# Persistent SQLite Database
DATABASE_URL=sqlite:////app/data/iris.db

# Security Secret (Generate a random 32+ character string)
SECRET_KEY=replace-with-a-secure-random-secret-key-32-chars-minimum

# AI Provider
AI_PROVIDER=nvidia
```

#### Secret Variables (Mark as "Secret" in Coolify)
```dotenv
# NVIDIA NIM Configuration
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_API_KEY=your-nvidia-api-key-here
NVIDIA_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
NVIDIA_TIMEOUT_SECONDS=45.0

# (Optional) Gemini API Key for Fallback
GEMINI_API_KEY=your-gemini-api-key-if-applicable
GEMINI_MODEL=gemini-2.5-flash
```

---

## 4. NVIDIA NIM Configurations

IRIS communicates with NVIDIA NIM using one of the following setups:

### Scenario A: NVIDIA Hosted NIM Cloud API (Recommended)
Using build.nvidia.com cloud endpoints:
```dotenv
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_API_KEY=nvapi-your-secret-api-key
NVIDIA_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
```

### Scenario B: Self-Hosted NVIDIA NIM Container
If running a local or private NIM container on your GPU infrastructure:
```dotenv
NVIDIA_BASE_URL=http://nim-service:8000/v1
NVIDIA_API_KEY=optional-key-if-auth-enabled
NVIDIA_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
```

### Scenario C: Deterministic Fallback Mode (No AI Key)
If `NVIDIA_API_KEY` is omitted or NVIDIA NIM is temporarily unreachable, IRIS **never crashes** — it gracefully operates using deterministic constraint, priority, and scoring engines.

---

## 5. Database Management & Safety

### Automated Migrations on Startup
When the backend container starts, `backend/entrypoint.sh` executes:
```bash
alembic upgrade head
```
This applies any pending schema migrations to the persistent SQLite database before starting the FastAPI server.

### Safe Online Database Backup
IRIS includes a WAL-aware online backup script that snapshots the database without downtime.

To create a live backup inside the running container:
```bash
docker compose exec backend python scripts/backup_db.py
```
This creates a timestamped snapshot in `/app/data/backups/iris_backup_YYYYMMDD_HHMMSS.db`.

To back up to a specific location on the host:
```bash
docker compose exec backend python scripts/backup_db.py /app/data/backups/manual_backup.db
```

### Restoring a Backup
1. Stop the backend service:
   ```bash
   docker compose stop backend
   ```
2. Copy the backup file over the live database file:
   ```bash
   cp /path/to/iris_backup_YYYYMMDD_HHMMSS.db /var/lib/docker/volumes/iris_data/_data/iris.db
   ```
3. Restart the backend service:
   ```bash
   docker compose start backend
   ```

---

## 6. Verification & Health Checks

### 1. Liveness & Readiness Endpoint
```bash
curl -i https://iris.example.com/health
```
**Expected Response:** `HTTP/1.0 200 OK`
```json
{
  "status": "ok",
  "service": "IRIS",
  "version": "0.1.0",
  "environment": "production",
  "database": "ok",
  "ai": "enabled"
}
```

### 2. Frontend SPA Routes
Test opening and refreshing the following URLs in a browser or phone:
- `https://iris.example.com/` (Home Chat & Recommendation Workspace)
- `https://iris.example.com/tasks` (3-Domain Tasks: Startup, Internship, College)
- `https://iris.example.com/schedule` (Weekly Schedule & Time Windows)
- `https://iris.example.com/projects` (Projects & Milestones)

All routes must return the React application with `HTTP 200`.

### 3. API Requests
- `GET https://iris.example.com/api/intelligence/today`
- `GET https://iris.example.com/api/chat/conversations`
- `GET https://iris.example.com/api/tasks`

---

## 7. Updates & Redeployments

- **Zero Data Loss**: The SQLite database is stored in the `iris_data` volume. Redeploying from Coolify or pulling updated Git commits replaces only the container images; your data remains untouched.
- **Rollback Procedure**: If a deployment has an issue, simply roll back the commit or tag in Coolify. The persistent volume `/app/data/iris.db` will remain fully intact.
- **Container Restarts**: The backend and frontend services have `restart: unless-stopped` configured.
