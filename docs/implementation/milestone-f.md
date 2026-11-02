# IRIS Milestone F — Coding Coworker & Multi-Agent Workspace

**Author:** IRIS Engineering Team & Autonomous Pair Programmer  
**Date:** November 2, 2026  
**Status:** Completed & Verified — Production Ready  
**Baseline:** `main` at `d5fbf39`  

---

## 1. Executive Summary

Milestone F transforms IRIS's existing coding-agent infrastructure into a unified **Coding Coworker** experience. Rather than requiring users to operate terminal decks, manually construct agent prompts, or manage Git branches, IRIS provides a specialized software development coworker. Users interact via natural language chat on desktop or mobile, review and approve structured implementation plans, and delegate execution to officially supported coding engines (Antigravity CLI and Codex CLI).

Execution security is guaranteed by backend-enforced Git workspace isolation: every task executes in a dedicated Git worktree and task-specific branch (`iris/task/<task-id>-<slug>`). Direct pushes to `main`, `master`, or the user's active branch are strictly denied by code. Terminal interaction is removed from normal user-facing flows while retaining the underlying ConPTY and execution companion infrastructure for diagnostics.

---

## 2. Existing Architecture Audit

### 2.1 Core Infrastructure Reused
- **FastAPI Backend:** Single unified backend serving REST and WebSocket endpoints. Single Vercel deployment model preserved.
- **Supabase PostgreSQL:** Central durable storage with SQLAlchemy models and Alembic migrations.
- **Windows Execution Companion:** Local Python 3.13 process with access to local filesystem, Git binary, Antigravity CLI, and Codex CLI.
- **Milestone A Coding Infrastructure:**
  - `backend/app/models/coding_project.py`: `CodingProject` model managing workspace paths, permissions (`read_access`, `write_access`, `command_access`, `network_access`, `allowed_commands`, `allowed_domains`).
  - `backend/app/models/coding_task.py`: `CodingTaskRecord` and `CodingSessionRecord`.
  - `backend/app/coding/contracts.py`: Lifecycle states (`TaskStatus`), transition validation (`TASK_TRANSITIONS`), `TaskBrief`, and `AgentCapabilities`.
  - `backend/app/coding/headless.py`: `HeadlessSession` and `AntigravityHeadlessManager` managing NDJSON streaming.
  - `backend/app/coding/persistence.py`: Background snapshot persistence loop.
  - `backend/app/api/routes/coding_execution.py`: Task drafting, brief review, approval, follow-up, resume, and stop endpoints.
- **Milestone B Coworker Governance:**
  - `backend/app/models/coworker.py`: `Coworker`, `CoworkerTask`, `CoworkerSession`, `CoworkerEvent`, `CoworkerApproval`.
  - `backend/app/coworkers/governance.py`: Read-only capability allowlists and 10-minute action-specific approvals.
  - `backend/app/coworkers/execution.py`: Task worker, supervisor recommendation, and developer handoff.
- **Milestone C & D UX & Mesh:**
  - Shared UI Orchestrator, mobile navigation layout, and Capacitor bridge.

### 2.2 Security Gaps in Pre-Milestone F State
1. **Lack of Worktree Isolation:** In Milestone A, coding agents executed directly inside the user's primary project working directory (`p.directory`). If uncommitted changes were present, agent modifications could conflict with or overwrite user work.
2. **Missing Branch Protection:** There was no backend enforcement preventing an agent from modifying the current active Git branch or touching protected branches.
3. **Terminal-Centric Friction:** The `/agy` terminal deck and manual prompt editing in `/projects` required the user to think like an operator rather than a software collaborator.
4. **Single Engine Binding:** The system was hardcoded to `antigravity-cli`, lacking multi-agent orchestration for Codex CLI or other engines.

---

## 3. CUA Identification and Evaluation

### 3.1 Component and License Audit
- **Repository:** `trycua/cua` monorepo.
- **Evaluated Components:**
  - `cua-sandbox` (0.9.1, MIT): Local container/VM sandbox abstraction.
  - `cua-driver` (0.37.0, MIT): Drives interactive Windows host desktop console/RDP session.
  - `cua-spaces` / `cua-spacesd` (FSL-1.1-MIT): Source-available, non-OSI approved license; excluded per IRIS policy.
  - `cua-perception` (AGPL-3.0): Model weights and OCR; excluded.
- **Local Host State:** The Windows host does not have `cua`, `docker`, or `cargo` installed.
- **Security Assessment:**
  - `cua-driver` operates the actual Windows desktop session with full user privileges. It does **not** provide desktop or filesystem isolation.
  - Driving the Antigravity desktop consumer app via UI automation is unsupported and violates service terms.
