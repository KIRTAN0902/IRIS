# Milestone B Progress

**Overall status:** Completed with documented environment/provider limitations  
**Implementation snapshot:** 2026-11-01

## Phase 4 — Coworker Foundation and Orchestration

**Status:** Completed

### Completed tasks
- Added persistent configurable coworker identities and the Researcher, Developer, Analyst, Writer and Project Manager templates.
- Added validated coworker/task lifecycle transitions and a provider-neutral coworker session record.
- Integrated execution with the existing IRIS provider factory and `AgentHarness`; read-only registered tools are filtered per coworker and rechecked by governance.
- Extended the existing `IrisSupervisor` with coworker fit, availability, capability and workload recommendations. The Coworkers page can request this recommendation or let the user assign directly.
- Added parent tasks, dependency gating, explicit retries/reassignment/follow-up, child result aggregation, parallel independent task execution and failure propagation.
- Added persistent structured task, tool, approval, completion, failure and recovery events.
- Developer coworkers create an `awaiting_approval` Milestone A coding brief and link to the existing Projects approval/execution workflow.

### Modified files and services
- `backend/app/models/coworker.py`, `backend/app/coworkers/`, `backend/app/agent/supervisor.py`
- `backend/app/api/routes/coworkers.py`, `backend/app/main.py`, `backend/app/models/__init__.py`
- Additive migration `backend/alembic/versions/i2a3b4c5d6e7_add_coworker_ecosystem.py`
- `frontend/src/features/coworkers/CoworkersPage.tsx`, `frontend/src/app/App.tsx`, `frontend/src/modules/registry.ts`

### Verification
- Coworker lifecycle, persistence, recommendations, task assignment, dependency sequencing/failure, approval, workspace denial, restart recovery, developer handoff, deliverable review and mock CUA coverage is in `backend/tests/api/test_coworkers.py`.
- Focused coworker test suite: 16 passed.
- Final full backend suite: 521 passed, four environment-bound Windows desktop failures. Frontend and Capacitor Android sync passed; exact evidence is in `milestone-b-test-report.md`.

### Known limitations
- Generic model execution has no provider-level active-call pause or cancellation. Queued work can be paused/cancelled; active calls are surfaced honestly.
- Developer work is delegated through Milestone A's reviewed coding workflow; generic coworkers cannot write project files directly.
- The existing single-user authentication stub remains the user identity boundary.

## Phase 5 — Workspaces, Tools, Permissions and Governance

**Status:** Completed

### Completed tasks
- Coworker/task workspaces reference user-owned, registered Milestone A projects and honor project read/write controls.
- Central capability evaluation checks user-owned coworker/task records, exact capability grants, project access and action risk.
- Read-only user-scoped IRIS tools are available to the task harness. Unconfined host command, desktop, device, network, email, drive and coding tools are denied.
- Mutating tool requests through the gateway create an exact-arguments approval record. Approval/rejection/expiry is persisted and audited; approval is single-action and short-lived.
- Persisted sessions, outputs, event history, approvals and explicit restart recovery are implemented. Recovery never silently replays an active task.
- Coworkers UI includes roles, status, task/result history, events, workspace assignment, Supervisor recommendation, approvals, retry/stop controls and responsive desktop/mobile layout.
- Coworker archive retains task and event history.
- Completion reporting distinguishes persisted deliverables from user-reviewed acceptance: unresolved criteria or failed tool actions remain `completed_with_issues`; user review is persisted without claiming independent verification.

### Verification
- Positive and denied permission tests plus narrow approval and expiry tests are in the coworker API suite.
- Migration `i2a3b4c5d6e7` was applied to the configured PostgreSQL database and `alembic current` reported the new head.
- SQLite migration chain also upgraded through `i2a3b4c5d6e7`.

### Known limitations
- Mutating tools are not advertised to the coworker model harness; an action can only be requested through the governed invocation API. This keeps the current generic harness from advancing past an approval boundary.
- Coworker events are retrieved through REST polling, not a dedicated WebSocket stream.
- The generic execution queue is process-local FastAPI background work, not a distributed durable queue. Persisted work is recoverable by inspection and explicit retry.

## Phase 6 — CUA Evaluation and Governed Computer-Use Prototype

**Status:** Completed (real CUA rejected; labelled mock contract demo verified)

### Completed tasks
- Evaluated CUA SDK/CLI, Driver, sandbox SDK, Spaces/daemon, CUA-S1, Bench and optional perception boundaries, including current upstream licence split and Windows requirements.
- CUA runtime was not installed on the host; current local probe found `cua`, Docker and Cargo unavailable. CUA Driver would control the interactive host desktop rather than isolate a coworker environment.
- CUA Spaces and current Cua Spaces daemon use FSL-1.1-MIT and are excluded. No CUA dependency was added.
- Added provider-neutral `ComputerUseProvider` operations and an explicitly-labelled local mock contract demo with persisted test evidence. It performs no real GUI action.

### Decision
- **Reject** production CUA integration for this host/milestone. The compliant safe demonstration is the mock provider; its output is always labeled as simulated.
- Full evidence is in `docs/implementation/cua-evaluation.md`.

### Remaining limitations
- The Windows host's Antigravity report says terminal sandboxing is unavailable. Developer coworkers do not launch coding work directly: they create a reviewed Milestone A task brief, whose execution still depends on existing workspace command/domain policy and Antigravity review. Avoid broad command/network rules; a stronger OS-level filesystem boundary remains a future hardening need.
- Real GUI control was not demonstrated because CUA and Docker are not installed and the Driver controls the host interactive desktop. The mock is clearly labelled and is not presented as real computer use.
- Four existing Windows desktop regression tests cannot pass here because VS Code is missing and Windows denies Brave/Windows Terminal access. The failures and exact evidence are in the test report.
