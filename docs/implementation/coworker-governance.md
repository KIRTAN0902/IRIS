# Coworker Governance and Permissions

## Enforcement path

The backend owns authorization. Model instructions and frontend visibility do not grant access.

1. Coworker configuration stores an explicit IRIS capability allowlist and optional registered project assignment.
2. Task creation checks workspace ownership/read access, coworker project scope, requested capabilities and dependency ownership.
3. The worker advertises only registered, granted, non-mutating tools. `GovernedCoworkerRegistry` calls `evaluate_capability` again for each tool invocation and records an event.
4. The API capability gateway rechecks user, coworker, task, project and capability before executing an action.
5. A state-changing capability creates an approval record containing immutable action arguments. IRIS pauses the task in `waiting_approval`; approval/rejection is audited. Approval expires after ten minutes and does not authorize other calls.
6. Tool failures and verification status are stored as returned by the existing IRIS tool.

## Allowed and denied actions

- A coworker may use a registered, user-scoped read-only capability only when it is listed in its own grant. Tasks may narrow this set further.
- A registered mutating capability may be requested through the governed invocation endpoint. It is not exposed to the model's task harness today. User approval executes only that stored action; current IRIS tool schema, ownership, validation and verification still apply.
- Host commands, filesystem/desktop access, Antigravity fast-path controls, Mesh/device control, email, cloud drive, and other external or unconfined tools are denied to coworker tasks. The generic capability registry does not provide enough coworker-level filesystem/network confinement to safely allow them.
- A project reference does not grant project writes. The Project Registry's existing `read_access`, `write_access`, `command_access`, allowed commands/domains and network access remain authoritative for coding execution.
- The `permission_profile` is configuration metadata only; it cannot elevate permissions. Enforcement uses actual project records and `allowed_capabilities`.

## Approval record

Records include requester coworker, task, capability, exact arguments, reason, status, approver label, decision reason, expiry and decision timestamp. Approval requires the task and coworker to remain owned by the current user and the permission check to still pass. Rejection cancels the waiting task. Expired approvals are closed and cannot be reused.

IRIS currently has a local single-user auth stub, so the approver label is `local-user`. A future authenticated multi-user system must replace it with a verified principal identifier.

## Isolation and recovery

Generic coworker execution has no host process or filesystem primitive. Workspace references are read-only context identifiers until the existing Developer-to-Coding workflow explicitly uses its selected directory after user approval. This is the isolation boundary implemented now; no container runtime is silently assumed.

On this Windows host, the installed Antigravity CLI reports terminal sandboxing unavailable. Developer coworkers therefore create only a reviewed Milestone A coding task; any CLI launch still uses that workflow's selected-project permissions and review prompts. IRIS does not claim an OS-enforced filesystem sandbox here. Keep command/domain rules narrow; do not grant broad host commands or network access. A stronger OS-level filesystem boundary remains a security hardening item.

On restart, active tasks/sessions become `interrupted`. Retry is explicit and dependency state is checked again. The application does not replay work that might repeat a destructive action. Active generic model calls cannot be safely paused or forcibly cancelled through the current provider API; queued work can be paused or cancelled and developer sessions use Milestone A's supported controls.

## Security tests

`backend/tests/api/test_coworkers.py` covers denied ungranted and host-command capabilities, narrow approval and rejection, expired approval, owner scoping paths, restart recovery, lifecycle validation, developer handoff, and the mock computer-use boundary. Run the focused suite and broader regressions listed in `milestone-b-test-report.md`.
