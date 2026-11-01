# Known issues and risks (Phase 0)

1. **Two separate Antigravity implementations.** SDK execution and CLI PTY execution have unrelated lifecycle state and API routes. Reconcile before adding another abstraction.
2. **Workspace selection is unsafe/inconsistent for coding.** SDK service has hard-coded names and silently falls back to the IRIS directory; CLI bridge has its own directory/alias settings. No common project allowlist/permission model was identified.
3. **No review-before-submit workflow.** `/api/coding/tasks` accepts instruction and launches immediately. The terminal bridge accepts raw prompts directly.
4. **Execution state (baseline finding).** The original coding task dictionary and legacy PTY sessions were in process memory. Milestone A adds persisted task/session records and background output/event snapshots for the managed headless adapter; recovery after a real IRIS restart still needs end-to-end validation.
5. **Completion claims are weak.** SDK task sets COMPLETED when response iteration ends. PTY bridge infers completion from a quiet output window and its git report does not establish that tests ran or passed.
6. **Terminal control surface.** The legacy Agy endpoints and Mesh Antigravity controls now require registered project scope and read/write/command permissions as applicable. They remain a lower-level compatibility surface outside the reviewed task lifecycle, so use the reviewed coding execution API for tasks.
7. **Project model mismatch.** Existing projects are user life/task groupings and lack directory paths, aliases and workspace permission fields.
8. **Build baseline unavailable in current shell.** Pytest absent; Node setup blocked by sandbox access to user AppData. Retry with the documented environment once available.
9. **CLI contract not verified.** This Phase 0 audit did not inspect the installed Antigravity executable/version or validate its flags, continuation, cancellation or approval behavior. This must precede adapter implementation.
10. **Licensing evidence is incomplete.** Runtime manifests identify direct dependencies but do not pin all Python ranges or provide a complete transitive license report. `google-antigravity` exact package licensing and whether its CLI/runtime requires proprietary service/subscription remain unverified; investigate before adoption as a required dependency.

## Milestone A implementation attempt (2026-10-31)

Partial implementation is present; see Phase 1 entry above. Phase 0 documentation was updated with installed CLI evidence and service-term concern. The work is **not complete** and does not meet all milestones. Backend checks remain blocked by missing FastAPI/pytest in active Python environment. Frontend Vite/TypeScript build passed. No coding-agent task was launched against a project during implementation.

## Implementation note

The reviewed execution workflow lives under `/api/coding/execution/tasks`; the legacy `/api/coding/tasks` SDK launch returns HTTP 410. Legacy `/api/agy/*` and Mesh Antigravity terminal controls require registered workspace scope and project permission checks, but do not provide the same reviewed task lifecycle. Use the reviewed API for coding tasks.

The Supervisor and Operator's older chat-driven Antigravity prompt paths are now blocked; their attach/status/slash operations are workspace-permission scoped. The interactive `/agy` terminal API remains available as an explicit user-controlled interface for registered workspaces.

## Follow-up implementation state

Reviewed task endpoints live under `/api/coding/execution/tasks` to avoid collision with the old route. The legacy direct SDK launch returns HTTP 410, and the legacy Agy transport now requires a registered workspace plus matching project permissions. These changes are tested. Tool-level permissions and structured approval handling remain incomplete; the CLI bridge only requests review-mode settings and streams terminal text. See the milestone progress log for the latest suite outcome and remaining gaps.

The Antigravity headless controller is implemented using documented NDJSON events and result statuses. The real verification script at `backend/scripts/verify_coding_e2e.py` has now passed against the already signed-in CLI when run with access to its local profile. It verified a first edit, independent file inspection, persisted follow-up session and expected final contents. A sandboxed invocation could not access the CLI profile; that was an execution-environment restriction rather than missing user sign-in.

On this Windows machine the CLI also reports terminal sandboxing is unavailable because the required Windows security environment is missing. IRIS requests review mode, restricts non-workspace access, and applies per-project command/domain rules, but headless CLI requests that require interactive approval can only be surfaced as waiting for user input; this machine's OS-level terminal sandbox warning remains a security deployment limitation.

The additive migration has been applied to the configured PostgreSQL database; `alembic current` confirms the new revision is at head. The migration-flow tests also pass against SQLite.
