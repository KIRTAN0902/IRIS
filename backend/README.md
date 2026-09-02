# IRIS — Intelligent Responsive Information System

> *Your personal decision command center.*
>
> Don't just manage your tasks. Decide what deserves your attention and time right now.

IRIS is a single-user personal decision intelligence system for managing **college**, an
**internship**, a **startup** (the primary strategic goal), and everything
personal — tasks, goals, deadlines, time, routine schedules, focus sessions, outreach CRM,
growth experiments, cross-domain signals, attention engine, and AI-powered contextual planning.

The central mission of IRIS is to answer ONE question with precision:

> **"Given my current situation, what deserves my attention right now?"**

---

## Decision Intelligence Architecture (Phases 1, 2 & 3)

```text
               USER DATA & PROFILE (Facts, Preferences, Goals, Constraints)
                                      │
                 CROSS-DOMAIN SIGNALS (Tasks, Goals, Calendar, Startup, Ext-Stubs)
                                      │
               ATTENTION ENGINE (Deterministic Urgency, Impact, Deadline pressure)
                                      │
             HARD CONSTRAINTS & TIME ENGINE (Sleep, Wake, Flexible Windows)
                                      │
                    DETERMINISTIC CONTEXTUAL DECISION ENGINE
                                      │
                                 DECISION CONTEXT
                                      │
              GEMINI REASONING (Structured Schema, Grounded in Reality)
                                      │
             RECOMMENDATION OUT (Action, Evidence, Outcome, Opportunity Cost)
                                      │
             DECISION AUDIT LOG & USER FEEDBACK LOOP (ACCEPTED/REJECTED/DEFERRED)
```

Key design principles:

* **Contextual Reasoning Over Fixed Formulas.** Fixed priority formulas (e.g. `Startup = 1.5`, `College = 1.0`) are inputs, not final determinants. Imminent college deadlines beat long-term startup tasks; open windows evaluate startup bottlenecks.
* **Deterministic Authority & Hard Constraint Protection.** Sleep hours (23:00) and fixed routine blocks are inviolable hard constraints. Durations are automatically sanitized and clamped.
* **Cross-Domain Signals & Relevance Filtering.** Normalized `Signal` model aggregates signals across domains with time-decay and expiration ranking.
* **Attention Engine.** Proactively detects overdue tasks, approaching deadlines, lagging milestones, inbound founder replies, and schedule conflicts.
* **Information Provenance & Zero Hallucination.** Strict separation between `OBSERVED`, `DERIVED`, `INFERRED`, and `RECOMMENDED`. External integrations that are not yet connected (`EMAIL`, `FINANCE`) are explicitly declared as unavailable, and IRIS responds with `ASK_USER` instead of fabricating fake inbox data.
* **Decision Audit & Feedback Loop.** Every recommendation is logged with context snapshots. User feedback (`ACCEPTED`, `REJECTED`, `DEFERRED`, `COMPLETED`) is recorded to guide future calibration.

### Deterministic Attention Score Formula

```text
attention_score = urgency × 35.0
                + impact × 25.0
                + strategic_relevance (Startup: 15.0, College/Internship: 10.0, Personal: 5.0)
                + deadline_pressure (Overdue: +30.0, <=2h: +25.0, <=24h: +15.0)
                - age_decay (capped at 15.0)
```

---

## Requirements & Setup

* Python **3.12+**
* PostgreSQL (Supabase / Render / Local) or SQLite (for local testing/dev)
* psycopg 3 driver (`psycopg[binary]>=3.2`)
* OmniRoute Gateway / Google Gemini API key *(optional — deterministic fallback operates fully without AI keys)*

```bash
cd backend
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt -r requirements-dev.txt
```

### Environment

Copy `.env.example` to `.env` and fill it in:

```env
# Supabase PostgreSQL (Production / Staging via Session Pooler)
DATABASE_URL=postgresql+psycopg://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres

# Or Local SQLite (Development)
# DATABASE_URL=sqlite:///./iris.db

SECRET_KEY=change-me-in-production
ENVIRONMENT=production
DEFAULT_TIMEZONE=Asia/Kolkata
LOG_LEVEL=INFO

# AI Provider Configuration
AI_PROVIDER=omniroute
OMNIROUTE_BASE_URL=http://localhost:20128/v1
OMNIROUTE_API_KEY=your-omniroute-api-key
OMNIROUTE_MODEL=auto/best-fast
```

### Database Migrations (Alembic)

```bash
alembic upgrade head
```

