# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Single user: Kirtan — a college student simultaneously managing a college
degree, a paid internship, and building his own startup. One human, all data
private, no multi-tenant concerns. He uses IRIS daily from a laptop/desktop
first, with the phone as a secondary companion surface (PWA on home screen).

## Product Purpose

IRIS is a Personal Operating System / command center for one life. It answers,
from real data:

1. What matters today?
2. What should I do right now?
3. Is anything urgent or falling behind?
4. Am I making meaningful progress (especially on the startup)?

Success = better decisions and real progress (prospects contacted, replies,
meetings, customers), not logged hours. "Progress > Activity."

## Positioning

Not a todo app and not a chatbot: a modular personal OS whose intelligence is
a deterministic priority/time engine with Gemini as a reasoning layer over the
user's actual tasks, deadlines, available time, goals, and startup pipeline.
The same intelligence layer will eventually span future life modules
(finance, email, calendar, drive, habits) — AI is cross-module, not a page.

## Operating Context

- Four life areas today: COLLEGE, INTERNSHIP, STARTUP (strategic priority),
  PERSONAL.
- Daily rituals: morning "what matters today", in-day "what now" (often inside
  limited free windows between classes/internship), evening review, weekly
  reflection.
- Startup operates as an outreach/distribution pipeline run through
  experiments (leads → outreach → replies → meetings → customers).
- Backend FastAPI at `/api` (SQLite) already exists and is the contract; the
  frontend consumes it typed via TanStack Query. Dev servers: Vite :5173,
  API :8000.

## Capabilities and Constraints

Implemented backend capabilities (v1): tasks/projects/goals (hierarchical),
time blocks + calendar events + availability engine, focus sessions, daily
reviews, startup CRM (leads/outreach/experiments), analytics (time /
productivity / funnel), AI endpoints (`recommend`, `plan-day` draft,
`daily-review`, `startup-analysis`, `ask`) with deterministic fallbacks.

Constraints:
- Single-user; auth seam exists but no login UI.
- AI may be unavailable (no key/rate limit): UI must treat `source:
  "DETERMINISTIC"` responses as first-class, never broken states.
- `plan-day` returns drafts only; user explicitly accepts blocks.
- Do NOT implement future modules (finance/email/calendar/drive/habits) —
  architecture must make them pluggable later without redesign. No fake data
  or fake pages for them.

## Brand Commitments

Name: **IRIS** — Intelligent Responsive Information System. Tagline: *"Your
personal command center."* Philosophy: *"Don't just manage your tasks. Manage
your direction."* Voice: direct, quantitative, calm confidence; a serious tool
used every day — never gamified fluff. Visual identity: established fresh
(no existing logo/colors).

## Evidence on Hand

Working seeded backend with realistic development data (college assignments,
internship deliverables, startup outreach history, experiments). Live Swagger
docs at http://localhost:8000/docs. No marketing assets, testimonials, or
press exist; none may be fabricated.

## Product Principles

1. **Command center first** — Home answers "what matters now"; modules hold
   depth, hierarchy beats equality.
2. **Deterministic truth, AI reasoning** — show where an answer came from;
   never present speculation as fact.
3. **Realistic plans** — respect actual free time; impossible schedules are
   bugs.
4. **Progress > Activity** — measure outcomes (replies, meetings, customers),
   not hours.
5. **Modular OS** — configuration-driven module registry; new life domains
   plug in without restructuring.
