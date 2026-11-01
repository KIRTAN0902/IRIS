# IRIS current-state audit (Phase 0)

Audit date: 2026-10-31. Evidence is the checked-in repository; historical product documents were not treated as proof of implementation.

## Architecture and status

| Area | Current implementation | Evidence / reuse | Status and gaps |
|---|---|---|---|
| Supervisor / intent routing | FastAPI application aggregates domain APIs; AI routes and multi-agent settings exist. | `backend/app/main.py`, `backend/app/ai/`, `backend/app/api/routes/assistant.py`, `intelligence.py` | No demonstrated single execution supervisor connecting intent to governed coding tasks. |
| Model abstraction | Provider factory, provider protocol, Gemini, NVIDIA, OpenAI-compatible and mock providers; settings include fallback and retries. | `backend/app/ai/factory.py`, `provider.py`, `providers/`, `config.py` | Core can be reused. Actual provider routing/fallback is configuration and code dependent. |
| Capabilities/tools | AI capability/tool definitions and a Windows desktop execution registry with policy classification, approval tokens, output scrubbing and postcondition verification. | `backend/app/ai/capabilities.py`, `tools.py`, `backend/app/execution/` | Desktop policy is not automatically a workspace permission boundary for the Antigravity paths. |
| Memory / conversations | SQLAlchemy AIConversation/AIMessage/AIMemory models; conversation search, summaries, transcript and memory services. | `backend/app/models/ai_conversation.py`, `backend/app/services/conversation_memory.py`, `memory_service.py`, `context_builder.py` | Reusable; no project-specific retrieval binding identified. |
| Tasks / projects | User-scoped task and project CRUD backed by SQLAlchemy. Project is a life/task grouping (name, description, area, status), not a filesystem registry. | `models/project.py`, `services/task_service.py`, `api/routes/projects.py`, `schemas/project.py` | No path, aliases, workspace permission or git metadata on project records. |
| Coding task execution | `autonomous_coder_service` starts Google Antigravity SDK work asynchronously; statuses/output only in process memory. | `services/autonomous_coder_service.py`, `api/routes/coding.py` | Hard-coded workspace shortcuts and fallback to IRIS root; no approval gate; not durable; completion means SDK response ended, not verification. |
| Antigravity terminal | `agy_bridge` maintains PTY/pipes, streams output, accepts prompts/slash input, monitors quiet periods, collects git diff and stores a completion memory. | `services/agy_bridge.py`, `api/routes/agy.py`, `frontend/src/features/agy/` | Independent from coding task service; active sessions are in memory; quiet-time completion heuristic; no durable recovery. |
| Voice / vision | Separate provider-backed voice, streaming, screen and vision services/API routes. | `backend/app/ai/voice*`, `services/vision_service.py`, `api/routes/{voice,vision}.py` | Existing feature families should remain intact. |
| Mesh / devices | Mesh relay/hub plus Windows/Android device registries and executors. Lifespan starts local relay where applicable. | `services/mesh*`, `devices/`, `api/routes/mesh.py`, `main.py` | Separate from coding lifecycle; relay excluded on Vercel/Lambda. |
| Desktop process execution | Electron main/preload; backend Windows shell/process/filesystem/app execution registry and policies. | `desktop/main.cjs`, `desktop/preload.cjs`, `backend/app/execution/` | Broad desktop command capability exists; coding work should use explicit selected workspace and permission scoping. |
| Android | Vite/React frontend with Capacitor Android configuration; Android build/release artifacts present. | `frontend/capacitor.config.ts`, `frontend/package.json`, `android-release/` | No native Android coding-agent execution implementation identified. |
| Persistence / API | FastAPI, SQLAlchemy, SQLite default and psycopg support; API routes grouped in `main.py`. | `core/database.py`, `core/config.py`, `api/routes/` | Coding tasks/sessions are not DB persisted. |

## Baseline

- Backend pytest attempt: could not run; active Python is 3.13 and `pytest` is not installed (`No module named pytest`). No test outcome is inferred.
- Frontend build attempt: blocked before project compilation by Node environment access error (`EPERM` resolving `C:\Users\shahk\AppData`); Node reports it could not determine installation directory. No build outcome is inferred.
- The repository has backend API, service, integration, AI, execution, device, ambient and voice/vision test suites. A checked-in `backend/requirements-dev.txt` declares pytest tooling.
- No source files or runtime configuration were changed for baseline attempts.

## Relevant dependencies and known limitations

See `dependency-and-license-audit.md` for manifest-level status. Exact transitive license inventory was not available from these manifests alone.

## Implementation state update

The coding workspace registry and governed execution API are implemented as described in `milestone-a-progress.md`. The headless adapter persists the CLI conversation ID and resumes by that ID where supported. Structured result events determine completion; legacy PTY completion inference is not used by the managed adapter. A background persistence loop now writes headless output/events/status independently of the Projects screen polling.

The current workflow persists project-scoped tasks/sessions, Git preflight snapshots, and structured CLI events. It retrieves small README context and relevant conversation summaries for review. Headless CLI permission requests that require interactive approval are soft-denied and surfaced for a user follow-up. Agent-reported test outcomes remain distinct from independent verification. Legacy SDK launches have been disabled at the API boundary because they bypass the review flow; the service module remains for compatibility investigation but is no longer reachable from the public launch route.

The deprecated SDK coding runner is no longer exposed as a launch route, and its `google-antigravity` Python dependency has been removed from the backend runtime requirements. The optional Antigravity CLI continues to require the user's Google sign-in and service terms.

### Milestone A latest status

Ask IRIS now turns explicit requests against a uniquely named registered project into reviewable `awaiting_approval` tasks and links to the Projects UI. A live Antigravity task plus a second-turn follow-up was executed successfully with the existing signed-in CLI; the generated file was independently checked by the verifier. The verifier also caught and drove a fix for child-task/session foreign-key ordering. Current scoped tests pass. Remaining risks include restart recovery end-to-end validation, headless permission questions, and this machine's Antigravity warning that Windows terminal sandboxing is unavailable.
