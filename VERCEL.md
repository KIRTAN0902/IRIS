# IRIS — Production Deployment Guide: Vercel + Supabase

This guide outlines how to deploy IRIS to **Vercel** as a fullstack serverless application (React/Vite SPA + FastAPI serverless backend) backed by **Supabase PostgreSQL**.

---

## 1. Architecture Overview

```text
       Browser (User on Desktop / Mobile)
                       │ (HTTPS)
                       ▼
            Vercel Edge Network
      ┌─────────────────────────────────┐
      │  Frontend: React / Vite SPA     │ (Routes / -> dist/index.html)
      │  Backend:  FastAPI Serverless   │ (Rewrites /api/* -> /api/index.py)
      └─────────────────────────────────┘
                       │
                       │ SQLAlchemy 2.0 (NullPool)
                       │ psycopg 3 driver
                       ▼
       Supabase Transaction Pooler (:6543)
       (aws-0-ap-southeast-1.pooler.supabase.com)
                       │
                       ▼
          Supabase Managed PostgreSQL 17
```

---

## 2. Environment Variables on Vercel

In your **Vercel Project Settings → Environment Variables**, configure:

| Variable | Value | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres.ermbceotgkkuiyebujaa:[PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres` | Supabase Transaction Pooler (:6543) |
| `ENVIRONMENT` | `production` | Production mode |
| `DEFAULT_TIMEZONE` | `Asia/Kolkata` | User timezone |
| `LOG_LEVEL` | `INFO` | Standard logging |
| `SECRET_KEY` | `[GENERATE_A_RANDOM_32_CHAR_STRING]` | App secret key |
| `AI_PROVIDER` | `omniroute` *(or `gemini`)* | Active AI provider |
| `OMNIROUTE_BASE_URL` | `https://omniroute.yourdomain.com/v1` | Public/Hosted OmniRoute gateway URL |
| `OMNIROUTE_API_KEY` | `[YOUR_OMNIROUTE_API_KEY]` | OmniRoute API Key |
| `GEMINI_API_KEY` | `[OPTIONAL_GEMINI_KEY]` | Fallback Gemini API Key |

---

## 3. Deploying to Vercel (Step-by-Step)

### Option A: Via Vercel Web Dashboard (Recommended)
1. Push your latest code to your GitHub repository:
   ```bash
   git add .
   git commit -m "feat: complete Supabase PostgreSQL migration & Vercel serverless configuration"
   git push origin main
   ```
2. Go to [vercel.com/new](https://vercel.com/new) and import your `IRIS` repository.
3. Configure Project:
   - **Framework Preset**: `Vite` (or `Other`)
   - **Root Directory**: `./` (Leave as Root)
   - **Build Command**: `cd frontend && npm install && npm run build`
   - **Output Directory**: `frontend/dist`
4. Expand **Environment Variables** and paste the production variables from the table above.
5. Click **Deploy**.

---

### Option B: Via Vercel CLI
```bash
# Install Vercel CLI if needed
npm i -g vercel

# Deploy to preview
vercel

# Deploy to production
vercel --prod
```

---

## 4. Running Migrations in the Future

Because Vercel serverless runtimes do not execute long-running CLI commands, run future Alembic schema updates directly against Supabase Session Pooler (`:5432`) from your local terminal or CI/CD:

```bash
# In backend/ directory
alembic upgrade head
```

---

## 5. Deployment Verification Checklist

- [x] Schema initialized with all 18 tables in Supabase PostgreSQL.
- [x] Development data migrated and PostgreSQL sequences synchronized.
- [x] Serverless connection pool (`NullPool`) active for port 6543.
- [x] Unified `vercel.json` configured with SPA fallback and `/api/*` serverless bridge.
- [x] All 144 unit and integration tests passing.
