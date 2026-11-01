
## Implementation progress update — 2026-10-31

**Overall status:** Completed with documented environment and provider limitations.

### Phase 0 — Repository audit and baseline
**Status:** Completed (audit artifacts recorded). Baseline tests were unavailable in system Python, then rerun from `backend/.venv`.

### Phase 1 — Contracts
**Status:** Completed. Task/session lifecycle contracts, legal transitions, adapter capabilities, permissions and structured events are implemented. The PostgreSQL migration is applied and verified at head; transition, persistence and resume paths have API coverage.

### Phase 2 — Project registry and workspaces
**Status:** Completed. Registered directory management, user scoping, aliases, read/write/command/network permissions, Electron directory picker, ambiguity handling, active workspace selection, recent access, relevant context retrieval, directory validation and Git preflight are implemented. Android selects host-registered workspaces because Android content URIs cannot be used as the Windows CLI working directory.

### Phase 3 — Antigravity controller
**Status:** Completed; live task and follow-up acceptance demonstrated. CLI 1.4.12 is integrated through the adapter registry. Brief approval, headless NDJSON output, background session persistence, follow-up, stop and conversation-ID resume are implemented. Live E2E created and independently checked a file, then completed a follow-up and verified the final contents. Unsupported interactive approvals are surfaced as waiting for user input.

### Checks
- `frontend`: `npm run build` passed; Vite reported existing dynamic import/chunk-size warnings.
- `backend`: focused coding/API/migration tests passed (8 passed).
- Backend compileall and Alembic heads check passed.
- Full suite with workspace-local temp path: 491 passed, 4 failed. All four failures are in pre-existing Windows desktop/device tests that expect local applications/browser/Windows Terminal access unavailable in this sandboxed run. No errors occurred; 8 pre-existing warnings remain.
- Desktop `node --check` passed for `main.cjs` and `preload.cjs`.
- No coding-agent task was launched in this turn.

### Follow-up fixes (2026-10-31)
- Split reviewed execution task endpoints to `/api/coding/execution/tasks`; fixed the route collision with legacy task launch.
- Disabled legacy direct SDK launch with HTTP 410 and updated coverage. Legacy `/agy` routes now expose/attach/control only registered projects, enforce read/write/command permissions, and gate WebSocket sessions against the registry.
- Managed CLI sessions request Antigravity's `request-review` tool policy. Resume uses the installed CLI's workspace-scoped `--continue` behavior; arbitrary conversation-ID recovery is not claimed.
- Task draft now captures a concise README excerpt and relevant conversation summaries, and snapshots Git branch/working-tree state. Approval refuses a Git state change since draft creation.
- Added tests for approval permission gates and ambiguous alias resolution.
- Focused coding/legacy-Agy/migration suite: 10 passed. Full backend suite after changes: 493 passed, 4 failed, no errors; same four environment-bound Windows desktop/device tests. Frontend production build passed, with existing bundle warnings.

**Security and completion gaps still open:** The CLI does not provide structured approval events through this PTY bridge. Its review prompts appear only as terminal output and IRIS cannot reliably correlate/resolve them. `request-review` is requested but network permissions and individual tool approvals are not centrally enforced by IRIS. Output is only snapshotted while polling; restarts rely on `--continue` for the latest workspace conversation. Agent-reported completion and quiet-window completion are not independent verification. The approved E2E workflow has not yet been demonstrated against a real coding task.

### Additional completion work
- Resolved the conflicting `/coding/tasks` registrations by separating the new reviewed lifecycle under `/api/coding/execution/tasks`; disabled direct legacy launch at `/api/coding/tasks` with HTTP 410.
- Restricted legacy `/api/agy` sessions to registered, user-owned workspaces with read/write/command checks, including WebSocket access.
- Managed Antigravity processes now use session-local settings requesting review, enabling the CLI terminal sandbox, and denying access outside workspace folders. The CLI documents that sandbox enforcement is ineffective when unavailable, so request-review remains the fallback.
- Context now includes a bounded README excerpt and up to three relevant prior conversation summaries. Git branch and working-tree state are captured at draft time and checked again at approval.
- Final focused suite after these changes: 9 passed. Full suite: 493 passed, 4 environment-dependent Windows tests failed (run preceded two final adapter tests); frontend build, Python compile, migration head, desktop JS syntax, and diff whitespace checks passed.

**Still not complete:** Real Antigravity execution and follow-up demonstration; structured agent tool-approval/questions; agent capability choosing beyond one installed adapter; direct network permission enforcement; robust durable output and exact session recovery; actual test-command evidence; active workspace/recent projects UI; Android directory selection; supervisor intent-routing integration; production database migration verification. Phase statuses remain In progress.

## Headless controller and current end-to-end status (2026-10-31)