- **Decision:** IRIS rejects live desktop CUA automation for coding execution. IRIS retains `MockLocalComputerUse` in `backend/app/coworkers/computer_use.py` for simulated lifecycle demonstration. Browser-based testing is handled via isolated headless Playwright MCP where required, never claiming unverified OS-level isolation.

---

## 4. Coding-Agent Compatibility Matrix

| Engine | Binary / Package | Version | Integration Method | Auth Method | Isolation / Sandbox Support | Streaming & Cancellation | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Antigravity CLI** | `agy.exe` | 1.4.12 | Headless NDJSON (`--input-format stream-json --output-format stream-json --settings <json> --sandbox`) | Google Account CLI login (`agy models` verified) | Terminal sandbox via CLI settings; IRIS enforces Git worktree isolation | Real-time stdout/stderr streaming; process termination on stop | **Fully Supported** |
| **Codex CLI** | `codex.exe` | 0.166.0 | Headless JSONL (`codex exec [PROMPT] --json -C <worktree> -s workspace-write`) | ChatGPT tokens via `~/.codex/auth.json` (verified via `codex doctor`) | Filesystem sandbox (`workspace-write`); native worktree flag; IRIS enforces Git worktree isolation | Real-time JSONL event stream; process termination on stop | **Fully Supported** |
| **Antigravity Desktop App via CUA** | N/A | N/A | UI Automation / Screen scraping | Consumer GUI login | None (operates actual host screen) | None | **Unsupported & Prohibited** |

---

## 5. Final Architecture

```
                 +-----------------------------------------------+
                 |       IRIS User Interface (Web / App)        |
                 | - Coding Coworker Chat (Conversational UI)   |
                 | - Plan & Branch Approval Cards                |
                 | - Event Milestones & Diff Review             |
                 +-----------------------+-----------------------+
                                         |
                                         v
                 +-----------------------------------------------+
                 |       IRIS Coworker & Governance Layer        |
                 | - Coding Coworker Specialist Profile          |
                 | - Task Planning & Engine Selection            |
                 | - Milestone B Governance Gateway              |
                 +-----------------------+-----------------------+
                                         |
                                         v
                 +-----------------------------------------------+
                 |        Git Workspace & Isolation Engine       |
                 | - Preserves user working-tree changes         |
                 | - Creates task branch: iris/task/<id>-<slug>  |
                 | - Creates isolated Git worktree               |
                 | - Enforces branch protections (main/master)   |
                 +-----------------------+-----------------------+
                                         |
                        +----------------+----------------+
                        |                                 |
                        v                                 v
          +---------------------------+     +---------------------------+
          |  Antigravity CLI Adapter  |     |     Codex CLI Adapter     |
          | - Headless NDJSON stream  |     | - Headless JSONL stream   |
          | - Workspace-scoped exec   |     | - Workspace-write sandbox |
          +---------------------------+     +---------------------------+
                        |                                 |
                        +----------------+----------------+
                                         |
                                         v
                 +-----------------------------------------------+
                 |         Result Review & Verification          |
                 | - Diff capture (`git diff <base>..<branch>`)  |
                 | - Test execution verification                 |
                 | - User-approved commit & branch push          |
                 +-----------------------------------------------+
```

---

## 6. Coworker Responsibilities

The **Coding Coworker** operates as a specialized collaborator:
1. **Requirement Analysis:** Conversational intake of user intent; resolves or prompts for target project.
2. **Context Inspection:** Reads project architecture, README, and relevant memory without mutating files.
3. **Plan Formulation:** Formulates a structured brief with objectives, acceptance criteria, constraints, and test requirements.
4. **Engine Selection:** Recommends Antigravity CLI or Codex CLI based on task profile, tool needs, and availability.
5. **Approval Delegation:** Presents brief, branch name, and worktree location for human approval.
6. **Isolated Execution:** Orchestrates execution within the dedicated Git worktree.
7. **Progress Translation:** Converts raw engine events into human-readable milestones.
8. **Verification & Delivery:** Gathers Git diff, test outputs, and verification evidence, presenting a clean review summary with push/merge controls.

---

## 7. Adapter Implementation

A unified adapter interface (`CodingAgentAdapter`) standardizes engine operations:
- `detect() -> dict[str, Any]`: Discovers binary path, version, and availability.
- `launch(directory, prompt, session_id, permissions) -> Any`: Initiates session inside worktree.
- `send_prompt(session_id, prompt) -> Any`: Passes follow-up prompts to the active session.
- `get_status(session_id) -> dict[str, Any]`: Inspects process health and lifecycle state.
- `get_output(session_id) -> str`: Retrieves captured output buffer.
- `stop(session_id) -> bool`: Safely terminates the agent process.
- `resume_session(...) -> Any`: Reconnects to previous session ID where supported.

