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
* An API key for any LLM provider, or a local model server *(optional — deterministic fallback operates fully without AI)*

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

# AI model: any provider, any model
AI_PROVIDER=nvidia
AI_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
AI_API_KEY=your-api-key
```

### AI Model Harness (model-agnostic)

IRIS does not depend on any particular model. The agent is a **harness**: IRIS
owns the loop, tools, memory, context and safety rails, and the model only
decides what to say and which tool to call next. To change models, edit `.env`:

```env
AI_PROVIDER=openrouter                  # or openai, groq, together, deepseek, mistral,
AI_MODEL=anthropic/claude-sonnet-4.5    # fireworks, anthropic, nvidia, gemini, ollama,
AI_API_KEY=sk-or-...                    # lmstudio, vllm, openai_compatible (+ AI_BASE_URL)
```

How the harness adapts to each model:

| Layer | What it does | Where |
|---|---|---|
| Capability profile | Detects native tool calling, JSON mode, reasoning output, system-role support, temperature support, token parameter name and context window from the model id; override with `AI_CAPABILITIES` | `app/ai/capabilities.py` |
| Runtime adaptation | If an endpoint rejects `tools`, `response_format`, `temperature`, a system message or `max_tokens`, that capability is turned off and the request retried. The change is remembered for later calls | `app/ai/providers/openai_compatible.py` |
| Output normalisation | Strips `<think>` blocks and `reasoning_content`, markdown fences and prose around JSON; inlines `$ref` schemas for strict tool APIs | `app/ai/structured.py` |
| Self-repair | Invalid structured output is sent back to the model with the validation error to fix (`AI_STRUCTURED_RETRIES`) | `AIProvider.generate_structured` |
| Agent loop | Multi-step: the model sees tool results and can read → decide → act before answering (`AI_AGENT_MAX_STEPS`) | `app/agent/harness.py` |
| Strategy selection | `native_tools` (provider function calling) → `structured_json` (prompted JSON protocol) → deterministic engine | `AgentHarness.run` |
| Safety rails | Parameter validation, tool errors returned to the model, no repeated state changes in a turn, tool output truncated to the context budget, a truthful summary if the model stops partway | `app/agent/harness.py` |

`GET /api/ai/status` shows the active provider, model, strategy and resolved
capabilities. To smoke-test a model live:

```bash
python scripts/verify_live_model.py              # uses .env
AI_PROVIDER=groq AI_MODEL=llama-3.3-70b-versatile python scripts/verify_live_model.py
```

Adding a provider that does not speak the OpenAI protocol means subclassing
`AIProvider` and implementing `chat()`. Structured output, the agent loop and
fallbacks then work with no further changes.

### Awareness & Memory (contextual + personal)

Every chat turn, IRIS gives the model two always-fresh blocks, sized to the
model's context window:

* **Situation** (contextual memory, `app/intelligence/situation.py`): the time
  and current block (and whether it is a hard commitment), next commitment and
  next free window, today's schedule, in-progress / overdue / due-today /
  due-this-week / blocked tasks, the deterministic priority ranking, what got
  done today and this week, goal progress, and what changed since the last
  conversation.
* **Personal model** (external memory, `app/intelligence/personal_model.py`):
  *stated*: profile facts, operating preferences, the weekly routine (recurring
  schedules) and memories in the `ROUTINE`, `WORK_STYLE`, `PREFERENCE`,
  `CONSTRAINT` and `INSTRUCTION` categories; *observed*: patterns learned from
  behaviour (peak hours, active span, best days, throughput, area mix,
  estimate vs. actual, focus-session length and completion rate, self-rated
  productivity). Observed patterns only appear once there is enough data, and
  each carries its sample size.

Memories in other categories (`FACT`, `PEOPLE`, `PROJECT`, `GENERAL`) are
retrieved per message by relevance. The model can go deeper with the
`get_situation`, `get_personal_profile` and `get_completed_tasks` tools, and
saves new routine/work-style facts with `save_memory`.

**One memory across conversations.** Facts live in `ai_memories`; *what was
discussed* lives in each conversation's rolling `summary` (topics, decisions,
plans, open questions). It is refreshed every turn by the same model call that
extracts memories (deterministic fallback offline). Every turn sees the most
recent other conversations plus older ones relevant to the message, and can dig
deeper with `search_conversations` / `get_conversation`
(`app/services/conversation_memory.py`). Requires migration `e7a2c4f19b30`
(`alembic upgrade head`).

| Endpoint | Purpose |
|---|---|
| `GET /api/assistant/situation` | Live situation snapshot |
| `GET /api/assistant/profile` | Personal model (stated + observed) |
| `GET /api/assistant/briefing?narrate=true` | Proactive briefing; with `narrate`, the active model writes a spoken version |

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
