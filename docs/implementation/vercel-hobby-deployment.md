# IRIS Vercel Hobby Deployment Compatibility

## Executive summary

IRIS can use Vercel Hobby for the Vite web frontend and a bounded subset of the existing FastAPI API. The existing `api/index.py` entrypoint, root Python requirements file, frontend API client, and SQLAlchemy serverless connection mode already provide most of the deployment structure. This implementation fixes serverless startup side effects, prevents SQLite from being treated as persistent serverless storage, prevents local coworker/Codex execution from being falsely accepted on Vercel, and tightens CORS.

Vercel is not the execution host for IRIS's process-owning capabilities. Coding CLI sessions, project-directory access, coworker workflows, Mesh local process control, and durable background work require a persistent IRIS host. There is now an execution-provider boundary; the Vercel runtime reports those operations unavailable with `EXECUTION_PROVIDER_UNAVAILABLE`. A remote worker transport is not yet implemented. For full IRIS execution, keep the FastAPI service on a persistent host and point the frontend at it, or add a remote provider adapter in a later change.

**Deployment status: compatible for web frontend and short-lived API requests, with deployment prerequisites and security limits. Not ready for an unprotected public production launch.** The current backend uses a single-user identity stub rather than user authentication. Hobby's Vercel Authentication can protect all deployment URLs, including production; enable it before deploying personal data. Android/native clients cannot use Vercel's browser login gate as API authentication and should continue using a separately authenticated/persistent API endpoint.

## Existing deployment architecture and audit

- Frontend: React/Vite in `frontend`; Vercel builds to `frontend/dist`.
- API: `api/index.py` exports the existing `app.main.app` FastAPI app after adding `backend/` and repository root to `sys.path`.
- Python dependencies: repository-root `requirements.txt` is the Vercel dependency manifest. `api/requirements.txt` is a legacy duplicate and is not relied upon by the root deployment.
- Local development: `frontend/vite.config.ts` proxies `/api` and `/companion` to `localhost:8000`; backend remains runnable with Uvicorn.
- Browser API URL: `VITE_API_URL` is the existing build-time override. Without it, web uses same-origin `/api`; Capacitor has its own existing API default.
- Persistence: `backend/app/core/database.py` already uses SQLAlchemy `NullPool` for Vercel/Lambda and PostgreSQL transaction poolers. SQLite remains supported locally.
- CORS: settings are environment-driven. Capacitor origins are explicit. A development-only origin regex previously allowed arbitrary HTTP(S) origins with credentials; it is removed.
- Startup: the previous FastAPI lifespan bootstrapped users/recovery and started process-local Agy, headless persistence, and relay services even on Vercel. Serverless instances now skip those persistent-host operations.
- Background execution: coworker routes previously scheduled work with FastAPI `BackgroundTasks`, and task workers could spawn dependent tasks in-process. These are not durable queue semantics. Vercel run/launch actions now fail closed until a persistent execution provider is available.
- Files: Mesh uploads wrote to a local directory and returned URLs, which would not be durable across Function instances. Uploads now report execution/storage-provider unavailable on a serverless host.
- Authentication: current `current_user` is a single-user development-era stub; it is not an authenticated identity boundary. Do not expose data-bearing API routes publicly without Vercel deployment protection or real application authentication.
- Existing `VERCEL.md` contained outdated claims and a project-specific database connection template. It now points here, leaving this as the sole Vercel deployment guide.

### Architecture compatibility table

