# IRIS architecture map (observed)

```text
Desktop Electron shell ─┐
Android Capacitor app ───┼─> React/Vite frontend ─HTTP/WebSocket─> FastAPI backend
Browser frontend ────────┘                                    │
                                                               ├─ API routes -> domain services -> SQLAlchemy -> SQLite/Postgres
                                                               ├─ AI routes -> provider factory -> model providers
                                                               ├─ coding routes -> autonomous coder -> google.antigravity SDK (in-memory)
                                                               ├─ agy routes/WebSocket -> PTY bridge -> agy CLI (in-memory)
                                                               ├─ desktop execution registry -> policy -> Windows process/filesystem/apps
                                                               ├─ voice/vision services
                                                               └─ mesh relay + device executors
```

## Main entry points

- Backend: `backend/app/main.py` creates FastAPI, includes API routers and starts Antigravity manager and local Mesh relay in lifespan.
- Backend development daemon: `backend/run_daemon.py`; container setup: `backend/entrypoint.sh`, `backend/Dockerfile`.
- Frontend: `frontend/src/main.tsx` and `frontend/src/app/App.tsx`; Vite config in `frontend/vite.config.ts`.
- Desktop: `desktop/main.cjs`, `desktop/preload.cjs`; frontend packaged/synced by root scripts.
- Android: Capacitor configuration in `frontend/capacitor.config.ts`; Android code/build workspace is not fully represented in the initial file listing.

## Coding execution boundaries as currently wired

1. `/api/coding/tasks` delegates to an SDK-based background task service. The service chooses workspace using a fixed alias map and stores tasks in module memory.
2. `/api/agy/*` delegates to a separate long-lived terminal manager and exposes output over WebSocket. The manager uses configured `agy` command and configured/default directory; it does not share task records with `/coding`.
3. Project CRUD does not establish filesystem authorization. Desktop execution policy is a separate service, not applied as a common workspace governance layer to these paths.
4. Conversation memory and coding completion memory are reusable context sources, but no task brief approval workflow or durable session model is evident.

## Proposed Phase 1 mapping (for review)

- Extend project management with a filesystem project registry only after reconciling existing `Project` semantics; avoid reusing life-planning projects as paths without compatibility analysis.
- Introduce task/session execution contracts in a dedicated coding/execution boundary; preserve current task domain model and both existing Antigravity transports during migration.
- Define adapter capabilities around the existing terminal bridge first. Keep SDK service behavior available until parity and migration are demonstrated.
- Apply selected-workspace checks before launch and keep desktop command policy separate but composable.
- Use existing conversation/memory retrieval selectively when creating a user-reviewed task brief.

## Milestone A implementation mapping

- Ask IRIS routes explicit coding requests for a uniquely mentioned registered project to a persisted `awaiting_approval` task. Ambiguous or missing projects return a project-selection action; the frontend links to the Coding Projects review UI.
- Project records own the selected host directory and read/write/command/network permissions. Electron supplies the directory picker; Android can choose host-registered projects but cannot pass its local Storage Access Framework URI as the Windows CLI workspace.
- `/api/coding/execution/tasks` owns brief review, approval, session persistence, output/status polling, follow-up child tasks, stop, and workspace-scoped resume. Task and session rows are stored through SQLAlchemy; CLI details remain behind the adapter registry.
- The Antigravity adapter uses the installed CLI headless NDJSON transport. The old SDK task launch is disabled. Legacy terminal routes remain for explicitly user-driven sessions, with workspace permission checks; chat-driven Supervisor/Operator prompts no longer bypass task review.
- Mesh, Agy, and Supervisor paths enforce registered workspace ownership before session controls. The core task manager does not depend on Mesh or Electron.

## Milestone B coworker extension

- `Coworker`, `CoworkerTask`, `CoworkerSession`, `CoworkerEvent`, and `CoworkerApproval` extend the existing SQLAlchemy persistence layer through the additive `i2a3b4c5d6e7` migration.
- `IrisSupervisor` remains the single orchestration authority and exposes deterministic coworker recommendations. Generic coworker turns reuse the provider factory, `AgentHarness`, registered IRIS tools, and user/project records; the coworker governance registry filters and rechecks tool access.
- Developer coworkers create a reviewed coding task in the Milestone A execution manager rather than invoking the CLI independently. Completion status synchronization carries coding verification evidence into the coworker task.
- The `/api/coworkers` routes and responsive `CoworkersPage` expose management, recommendations, task history, event polling, approvals, and results. Desktop and Capacitor Android share the page.
- Computer-use is behind a provider interface. The only local demo is explicitly simulated; CUA Spaces components are excluded due to FSL licensing, and host GUI automation was not adopted.