### Migrate Existing SQLite Data to PostgreSQL

```bash
python scripts/migrate_sqlite_to_postgres.py --source sqlite:///./iris.db --target postgresql+psycopg://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres
```

### Seed Development Data

```bash
python scripts/seed.py --force
```

### Running & Tests

```bash
# Run server
uvicorn app.main:app --reload

# Run complete test suite (111 tests)
pytest

# Code formatting & lint check (0 errors)
ruff check app tests scripts

# Evaluate 20 Real-World Scenarios (A through T)
python scripts/evaluate_decisions.py
python scripts/evaluate_decisions.py --use-ai
```

---

## 20 Real-World Decision Scenarios (A through T)

| ID | Name | Core Context & Decision Expected |
|---|---|---|
| **A** | Normal Weekday Morning | 09:00, 90m free; no urgent obligations -> Startup outreach prioritized. |
| **B** | Urgent College Deadline | College assignment due in 90m -> MUST_DO College assignment. |
| **C** | Urgent Internship Deliverable | Internship deliverable due tomorrow -> MUST_DO Internship deliverable. |
| **D** | Large Saturday Window | 4h available -> Dynamic multi-step sequence (Outreach + Product + College). |
| **E** | Opportunity Cost | Founder conversations prioritized over UI polishing during validation. |
| **F** | No Meaningful Work | No open tasks -> Recommends rest / reflection without inventing fake filler work. |
| **G** | Missing Information | Unknown deadline / deliverable details -> Returns `ASK_USER`. |
| **H** | Sleep Protection | 22:45 query -> Duration strictly clamped to 15m before 23:00 sleep. |
| **I** | Low Energy Alignment | Low energy state -> Picks administrative task over deep-work architecture. |
| **J** | State Dynamic Change | Startup goal behind target -> Dynamic score boost for outreach sprint. |
| **K** | Urgency vs Strategic | 2h college deadline beats long-term startup 5-year strategy task. |
| **L** | Dependencies Ordering | Preparation task ordered before dependent execution call task. |
| **M** | Available Time Clamping | 30m window gracefully clamps 120m task or fits smaller task. |
| **N** | Realistic Weekday Evening | 21:00-23:00 flexible window evaluates startup work contextually. |
| **O** | Cross-Domain Architecture | Extensible DecisionContext accepts multi-domain signals. |
| **P** | Calendar + Startup | Evening flexible block (21:00-23:00) with startup goal behind. |
| **Q** | College Deadline Beats Startup | Imminent 2h college deadline beats long-term startup priority. |
| **R** | Inbound Signal + Startup | Inbound demo request email signal prioritized for immediate demo prep. |
| **S** | Conflicting Domain Signals | Multiple competing cross-domain signals ranked deterministically by attention score. |
| **T** | Missing External Integration | Context marks disconnected domains; missing info returns ASK_USER without hallucinating. |

---

## API Reference Overview

| Domain | Method & Endpoint | Description |
|---|---|---|
| **Intelligence** | `GET /api/intelligence/today` | Complete snapshot of schedule, windows, tasks, goals, signals, attention, decision. |
| **Intelligence** | `GET /api/intelligence/signals` | Query cross-domain signals (filter by domain, min_importance, active). |
| **Intelligence** | `GET /api/intelligence/attention` | Retrieve prioritized attention items ranked by deterministic score. |
| **Intelligence** | `GET /api/intelligence/decisions` | Historical decision audit log (filter by decision_type, feedback). |
| **Intelligence** | `POST /api/intelligence/feedback` | Record user feedback (`ACCEPTED`, `REJECTED`, `DEFERRED`, `COMPLETED`). |
| **Intelligence** | `POST /api/intelligence/recommend` | Trigger real-time decision recommendation. |
| **Intelligence** | `GET/POST /api/intelligence/recurring-schedules` | CRUD for weekly commitments, sleep schedule, routine blocks. |
| **Tasks** | `GET/POST /api/tasks`, `PATCH /api/tasks/{id}` | Task management with priorities, estimated duration, energy levels. |
| **Goals** | `GET/POST /api/goals` | Hierarchical goal trees with measurable target/current values. |
| **Startup** | `GET/POST /api/leads`, `GET/POST /api/outreach` | Founder outreach CRM, lead pipeline, and conversion analytics. |
| **AI** | `POST /api/ai/recommend`, `POST /api/ai/ask` | Contextual AI reasoning endpoints with structured output & deterministic fallbacks. |
