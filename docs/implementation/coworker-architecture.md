# IRIS Coworker Architecture

## Boundaries and reuse

- `IrisSupervisor` remains IRIS's central reasoning and routing authority. Its `recommend_coworker` method ranks only the signed-in user's available coworker records by role fit, required capability grants, and active workload. `/api/coworkers/recommend` exposes that Supervisor decision to the UI.
- Coworkers are persistent, configurable worker records. They do not own global routing or create child supervisors.
- Generic coworker work uses the existing `AIProvider` factory and `AgentHarness`. The coworker receives a per-task tool registry filtered to explicitly granted read-only IRIS capabilities and then rechecked by the governance gateway on every invocation.
- Developer coworkers hand work to Milestone A's `CodingTaskRecord`, `TaskBrief`, Project Registry, brief-review page, coding execution manager, and Antigravity adapter. The coworker creates an `awaiting_approval` coding brief; the CLI does not start until the user approves it through Projects.
- Existing memory, conversations, tasks, model providers, user-scoped IRIS tools and workspace permissions remain authoritative. Coworker outputs are task-specific and do not create a parallel memory store.

## Persistent records

The additive migration `i2a3b4c5d6e7` adds:

- `coworkers`: identity, configurable role, model preference, capability grants, project assignment, availability, status and config version.
- `coworker_tasks`: owner, parent, workspace, objectives, acceptance criteria, dependency IDs, permission scope, status, report and verification evidence. Developer work can link to the existing `coding_tasks` table.
- `coworker_sessions`: provider/model, lifecycle, durable output and error.
- `coworker_events`: append-only lifecycle and governance events exposed through REST.
- `coworker_approvals`: exact action request and narrow decision history.

All records are scoped by `user_id` and all resource lookups filter by the current IRIS user. The current codebase still uses its existing single-user authentication stub; multi-user authentication is not added by this milestone.

## Lifecycle and orchestration

Task transitions are validated in `app/coworkers/contracts.py`. Supervisor recommendations are deterministic and explain when multiple workers are equally suitable. Users can assign directly, ask Supervisor to recommend, create child tasks, add dependent tasks, reassign stopped work, and explicitly retry interrupted work. A dependent task starts after all dependencies complete only when automatic execution was requested. Child reports are aggregated into the parent result. Failed dependencies stop the dependent task with an explicit error.

FastAPI `BackgroundTasks` runs task work using an atomic queued-task claim. This prevents ordinary duplicate starts in one backend process. A backend restart marks running/paused tasks interrupted and preserves the session and output; IRIS does not automatically replay them. The worker loop is process-local, not a durable distributed queue. Generic model execution does not expose provider pause or cancellation controls; queued work can be paused/stopped, active provider calls are not falsely reported as stopped.

The current UI uses REST polling for task status and persisted events. No coworker-specific WebSocket channel is required for correctness. Events report only observed start, tool, approval, result, failure, and recovery transitions; no percentage progress is invented.

## Workspaces and deliverables

Each task may select a registered `CodingProject`; an assigned coworker is restricted to its assigned project. The backend validates owner, active state and read access. Existing project write/command/network settings remain in control. Generic coworker tasks do not receive filesystem, command, email, drive, device or external-network access. Developer tasks produce a user-reviewed Milestone A coding brief and inherit that workflow's workspace checks and reporting.

The Coworkers UI is shared by desktop and Capacitor Android, uses responsive navigation and layout, and links developer task briefs to the existing Projects experience. Android can use host-registered projects under the existing Milestone A limitation.

## Known boundaries

- Generic coworker tools are read-only. Write capabilities requested through the central gateway become a persisted, exact-action approval request; host, command, network, email, drive and device operations are denied until an adapter can enforce their scope.
- Approval actions are only executed after a user decision and are rechecked against the coworker's current grants and project. An approval is limited to the stored action arguments and expires after ten minutes.
- Developer work enters the reviewed coding workflow rather than bypassing it. Status synchronization is lazy and happens when the coworker task is retrieved.
- Antigravity's current Windows host reports terminal sandboxing unavailable. The coworker prepares a reviewed task brief first, and the existing CLI flow uses project-specific command/domain rules and review prompts, but an OS-level filesystem sandbox is not available in this environment. Keep command/network grants narrow; stronger filesystem containment remains future hardening.
- A generic coworker deliverable is persisted with explicit evidence. When acceptance criteria remain unchecked or a capability action fails, it enters `completed_with_issues` and waits for a recorded user review. With no unresolved criteria/actions, `completed` means only that a non-empty deliverable was persisted; `independently_verified` remains false. User acceptance records an attestation and never upgrades independent verification.