| Component | Vercel compatible? | Reason | Required action |
|---|---|---|---|
| React/Vite frontend | Yes | Static assets and client routing | Build from repository root using the checked-in Vite configuration. |
| FastAPI REST APIs | Partially | Python FastAPI runs as a Function; request must fit runtime limits and app must avoid process-local assumptions | Use existing `api/index.py`; deploy with Python 3.12, persistent PostgreSQL, and the configured route rewrites. |
| Short AI requests | Yes, bounded | Network-bound model calls can complete inside a Function invocation | Keep provider deadlines below the 300-second Hobby ceiling; handle timeout/error through current API envelopes. |
| Multi-step AI/coworker execution | No, not as a durable job | Request-scoped `BackgroundTasks` and process memory are not durable | Use a persistent IRIS backend/worker. Serverless execution routes return an explicit unavailable error. |
| Database access | Yes with a remote persistent database | Existing SQLAlchemy `NullPool` and psycopg configuration supports serverless connection lifetimes | Set `DATABASE_URL` to PostgreSQL. Vercel requests refuse SQLite and `/health` reports degraded if only SQLite is configured. |
| Memory and conversations | Yes if database-backed | Rows persist in the existing database; process caches do not | Configure the persistent database. Do not rely on local files or process caches as canonical memory. |
| Coworker execution | No with the current Vercel process | Coworker runner, dependent-task spawning, and progress are process-local | Keep execution on a persistent host. A remote dispatch adapter is future work. |
| Codex/Antigravity CLI | No | Launches local subprocesses against configured project directories and retains live session state | Use the existing backend on a persistent desktop/VPS host; do not approve coding tasks on Vercel. |
| WebSockets / streaming | Limited | Current Vercel docs support Python ASGI WebSockets with Fluid Compute, but Hobby connections end at 300 seconds and new connections may reach different instances | Reconnect and persist shared state externally. Existing voice may serve a short session; current in-memory Mesh hub is not a durable multi-instance relay. |
| File processing | Limited | Function request/response payload limit is 4.5 MB; local writable scratch space is temporary and instance-local | Keep small request-scoped processing only. Durable Mesh uploads require external persistent storage or a persistent API host. |
| Background jobs / schedules | No for current in-process loops | An invocation is not an always-running worker | Existing loop/daemon startup is skipped on Vercel. No paid queue/cron dependency was added. |
| Desktop integration | No | Electron, Windows process control, and local workspace access require the desktop host | Keep desktop's current API/native configuration; use a persistent IRIS backend for these capabilities. |
| Android integration | Partially | Android can call ordinary REST APIs and use existing Capacitor origins; web deployment protection is not native-client API authentication | Keep the current independent Capacitor API setting or point it to an authenticated persistent API. |

### API route-family assessment

FastAPI registers these current route families; paths are relative to `/api` except root routes:

| Route family | Vercel class | Notes |
|---|---|---|
| `/health`, `/docs`, `/redoc`, `/openapi.json`, `/companion`, `/mesh/companion` | Bounded HTTP | Explicitly routed. Health rejects ephemeral SQLite as persistent storage. |
| `/users`, `/tasks`, `/goals`, `/projects`, `/schedule`, `/focus`, `/reviews`, `/startup`, `/analytics`, `/finance`, `/habits`, `/workouts`, `/diary`, `/ui-orchestrator` | Database REST | Compatible with PostgreSQL and within request duration limits. |
| `/ai`, `/intelligence`, `/chat`, `/assistant` | Provider-backed | Short model calls fit; host process, oversized file, or long task capabilities do not. |
| `/email`, `/drive` | External API | Can run when provider credentials are configured; not live-tested. |
| `/voice/transcribe`, `/voice/speak`, `/voice/speak/stream`, `/vision/ingest` | Bounded media/provider | Subject to the 4.5 MB Function payload ceiling; no background capture is implied. |
| `/voice/live` WebSocket | Bounded WebSocket | Python ASGI support on Fluid Compute; 300-second Hobby ceiling, reconnect required, live provider not tested. |
| `/agy/*`, `/agy/stream/*` | Persistent process/session | Workspace and process state require the execution host. HTTP controls return unavailable; stream closes with 1013 on serverless. |
| `/coding/execution/*` | Persistent process/workspace | Project registration and process-mutating actions are guarded; task drafts/lists remain database based. |
| `/coworkers/*` | Mixed | Records/approvals are database APIs. Execution submission is unavailable without a persistent provider. |
| `/mesh/ws`, `/mesh/screen/*`, `/mesh/command`, `/mesh/terminal/*`, `/mesh/app/launch` | Persistent device/relay | Local hub is not shared across Function instances; device execution needs the separate relay/desktop host. |
| `/mesh/files/*` | Persistent file storage | Upload is unavailable on serverless because local disk is not durable or shared. |

## Vercel runtime and configuration