The adapter now uses the installed CLI's documented headless NDJSON protocol rather than treating terminal quiet time as structured completion. It captures `init` conversation IDs, response deltas, tool events and final result status, supports multiple prompts per conversation, persists event/output snapshots during status polling, and can resume by conversation ID. Process diagnostics redact detected secrets. CLI settings request review, enable the terminal sandbox, deny access outside project folders, apply per-project command allow rules and deny web URL actions unless project network access/domains are explicitly enabled. Unsupported permission requests in headless mode can be soft-denied; diagnostics are surfaced as warnings and a waiting state instead of being reported as success.

The actual end-to-end verification script is `backend/scripts/verify_coding_e2e.py`. It creates a disposable project, registers it, drafts and approves a small file change through the API, independently reads the result, sends a follow-up, and checks the follow-up output. An initial sandboxed run could not access the signed-in CLI profile and incorrectly surfaced the CLI's unauthenticated path; running with access to the existing local profile resolved this. The real end-to-end run passed: Antigravity created `FIRST_OK`, IRIS independently checked it, the follow-up completed, and the file contained `FIRST_OK` followed by `SECOND_OK`.

### Latest checks
- Focused coding contracts/adapter/API/migration suite: 16 passed.
- Mesh API, relay and dispatch suites: 21 passed after fixing the relay's no-event-loop coroutine warning; only the sandbox pytest-cache permission warning remains.
- Latest combined coding/Supervisor/Ask/Mesh/migration regression suite: 59 passed.
- Frontend production build passed (existing Vite dynamic-import and chunk-size warnings).
- Python compileall, Alembic head, desktop JavaScript syntax, and `git diff --check` passed.
- Full backend suite after the persistence changes: 505 passed, 4 environment-dependent Windows desktop/device failures (VS Code/Brave/Windows Terminal are unavailable or access denied in the sandbox); 6 warnings.

### Documented limitations
- This Windows host reports Antigravity terminal sandboxing unavailable. IRIS keeps non-workspace access disabled and uses request-review plus per-project command/domain allow rules; avoid broad command or network permissions on this host.
- Headless Antigravity cannot display interactive approval UI. Unsupported requests are soft-denied and surfaced for a user to adjust scoped permissions and send a follow-up.
- Android cannot register an on-device content URI as the Windows CLI workspace; it can choose projects registered on the host.
- Four unrelated Windows desktop/device tests fail because VS Code, Brave and Windows Terminal are unavailable or access denied in the sandbox.

### Latest hardening follow-up
- Fixed task resume to load and validate the persisted session before attempting CLI continuation.
- Resume now refuses to start a duplicate process while the original Antigravity session is still active; stale running tasks are recorded as interrupted before recovery.
- Fixed follow-up child/session persistence ordering after the live E2E uncovered a foreign-key failure; added a regression test.
- Legacy Mesh Antigravity control now requires an active paired device plus a registered workspace, and checks read/write/command permissions for attach, input and slash commands in both direct Mesh WebSockets and the laptop relay daemon.
- The Mesh relay sync broadcast no longer creates an unawaited coroutine when called without a running event loop.
- Live Antigravity end-to-end verification passed, including a first task, independent file read, persisted follow-up child session and final file contents.
- Ask IRIS now routes explicit coding requests for an unambiguous registered project into an `awaiting_approval` draft and provides a direct link to review it; ambiguity and missing-project cases return to project selection.
- Scoped the Supervisor's legacy Antigravity fast paths and Operator session tools to registered projects; chat-originated coding prompts through those old paths are refused and directed to reviewed task creation.
- Revalidated after these changes: 59 combined coding/Supervisor/Ask/Mesh/migration tests passed; compileall, Alembic head, frontend build, desktop syntax and diff checks passed.
- Full backend run after persistence/resume changes: 505 passed, 4 environment-dependent Windows desktop/device failures; same unavailable/access-denied VS Code, Brave and Windows Terminal cases seen earlier.
- Applied the additive migration to the configured PostgreSQL database and verified `alembic current` reports `h1a2b3c4d5e6 (head)`.
- Latest coding execution API tests after duplicate-resume protection: 5 passed.
- A backend snapshot loop now persists Antigravity output, conversation IDs, statuses and structured events to PostgreSQL once per second, independent of Projects UI polling; it also records completion/failure state and tool-reported changed paths. Added a no-API-poll regression test.
- Adapter now distinguishes a live process from a retained completed session; completed-session follow-up resumes by the saved Antigravity conversation ID. Added tests for active-session duplicate protection and interrupted-session inspection/resume.
- Live E2E passed again with the persistence loop and completed-session follow-up behavior in place: both tasks completed and the verifier read `FIRST_OK` and `SECOND_OK` from the selected workspace.
- Latest affected backend regression suite after persistence and resume changes: 33 passed.

The deprecated SDK runner remains in source for compatibility investigation but is no longer a public execution path; its Python SDK dependency has been removed from runtime requirements. The new headless CLI adapter is the supported path.
