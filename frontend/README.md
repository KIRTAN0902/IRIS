# IRIS Frontend

The React command center for IRIS — **Intelligent Responsive Information
System**. Built as a modular personal-OS shell, not a task-manager dashboard.

```text
React 18 · Vite 6 · TypeScript · Tailwind CSS 4
TanStack Query · Zustand · React Router · Recharts · Radix primitives
```

## Architecture

```text
src/
├── app/            # App root: providers + routes
├── api/            # THE ONLY layer that talks to the backend
│   ├── client.ts       # typed fetch wrapper, parses the {"error":{...}} envelope
│   ├── endpoints.ts    # one function per backend endpoint, grouped by module
│   └── queryKeys.ts    # central TanStack Query key factory
├── types/          # TypeScript mirrors of the backend Pydantic schemas
├── hooks/          # query/mutation hooks — components never call fetch
├── stores/         # Zustand: UI state (nav fold, ask console) + focus session mirror
├── modules/        # ★ the module registry — navigation & future expansion contract
├── components/
│   ├── layout/     # AppShell: sidebar rail, status strip, mobile nav
│   └── ui/         # primitives: Button, Panel/Lamp/Ladder, Field, Dialog…
├── features/       # one folder per domain; pages compose shared pieces
│   ├── home/       # Command Center (GO panel + Today/Progress/Attention)
│   ├── today/      # urgency axis + plan-day draft/accept flow
│   ├── tasks/ goals/ schedule/ projects/ focus/
│   ├── startup/    # funnel, lead pipeline, outreach journal, experiments
│   ├── areas/      # College / Internship lenses over shared data
│   ├── insights/   # few charts, high signal
│   ├── modules/    # the "More" bay view (live + planned modules)
│   └── ai/         # Ask IRIS console — the cross-module intelligence layer
├── lib/            # formatting helpers (naive-UTC handling, urgency labels)
└── styles/         # design tokens (Mission Ops Wall) + browser-surface theming
```

### Module registry (the expansion contract)

`src/modules/registry.ts` is the single source of truth for navigation. Each
module is data:

```ts
{ id, name, icon, route?, category, enabled, brief? }
```

- The sidebar, mobile nav, and Modules page all render **from the registry** —
  adding a life domain (Finance, Email, Calendar, Habits…) means adding one
  entry plus a feature folder. No shell surgery.
- `enabled: false` entries are **planned bays**: announced honestly on the
  Modules page, never rendered as fake pages or fake data.
- Future integrations (Google Calendar, Gmail…) register here when their
  backends exist.

### AI is a layer, not a page

- **Ask IRIS console** overlays every route (`⌘K` / floating button), grounded
  by the backend's context builder.
- The **GO panel** (Home) renders `POST /api/ai/recommend` with its provenance
  chip (`AI` vs `AUTO`) and confidence; `Start focus` chains straight into a
  focus session.
- **Plan-day** (`Today`) treats AI output as a draft: each block is accepted
  explicitly before a time block is created.
- Every AI failure degrades to the deterministic answer with an `AUTO` chip —
  the UI never shows a broken state for AI downtime.

### Backend contract

- All datetimes arrive as **naive UTC** strings; `lib/format.ts#parseUtc`
  converts at the presentation edge. Naive UTC strings are sent back for
  window queries (`toNaiveUtc`).
- Errors always arrive as `{"error":{"code","message"}}`; `ApiError` carries
  both. Components render `ErrorState`, never raw exceptions.
- Single-user v1: no auth UI; the backend resolves the default user.

## Design system

**Mission Ops Wall** — recorded in `../DESIGN.md`. Summary: abyssal
blue-black ground with a subtle scanline; hairline panels, zero radius, zero
shadows; color is status semantics only (GO green / caution amber / critical
red / AI cyan as provenance); Chakra Petch display + Barlow body + JetBrains
Mono tabular telemetry; segmented progress ladders; one authored motion (the
breathing status lamp).

## Development

```bash
npm install
npm run dev        # http://localhost:5173 (proxies /api → 127.0.0.1:8000)
```

The FastAPI backend must be running (`uvicorn app.main:app --port 8000` from
`../backend`). Seed it first: `python scripts/seed.py`.

```bash
npm run build      # tsc --noEmit + vite build
node scripts/capture.mjs   # screenshot all routes at exact viewports (uses local Edge)
```

## PWA

`public/manifest.webmanifest` + theme color + apple-touch icon are wired.
Install-to-home-screen works today; a service worker (offline cache) is
deliberately deferred until the deployment target exists.

## Scripts

- `scripts/capture.mjs` — full-route screenshots into `../.impeccable/review/`
- `scripts/layout-probe.mjs` — reports any element wider than the viewport