---

## 8. Git Isolation Design

### 8.1 Worktree Management Flow
1. **Preflight Check:** Validate repository root, current branch, and `HEAD` commit.
2. **Uncommitted Changes Preservation:** If uncommitted changes exist in the user's working copy, they remain untouched in the primary workspace. The task worktree branches off `HEAD`.
3. **Branch Creation:** Creates `iris/task/<task-id>-<slug>` from `HEAD`.
4. **Worktree Creation:** `git worktree add -b <branch-name> <worktree-path> <base-commit>`.
5. **Execution Boundary:** The coding agent's working directory is pinned to `<worktree-path>`.
6. **Diff & Verification:** Once execution finishes, IRIS queries `git diff <base-commit>..HEAD` inside the worktree.
7. **Teardown & Cleanup:** Safe removal via `git worktree remove` upon user review or archival.

### 8.2 Backend-Enforced Git Protections
- **Denied Targets:** Direct push to `main`, `master`, or the base working branch is blocked by backend code with HTTP 403.
- **Force Push Prohibition:** `--force`, `-f`, and destructive ref updates are strictly disallowed.
- **Explicit Branch Push:** Pushing to remote is restricted exclusively to `iris/task/*` branches and requires user approval.
- **Merge Governance:** Merging a task branch requires explicit user confirmation.

---

## 9. Security and Governance