The current Vercel Python runtime supports FastAPI ASGI apps and recognizes `api/index.py` exporting `app`. The existing entrypoint is correct; no duplicate backend or `tool.vercel.entrypoint` is needed. Vercel's Python runtime is documented as Beta, supports Python 3.12–3.14, and installs dependencies from root `requirements.txt`. The repository now pins `.python-version` to 3.12, which also satisfies `backend/pyproject.toml`'s `>=3.12` requirement. See [Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python) and [FastAPI on Vercel](https://vercel.com/kb/guide/ship-a-fastapi-app-on-vercel).

`vercel.json` retains the existing root project structure and configures:

- Framework: `vite`.
- Build command: `cd frontend && npm ci && npm run build`.
- Output directory: `frontend/dist`.
- Function entry: `api/index.py`, `maxDuration: 300`, `region: sin1`.
- Rewrites from `/api/*`, `/health`, `/docs`, `/docs/oauth2-redirect`, `/redoc`, `/openapi.json`, `/companion`, and `/mesh/companion` to the existing FastAPI app; remaining routes fall through to the SPA entry.

The 300-second setting is the current Hobby maximum, not a promise that every operation should run that long. Vercel lists a 4.5 MB request/response payload maximum for Functions. Hobby WebSockets are supported by the current Vercel documentation when Fluid Compute is enabled, but each connection closes at its function duration; reconnect and shared-state requirements still apply. See [Function limits](https://vercel.com/docs/functions/limitations) and [WebSockets on Vercel Functions](https://vercel.com/kb/guide/do-vercel-serverless-functions-support-websocket-connections).

### Vercel dashboard settings

For a new Vercel project, configure:

1. Import the repository from its Git provider.
2. Set **Root Directory** to `./` (repository root).
3. Select **Vite** as the framework preset. Keep the checked-in build command and output directory from `vercel.json`; do not set `frontend/` as the project root, because that would hide `api/index.py` and root `requirements.txt`.
4. Set the project region to `sin1` if the dashboard offers a conflicting override; the repository function config already selects it.
5. Enable **Security → Deployment Protection → All Deployments → Vercel Authentication** before placing personal data on the deployment. Current Hobby support includes protection for production domains. This is platform access protection, not an IRIS API user/session implementation. See [Deployment Protection](https://vercel.com/docs/deployment-protection) and [Vercel's production protection announcement](https://vercel.com/changelog/protect-production-deployments-for-free-on-every-plan).
6. Deploy a preview first and verify the listed routes and health response before promoting it. No live deployment was performed in this audit.

## Environment-variable reference

Set secrets in Vercel Project Settings → Environment Variables. Vite variables are compiled into browser assets and must never contain secrets.

| Variable | Scope | Purpose |
|---|---|---|
| `DATABASE_URL` | Vercel server | Required persistent PostgreSQL connection URL. Prefer the provider's transaction pooler where available; the app uses `NullPool` in serverless. Never use SQLite for Vercel. |
| `ENVIRONMENT=production` | Vercel server | Disables development CORS behavior. |
| `SECRET_KEY` | Vercel server | Set a fresh random secret; do not use the example value. |
| `CORS_ORIGINS` | Vercel server | JSON array of exact trusted browser origins. For same-origin Vercel web, no Vercel origin is needed. Add `https://localhost` and `capacitor://localhost` only for the bundled Capacitor API calls, and exact web origins if frontend and API use separate domains. Never use `*`. |
| `DEFAULT_TIMEZONE` | Vercel server | Existing user timezone, e.g. `Asia/Kolkata`. |
| `LOG_LEVEL` | Vercel server | Optional operational log level, normally `INFO`. |
| `AI_PROVIDER`, `AI_MODEL`, provider key | Vercel server | Configure only the chosen existing provider. Provider credentials remain backend-only. |
| `VITE_API_URL=/api` | Vercel build, Production and Preview | Explicit same-origin API base for browser bundles. If the API is hosted elsewhere, use its absolute URL ending in `/api` and permit the Vercel site origin in that API's exact CORS list. |
| `IRIS_API_URL` / Capacitor API setting | Android/Electron build environment | Existing native build configuration remains independent of Vercel; use a reachable API URL. Do not set the browser build variable as a substitute for native deployment configuration. |

Do not add `.env` files to Vercel or commit credentials. The checked-in `.gitignore` excludes `.env` variants. Vercel's environment variables are injected into the server function; variables prefixed `VITE_` are public build-time values.

## Database, migrations, and persistence

The current database engine already detects Vercel and uses SQLAlchemy `NullPool`, `pool_pre_ping`, and psycopg's disabled prepared-statement threshold for the PostgreSQL transaction pooler. This avoids retaining idle SQLAlchemy pool connections across function lifetimes. Each request still gets a closed SQLAlchemy session through `get_db`.

On serverless runtime, the database dependency now rejects SQLite with error code `DATABASE_CONFIGURATION_REQUIRED`; `/health` does not attempt a SQLite connection and returns `status: degraded` with a database diagnostic until a persistent database is configured. This prevents a successful response backed by disposable local function storage. Conversations, memory, tasks, UI state, and other database features still depend on a reachable existing PostgreSQL database.

Migrations are not run from the FastAPI lifespan or on every invocation. Run the existing Alembic migration chain once from a trusted operator environment using `backend/alembic` and a direct/session-pooler migration URL (`MIGRATION_DATABASE_URL`, `DIRECT_DATABASE_URL`, or `DATABASE_URL_UNPOOLED`, as supported by `backend/alembic/env.py`). Example from repository root after setting the private migration URL in the shell:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m alembic upgrade head
Pop-Location
```

Do not print or place the migration URL in this document. No database migration was added for Vercel compatibility.

## Execution-provider boundary and persistent-host path

`backend/app/core/execution_provider.py` introduces a vendor-neutral `ExecutionProvider` status contract. The current local provider keeps local development behavior and reports unavailable in Vercel/Lambda/serverless mode. Coworker `run`, auto-run, and run-on-follow-up requests check the provider before changing task state or scheduling a request-bound background task. Coding-agent approve/follow-up/resume/stop and local project registration require the coding execution provider. Agy session controls reject serverless process access; its WebSocket closes with code 1013. Mesh file upload requires persistent file storage and returns unavailable in serverless mode. Errors use the standard API envelope and code `EXECUTION_PROVIDER_UNAVAILABLE` with an actionable reason.

The API process still serves bounded REST operations and durable task records through PostgreSQL. It does not enqueue work into a fake in-process Vercel background task. No remote queue, Redis, SaaS, or paid dependency was added. The provider protocol is the intended seam for a future authenticated remote dispatch adapter.

For the current fully supported persistent execution path, run the existing FastAPI service on a persistent host with its normal local execution services and PostgreSQL, then set the web `VITE_API_URL` to that host's `/api` URL at build time. Add the exact Vercel frontend origin to the persistent API's `CORS_ORIGINS`. Keep Electron and Capacitor endpoint configuration separate. A hybrid where Vercel handles REST and a remote host accepts only execution jobs needs a remote provider transport and server endpoint; that is explicitly not implemented or claimed here.

## WebSockets, streaming, and file limits

Current official Vercel docs support Python ASGI WebSockets in public beta with Fluid Compute. Hobby connections are capped by the Function's 300-second maximum. A reconnect may reach another function instance; process-local presence and `mesh_service.hub` are not shared across instances. IRIS's current Vercel deployment can therefore handle short, request-scoped/individual WebSocket sessions only when the request finishes inside that bound. It is not a durable device mesh, background voice listener, or multi-instance broadcast service. Persist shared state/pub-sub and implement reconnect/resubscription before relying on those features at scale.

Streaming responses can be used for bounded provider calls, but all work remains constrained by the invocation duration. Function request/response payloads are capped at 4.5 MB; the existing vision service's larger configured image ceiling does not override Vercel's platform cap. Mesh File Vault uploads are disabled on Vercel because its local storage path is not durable or shared. Use a persistent API/storage provider for larger or durable files.

## CORS, security, and identity

- Production CORS accepts only explicit `CORS_ORIGINS` plus the two existing Capacitor local origins. Development keeps only explicit localhost Vite origins; the open credentialed origin regex was removed.
- Same-origin Vercel browser API traffic does not require CORS. For split frontend/API origins, configure exact origins on the API service.
- FastAPI route-level ownership, coworker governance, and approval checks are unchanged; frontend visibility does not grant access.
- The existing single-user identity stub is not authentication. Vercel Authentication with **All Deployments** can protect the browser deployment and its API at Vercel's edge, but native clients cannot treat that browser gate as application credentials. A publicly accessible API still needs real app authentication before a public launch.
- Vercel's request size and timeout limits are platform boundaries; do not relax application permissions to fit them.
- Existing upload handlers and local project paths are not made durable or safe by deploying them as a Function. Local project execution is guarded.

## Local development and deployment commands

Local development remains unchanged:

```powershell
# Terminal 1, from repository root
Push-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
Pop-Location

# Terminal 2, from repository root
Push-Location frontend
npm.cmd run dev
Pop-Location
```

Vite proxies `/api` to the local backend. To locally test Vercel routing, install the CLI and authenticate in your own shell, then run `vercel dev` from repository root; the CLI was not installed in the audit environment, and no deployment was made. For deployments, Vercel Git integration is preferred. CLI commands when configured are:

```powershell
vercel             # preview deployment
vercel --prod      # production deployment; run only after you choose to publish
```

This audit did not invoke either deployment command.

## Files created or modified

- Added `.python-version` to pin Vercel's Python runtime to 3.12.
- Added `backend/app/core/execution_provider.py` for the runtime/provider boundary.
- Updated `backend/app/main.py` to skip process-local recovery and managers on serverless; removed permissive development CORS regex.
- Updated `backend/app/core/database.py`, `backend/app/core/errors.py`, and `backend/app/api/routes/health.py` to reject serverless SQLite configuration safely.
- Updated coworker, coding execution, and Mesh upload routes to fail explicitly when the local persistent execution provider is unavailable.
- Updated root `requirements.txt` to include existing `google-antigravity` runtime dependency already declared by `api/requirements.txt`; verified its license metadata as Apache-2.0. No Python package was newly introduced to the project dependency set.
- Updated `frontend/package-lock.json` with `npm audit fix` semver-compatible updates (no `--force`, no `package.json` change): Vite 6.4.3→6.4.5, Puppeteer Core 25.8.0→25.16.0, source-map-js 1.2.1→1.2.2, Zod 3.25.76→4.6.7, Capacitor CLI 8.5.3→8.6.0 and compatible transitive updates. These remove all 5 high audit findings.
- Updated `vercel.json` to use lockfile installation and route FastAPI docs/companion aliases through the function.
- Added `backend/tests/api/test_deployment_runtime.py`.
- Replaced outdated root `VERCEL.md` content with a pointer to this canonical deployment document.
- No database migration, frontend package, Electron, or Capacitor code changed.

## Tests and exact results

Executed in this workspace:

| Command | Result |
|---|---|
| `backend\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp=$env:TEMP\iris-vercel-full-final -q --tb=short` (from `backend`) | **549 passed, 0 failed, 4 warnings** in 477.57s. Warnings are existing Starlette 422 deprecation and three naive `datetime.utcnow()` deprecations in existing tests/services. |
| `backend\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp=$env:TEMP\iris-vercel-target-verified tests\api\test_deployment_runtime.py -q --tb=short` (from `backend`) | **10 passed**. Covers execution/provider checks, SQLite fail-closed behavior, serverless lifespan, CORS origin filtering, coworker auto-run rejection before task mutation, Agy process controls, and protection against a serverless status request marking another host's coding task interrupted. |
| `backend\.venv\Scripts\python.exe -m compileall -q app ..\api` (from `backend`) | Passed; backend and Vercel entrypoint Python files compile. |
| `npm.cmd ci` followed by `npm.cmd run build` (from `frontend`) | Passed on the final audited lockfile; `npm ci` installed 300 packages and reported the same six moderate residual advisories. Vite 6.4.5 TypeScript/Vite build passed, transforming 2,367 modules; main chunk 432.56 kB (135.35 kB gzip). npm warned that the `esbuild` install script was not in the local script allowlist; the native package resolved and the build passed. |
| `npm.cmd audit --json` (from `frontend`) | Before safe fixes: 13 total (5 high, 8 moderate). After non-breaking fixes: **6 moderate, 0 high, 0 critical**. Remaining advisories concern React Router 6 and Capacitor CLI transitive `glob`/`minimatch` chains; npm's proposed fixes require major-version changes, so no `--force` upgrade was made. |
| `.\gradlew.bat assembleDebug` (from `frontend/android`) | **BUILD SUCCESSFUL**, 97 tasks up-to-date. This is an APK build result, not device/emulator runtime verification. |
| `node --test desktop/security.test.cjs` plus `node --check` for Electron main/preload/security files | **3 passed**, syntax checks passed. Desktop has no packaging/build command in `desktop/package.json`; Electron runtime was not launched. |
| Python entrypoint smoke with `VERCEL=1`, `AI_PROVIDER=mock`, and SQLite | `api/index.py` imported the existing FastAPI app; `/health` returned HTTP 200 with `status=degraded` and database `unconfigured_or_unreachable`; verified the function does not report ephemeral SQLite as durable. |
| `git diff --check` and `vercel.json` JSON/limit assertion | Passed; JSON parses, duration is 300, output is `frontend/dist`, and build command uses `npm ci`. |

An initial non-escalated clean install attempt failed because Windows denied access to a global npm cache file outside the workspace and left `node_modules` empty. A local cache attempt confirmed registry access is restricted in the sandbox. The authorized install then succeeded and restored the frontend dependencies; no user dependency directory is left missing. The Vercel CLI is not installed, so Vercel's own validator was unavailable. No live Vercel deployment was performed.

## Known limits and future migration path

1. This deployment does not provide a durable worker queue or remote dispatch transport. Extend `ExecutionProvider` and add a token-authenticated host endpoint before splitting Vercel API from a worker. Until then, point the app to the persistent API host for coding/coworker operations.
2. Do not use SQLite, local file vault storage, process caches, or local project directories as serverless persistent state.
3. WebSocket support exists on Vercel, but the 300-second Hobby ceiling and non-shared in-memory Mesh state prevent treating it as persistent device coordination.
4. Function request/response payloads are limited to 4.5 MB.
5. User authentication remains a single-user stub. Vercel Authentication can protect browser deployment URLs, but it does not replace native API authentication or IRIS authorization.
6. The final npm audit still reports six moderate findings in the existing React Router 6 and Capacitor CLI dependency trees. Safe semver fixes removed all high findings; remaining fixes require major upgrades.
7. Hobby is documented for personal, non-commercial projects. Confirm current [Hobby plan terms and limits](https://vercel.com/docs/plans/hobby) before use.
8. A live Vercel deployment, DB integration, Vercel CLI validation, Android runtime through Vercel, and production authentication were not verified.

## Final deployment-readiness checklist

- [x] Existing FastAPI app is exported from recognized `api/index.py` entrypoint.
- [x] Root Python dependency manifest covers the API's current runtime dependencies.
- [x] Python version pinned to supported 3.12.
- [x] Function duration is within Hobby's documented 300-second maximum.
- [x] Serverless startup no longer starts process-local daemons or user/task recovery writes.
- [x] Serverless SQLite use is rejected and health is degraded when no persistent DB is configured.
- [x] Local execution-dependent operations fail explicitly rather than pretending to run.
- [x] CORS no longer permits arbitrary credentialed development origins.
- [x] Frontend has an explicit existing `VITE_API_URL` setting; Vercel should set it to `/api` for Production and Preview.
- [ ] Vercel Hobby deployment itself verified: not run (CLI unavailable; user asked for compatibility work, not a live publish).
- [ ] Real application authentication: not implemented; use Vercel All Deployments protection for personal web access and do not expose native/API traffic publicly.
- [ ] Durable remote execution-provider transport: not implemented; persistent API host remains required for coding/coworker execution.

**Readiness assessment:** ready to create a protected Vercel preview for static frontend and short-lived REST testing after setting a persistent PostgreSQL URL and server secrets. Not ready for unprotected public production use, native clients routed through Vercel Authentication, or persistent coding/coworker/Mesh execution.