- **Permission Profiles:** Coworker executes with least-privilege capability grants. Write and command actions are gated by the project registry.
- **Approval Tokens:** Task approvals expire after 10 minutes and are strictly bound to the exact task and workspace ID.
- **Environment Scrubbing:** Environment variables containing sensitive keys (`KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `CREDENTIAL`, `AUTH`) are stripped before launching child processes.
- **Path Confinement:** Working directories are validated and canonicalized before process invocation.

---

## 10. Database Changes

No destructive migrations. Existing tables `coding_projects`, `coding_tasks`, `coding_sessions`, `coworkers`, `coworker_tasks`, `coworker_sessions`, and `coworker_events` are reused. Structured workspace metadata (`branch_name`, `worktree_path`, `base_commit`, `commit_hash`, `diff_summary`) are persisted inside `brief` and `result` JSON columns, ensuring zero schema disruption.

---

## 11. UI Changes

- **Primary Navigation:** Replace the terminal `/agy` entry in primary navigation with **Coworkers** / **Coding Coworker**.
- **Conversational Coding Workspace:** Chat stream featuring interactive Task Brief cards, progress milestone feeds, approval modals, and diff summaries.
- **Technical Details Panel:** Optional collapsible drawer for viewing raw process logs, diagnostic warnings, and CLI outputs without cluttering the chat view.
- **Diagnostic Retention:** `/agy` remains accessible under advanced tools for developer troubleshooting.

---

## 12. Mobile and Desktop Integration

- **Android (Capacitor):** Users can start coding tasks, approve briefs, review diff summaries, and monitor progress from their phone. Local execution remains hosted on the Windows execution companion.
- **Desktop (Electron):** Direct integration with local workspace folder pickers and native notifications.

---

## 13. Test Results

### 13.1 Automated Backend Test Suite
All backend tests passed with 100% success rate (`41 passed in 14.78s`):
```text
backend/tests/coding/test_antigravity.py .                                [ 2%]
backend/tests/coding/test_approval_gate.py ...                           [ 9%]
backend/tests/coding/test_codex_adapter.py ...                           [17%]
backend/tests/coding/test_coding_coworker_workflow.py ..                 [21%]
backend/tests/coding/test_git_workspace.py ....                          [31%]
backend/tests/coding/test_multi_agent_isolation.py ...                   [39%]
backend/tests/coding/test_persistence.py ...                             [46%]
backend/tests/coding/test_pty_bridge.py ..                               [51%]
backend/tests/coding/test_sessions.py ...                                [58%]
backend/tests/api/test_coding_execution_api.py .........                 [80%]
backend/tests/api/test_coworkers.py ........                            [100%]
============================== 41 passed in 14.78s ==============================
```

#### Detailed Test Verification Coverage:
1. **Git Isolation & Protection (`test_git_workspace.py`):**
   - Verified automated worktree creation via `git worktree add -b <branch> <dir> <commit>`.
   - Verified that uncommitted changes in the user's primary working tree remain untouched and clean while the agent executes in its dedicated worktree.
   - Verified diff generation via `git diff <base>..<branch>`.
   - Verified strict push guards: direct push to `main`, `master`, or the active user working branch is blocked with HTTP 403 / `PermissionError`.
   - Verified safe worktree removal and branch preservation.
2. **Multi-Agent Adapters (`test_codex_adapter.py` & `test_multi_agent_isolation.py`):**
   - Verified discovery of both `antigravity-cli` (v1.4.12) and `codex-cli` (v0.166.0).
   - Verified capability detection (`workspace_write`, `stream_json`, `worktree_native`).
   - Verified headless manager lifecycle: launch, streaming stdout/stderr parsing, event capture, process termination, and persistence.
   - Verified dynamic engine assignment: tasks targeted to `codex-cli` spawn `CodexHeadlessSession` pinned to the task's worktree.
3. **Coding Coworker Foundation & Governance (`test_coding_coworker_workflow.py`):**
   - Verified `coding_coworker` starter template with least-privilege capability allowlists (`search_conversations`, `search_memory`, `get_conversation`, `get_projects`, `list_coding_tasks`, `get_coding_task_status`).
   - Verified natural-language task planning: auto-resolves target projects, creates isolated brief with task branch `iris/task/<task-id>-<slug>`, and transitions task to `waiting_input` awaiting human review.
4. **API Integration & Persistence (`test_coding_execution_api.py`):**
   - Verified `/coding/execution/tasks/{id}/approve` creates isolated worktrees dynamically.
   - Verified `/coding/execution/tasks/{id}/diff`, `/commit`, `/push`, and `/cleanup` endpoints.
   - Verified snapshot persistence loop captures diffs and engine states.

### 13.2 Frontend & Desktop Verification
1. **TypeScript Typecheck & Production Build (`frontend`):**
   - `tsc --noEmit && vite build` succeeded without warnings or errors (`✓ 2368 modules transformed, built in 19.57s`).
2. **Desktop Sync & Syntax (`desktop`):**
   - `node scripts/sync-desktop.cjs` completed with code 0, syncing all dist assets to Electron build.
   - `node --check desktop/main.cjs` verified valid syntax and IPC message handlers.

---

## 14. Known Limitations & Technical Boundaries

1. **Host-Bound Execution:**
   - Both Antigravity CLI and Codex CLI require the local Windows execution companion. Android devices supervise and approve tasks remotely over HTTPS/WebSocket via the IRIS API.
2. **Filesystem vs. OS Kernel Isolation:**
   - Git worktrees isolate repository files, branches, and commits completely. However, on Windows without a Docker/Hyper-V container boundary, processes share the host OS kernel and user permissions. Process environment scrubbing (`strip_sensitive_env`) is strictly enforced to protect host API credentials.
3. **CUA Automation Rejection:**
   - Controlling consumer desktop GUIs via UI automation is technically fragile, unisolated, and violates provider terms of service. Real desktop CUA automation is officially unsupported and excluded. Headless CLI execution (`stream-json` / `jsonl`) is the only supported execution pathway.
4. **Concurrent Worktree Limitation:**
   - Git does not permit checking out the exact same branch in two different worktrees simultaneously. Each IRIS task creates a unique, dedicated branch name (`iris/task/<task-id>-<slug>`) to avoid checkout collision.

---

## 15. Deployment Compatibility

- **Single Vercel Project Preserved:** Zero secondary Vercel deployments or cloud backends created.
- **Supabase PostgreSQL Compatibility:** Reused existing tables and migrations. Dynamic worktree paths, branch identifiers, diff outputs, and engine selections are persisted in structured JSON columns (`brief` and `result`) without requiring schema alteration.
- **Stateless Cloud, Stateful Companion:** Cloud Vercel functions handle REST routing and auth gating, while long-running agent execution is managed by the local companion background loops.

---

## 16. Verification & Rollout Checklist

- [x] Phase 0 Architecture and Integration Audit completed and documented.
- [x] Phase 3 Isolated Git Execution Engine (`app/coding/git_workspace.py`) implemented and tested.
- [x] Phase 2 Multi-Agent Adapters (`app/coding/adapters/codex_adapter.py`, `app/coding/antigravity.py`) implemented and tested.
- [x] Phase 1 & 5 Coding Coworker Foundation & Governance (`app/coworkers/templates.py`, `app/coworkers/execution.py`, `app/api/routes/coding_execution.py`) implemented and tested.
- [x] Phase 4 & 8 Conversational Coding Coworker UI (`CodingCoworkerWorkspace.tsx`, `CoworkersPage.tsx`, `ProjectsPage.tsx`, `registry.ts`) implemented and built.
- [x] Terminal interaction demoted from primary user workflows to advanced developer diagnostics.
- [x] Zero-push guardrails for `main`, `master`, and base branches verified by automated tests.
- [x] All 41 backend tests green and frontend Vite build verified clean.
