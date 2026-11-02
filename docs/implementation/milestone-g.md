# IRIS Milestone G — Conversational Coworker Experience & Autonomous Agent Interaction

**Author:** IRIS Engineering Team & Autonomous Pair Programmer  
**Date:** November 2, 2026  
**Status:** In Progress — Architecture & Implementation  
**Baseline:** `main` at `97b75ad` (Milestone F Complete)  

---

## 1. Executive Summary

Milestone G evolves IRIS coworkers from a rigid, card-based task system into a natural, conversational AI coworker experience. Interacting with an IRIS coworker should feel as intuitive, capable, and seamless as using modern coding agents like Codex CLI or Claude Code.

The user opens any coworker, selects a working directory, and communicates naturally in ordinary language. The coworker understands the user's intent, inspects the project context, determines requirements, formulates its own execution instructions, coordinates the underlying execution engine (Antigravity CLI or Codex CLI), streams progress updates into the conversation, provides an immediate and verified cancellation control ("Stop"), and presents the actual, verified results in a conversational final report.

**Core Principle:** *The conversation is the interface. The coworker is responsible for everything behind it.*

---

## 2. Existing Milestone F Audit & UX Pain Points

### 2.1 Why the Previous Interface Felt Hardcoded and Rigid
1. **Form-Based Disconnection:**
   In Milestone F, the user did not converse with the coworker. The interface presented an "Assign work" form or a multi-field plan card ("Describe Development Task", "Formulate Implementation Plan"). The user had to behave like an operator filling out rigid inputs rather than a developer talking with a coworker.
2. **Boilerplate Brief Templates:**
   Task planning generated hardcoded strings (`architecture="Inspect the project documentation and current architecture before changing code."`, `restrictions=["Do not discard existing changes.", "Do not claim tests ran without evidence."]` rather than dynamically analyzing the actual project repository (frameworks, dependencies, structure, existing patterns).
3. **Execution Control & Cancellation Gaps:**
   In `backend/app/api/routes/coworkers.py`, the cancellation endpoint (`/tasks/{task_id}/cancel`) rejected cancellation with HTTP 409 if the task was running (`"Active provider execution cannot be cancelled safely by the current provider"`). Meanwhile, the coding task stop endpoint (`/coding/execution/tasks/{id}/stop`) was isolated in a different router, making it nearly impossible for users to stop an active execution from the coworker view.
4. **Interface Fragmentation Across Coworker Types:**
   The Developer coworker was rendered via a bespoke `CodingCoworkerWorkspace` filled with complex task cards, whereas other coworkers (Researcher, Analyst, Writer) were rendered with a raw task history list and raw JSON event streams. There was no unified conversational shell.
5. **Context Loss on Follow-Ups:**
   When a user attempted to follow up (e.g., *"Make it more premium and use a dark theme"*), the system either created an unrelated new task or failed because the previous task was marked complete or another task was active on the project.

### 2.2 Reusable Milestone F Infrastructure
Milestone G preserves and builds upon the robust foundations delivered in Milestone F:
- **Git Worktree Isolation Engine (`backend/app/coding/git_workspace.py`):** Automated creation of dedicated worktrees under `.iris_worktrees/` and task-specific branches (`iris/task/<task-id>-<slug>`), with strict push guardrails against `main`, `master`, or base branches.
- **Multi-Agent Adapters (`backend/app/coding/adapters/codex_adapter.py`, `backend/app/coding/headless.py`):** Headless streaming execution for both Antigravity CLI and Codex CLI.
- **Windows Execution Companion:** Local host runtime with process management, environment scrubbing, and filesystem access.
- **Database Architecture:** Supabase PostgreSQL with SQLAlchemy models (`Coworker`, `CoworkerTask`, `CoworkerSession`, `CoworkerEvent`, `CodingProject`, `CodingTaskRecord`).

---

## 3. Unified Conversational Architecture

```
+-----------------------------------------------------------------------------------+
|                        IRIS Unified Coworker Chat Shell                           |
|  - Consistent across ALL coworkers (Developer, Researcher, Analyst, Writer, PM)   |
|  - Working Directory Quick-Selector (persisted per coworker context)               |
|  - Coding Engine Selector (for coding-capable coworkers)                          |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                             Message Stream Component                              |
|  - Natural user & coworker message bubbles                                        |
|  - Live execution progress indicators & elapsed timers                            |
|  - 1-Click visible Stop button & conversational "Stop" intent detection           |
|  - Expandable Technical Diagnostics drawer (collapsed by default)                 |
|  - Final completion reports (files changed, tests, Git branch)                    |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                       Coworker Conversational Backend Engine                       |
|  - Intent Classification (Stop / Question / Development / Follow-up)              |
|  - Workspace Inspection (frameworks, files, git state, empty vs existing app)     |
|  - Dynamic Engine Prompt Synthesis (tailored to user request and repo state)      |
|  - Autonomous Isolated Execution (Git worktree + task branch + engine spawn)      |
|  - Streaming Event Translation (raw engine events -> user-facing progress)        |
|  - Verified Process Cancellation (SIGTERM/kill on companion, worktree preserved)  |
+-----------------------------------------------------------------------------------+
```

### 3.1 Message & Conversation State Model
A coworker's conversation is represented as an intelligent thread of turns:
- Each turn represents a user message (`instruction`), in-flight execution events (`CoworkerEvent`), and the coworker's conversational response (`output`).
- Follow-up turns link back to the parent task (`parent_task_id`), preserving accumulated context, previous design decisions, and active Git worktrees.
- If a task is running, the chat displays the real-time execution state, elapsed time, and an obvious **Stop** button.
- If a task finishes, the coworker provides a comprehensive natural-language report summarizing what was built, files changed, and test outcomes.

---

## 4. Working Directory & Workspace Context Handling

1. **Header Directory Selector:**
   Every coworker interface displays the current working directory in the header:
   `Working Directory: C:\kirtan\IRIS (Active)`
   The user can switch between registered workspaces or register a new directory via 1-click dialog or folder picker.
2. **Backend Validation:**
   The backend validates all directory paths against the registered `CodingProject` records (`user_id = user.id, active = True`). Unregistered filesystem paths cannot be selected by the frontend or model.
3. **Workspace Persistence:**
   The selected workspace is saved to the coworker record (`project_id`), ensuring context is restored across browser refreshes, desktop restarts, and mobile sessions.

---

## 5. Autonomous Coding Execution & Engine Interaction

### 5.1 Project Inspection
Before formulating an implementation plan, the coworker inspects the target repository:
- Determines whether the directory is an empty repository or contains an existing project.
- Identifies the tech stack (e.g., `package.json` -> Vite/React/TypeScript, `pyproject.toml` -> FastAPI/Python).
- Inspects the git branch and working-tree status.

### 5.2 Dynamic Prompt Synthesis
Instead of rigid boilerplate, the coworker generates an implementation prompt tailored to the request:
- Specifies exact files to inspect, modify, or create.
- Pours conversational requirements (e.g., "dark theme", "minimalist", "premium design") directly into the prompt.
- Instructs the engine to run existing project test suites and report concrete outputs.

### 5.3 Worktree Isolation & Engine Spawn
- Creates a dedicated branch: `iris/task/<task-id>-<slug>`.
- Spawns the isolated Git worktree: `.iris_worktrees/<task-id>`.
- Launches the selected engine (**Antigravity CLI** or **Codex CLI**) strictly inside the worktree.
- Streams events into `CoworkerEvent` (`thread.started`, `tool_call`, `item.completed`).

### 5.4 Verified Final Report
When the engine exits, the coworker parses the engine's final response, gathers `git diff <base>..HEAD`, inspects changed files, and produces an authentic report:
```text
Website implementation completed.

Antigravity's report:
- Created the photography portfolio gallery and responsive navigation.
- Applied dark theme aesthetics with smooth typography and minimal borders.
- Added client inquiry contact drawer.
- Verified build: npm run build succeeded with 0 errors.

Files changed: 6
Tests: Passed (Vite build + TypeScript check)
Branch: iris/task/8f31a-photo-portfolio

The implementation is ready for review in the isolated branch.
```

---

## 6. Execution Control & Cancellation

### 6.1 Requirements
A running task must always have an obvious and accessible **Stop** control:
1. **Visible Stop Button:** Displayed in the chat header, the active task banner, and inside the streaming message bubble.
2. **Conversational Stop Intent:** When the user types "Stop", "Cancel this", "Hold on", "Terminate", or "Don't continue", the backend immediately intercepts the message as a cancellation request.

### 6.2 Process Termination Mechanism
1. Looks up the active `CoworkerTask` and linked `CodingTaskRecord` / `CodingSessionRecord`.
2. Signals the Windows companion to terminate the engine subprocess tree (`process.terminate()` -> `process.kill()`).
3. Updates session status to `stopped` and task status to `cancelled`.
4. Guarantees that no Git commit or push occurs after cancellation.
5. Preserves the worktree directory and branch so the user's progress is not discarded.
6. Emits a `task_stopped` event and informs the user in chat:
   *"Task stopped. Process terminated safely and worktree changes on branch `iris/task/...` are preserved. What would you like to do next?"*

---

## 7. Role-Specific Governance Across All Coworkers

The conversational shell is unified, but coworker roles and permissions remain strictly governed:
- **Developer / Coding Coworker:** Granted read, write, and command execution capabilities within assigned Git worktrees.
- **Researcher:** Read-only access to search memory, conversations, and project files. Cannot mutate repository files or push Git branches.
- **Analyst:** Computes insights, metrics, and data summaries without host command access.
- **Writer:** Generates content, documentation, and copy without filesystem write permissions unless explicitly granted.
- **Project Manager:** Tracks tasks, milestones, and schedules across registered projects.

---

## 8. Multi-Device Synchronization (Desktop, Web, Android)

- All messages, task states, and event updates are persisted in Supabase PostgreSQL (`coworker_tasks`, `coworker_events`, `coworkers`).
- Real-time polling and WebSocket mesh ensure that an action started on Android reflects immediately on the Windows desktop app.
- A user can stop a task running on the Windows companion from their Android phone via the `/api/coworkers/{id}/stop` endpoint.

---

## 9. Implementation Execution Summary

1. **Phase 1: Backend Conversational Engine & Stop API** — COMPLETED
   - Implemented `POST /api/coworkers/{id}/chat` endpoint supporting natural conversation, stop intent detection, and dynamic task dispatch.
   - Implemented `GET /api/coworkers/{id}/messages` endpoint providing unified conversation history with event milestones and diff summaries.
   - Implemented robust `POST /api/coworkers/{id}/stop` and updated `/tasks/{id}/cancel` to safely terminate engine processes on the Windows companion (`adapter.stop(manager_key)`).
   - Updated `run_coworker_task` in `backend/app/coworkers/execution.py` to inspect workspaces, generate dynamic engine prompts, create isolated Git worktrees, and autonomously launch execution.
2. **Phase 2: Unified Conversational UI Component** — COMPLETED
   - Created `frontend/src/features/coworkers/CoworkerChatView.tsx` as the single unified conversational shell for all coworkers.
   - Incorporated sticky header with coworker avatar, status indicator, working directory selector (+ Add Workspace button), engine picker (`antigravity-cli` vs `codex-cli`), and coworker profile settings toggle.
   - Implemented message bubbles, live progress indicator, elapsed timer, visible Stop button, and collapsible technical details drawer.
   - Included bottom composer with multi-line input, voice dictation, directory indicator, and active execution warning banner.
   - Replaced rigid card view in `CoworkersPage.tsx` with `CoworkerChatView`.
3. **Phase 3: Antigravity & Codex Autonomous Execution Integration** — COMPLETED
   - Connected live execution event streaming and diff collection (`git status --porcelain`, `git diff --stat`) to conversational bubbles.
   - Implemented conversational final report generation from actual CLI outputs and verification steps.
4. **Phase 4: Multi-Device Sync & Testing** — COMPLETED
   - Verified backend test suites: 45 passed out of 45 tests in 19.87s.
   - Verified frontend TypeScript check and Vite production build (`npm --prefix frontend run build`): 0 errors, compiled in 5.38s.
   - Verified desktop synchronization (`node scripts/sync-desktop.cjs; node --check desktop/main.cjs`): 0 errors.

---

## 10. Verification & Test Results

### Backend Test Matrix (`pytest`)

```
backend/tests/coding/test_antigravity_adapter.py::test_adapter_initialization_and_mock_run PASSED
backend/tests/coding/test_antigravity_adapter.py::test_adapter_missing_binary PASSED
backend/tests/coding/test_antigravity_adapter.py::test_adapter_process_execution_real PASSED
backend/tests/coding/test_antigravity_adapter.py::test_adapter_stop_process PASSED
backend/tests/coding/test_antigravity_adapter.py::test_adapter_get_metrics PASSED
backend/tests/coding/test_codex_adapter.py::test_codex_adapter_initialization PASSED
backend/tests/coding/test_codex_adapter.py::test_codex_adapter_missing_binary PASSED
backend/tests/coding/test_codex_adapter.py::test_codex_adapter_mock_run PASSED
backend/tests/coding/test_codex_adapter.py::test_codex_adapter_stop_process PASSED
backend/tests/coding/test_codex_adapter.py::test_codex_adapter_metrics PASSED
backend/tests/coding/test_conpty_wrapper.py::test_conpty_wrapper_initialization PASSED
backend/tests/coding/test_conpty_wrapper.py::test_conpty_read_timeout PASSED
backend/tests/coding/test_conpty_wrapper.py::test_conpty_mock_process PASSED
backend/tests/coding/test_conpty_wrapper.py::test_conpty_write_input PASSED
backend/tests/coding/test_conpty_wrapper.py::test_conpty_terminate PASSED
backend/tests/coding/test_diff_collector.py::test_collect_diff_clean_repo PASSED
backend/tests/coding/test_diff_collector.py::test_collect_diff_with_modified_file PASSED
backend/tests/coding/test_diff_collector.py::test_collect_diff_with_untracked_file PASSED
backend/tests/coding/test_diff_collector.py::test_collect_diff_max_bytes_limit PASSED
backend/tests/coding/test_diff_collector.py::test_collect_diff_nonexistent_dir PASSED
backend/tests/coding/test_git_workspace_manager.py::test_create_and_cleanup_worktree PASSED
backend/tests/coding/test_git_workspace_manager.py::test_list_worktrees PASSED
backend/tests/coding/test_git_workspace_manager.py::test_branch_isolation PASSED
backend/tests/coding/test_git_workspace_manager.py::test_multiple_concurrent_worktrees PASSED
backend/tests/coding/test_git_workspace_manager.py::test_push_to_branch_policy PASSED
backend/tests/coding/test_session_manager.py::test_session_create_and_get PASSED
backend/tests/coding/test_session_manager.py::test_session_heartbeat PASSED
backend/tests/coding/test_session_manager.py::test_session_complete PASSED
backend/tests/coding/test_session_manager.py::test_session_cleanup_stale PASSED
backend/tests/coding/test_session_manager.py::test_session_list_active PASSED
backend/tests/coding/test_windows_companion.py::test_companion_initialization PASSED
backend/tests/coding/test_windows_companion.py::test_companion_status PASSED
backend/tests/coding/test_windows_companion.py::test_companion_execute_and_stream PASSED
backend/tests/coding/test_windows_companion.py::test_companion_cancel_execution PASSED
backend/tests/coding/test_windows_companion.py::test_companion_list_active_processes PASSED
backend/tests/api/test_coding_execution_api.py::test_list_registered_projects PASSED
backend/tests/api/test_coding_execution_api.py::test_create_and_get_coding_task PASSED
backend/tests/api/test_coding_execution_api.py::test_list_sessions PASSED
backend/tests/api/test_coding_execution_api.py::test_companion_status_endpoint PASSED
backend/tests/api/test_coworkers.py::test_list_and_create_coworker PASSED
backend/tests/api/test_coworkers.py::test_coworker_task_lifecycle PASSED
backend/tests/api/test_coworker_conversational.py::test_coworker_chat_dispatch PASSED
backend/tests/api/test_coworker_conversational.py::test_coworker_messages_endpoint PASSED
backend/tests/api/test_coworker_conversational.py::test_coworker_stop_intent_phrase PASSED
backend/tests/api/test_coworker_conversational.py::test_coworker_stop_endpoint PASSED

======================== 45 passed in 19.87s ========================
```

### Frontend Build Verification

```
> tsc --noEmit && vite build

vite v6.4.5 building for production...
✓ 2368 modules transformed.
✓ built in 5.38s
```

### Desktop Synchronization

```
> node scripts/sync-desktop.cjs; node --check desktop/main.cjs
Synced frontend assets and Electron main/preload/security files.
Syntax check passed with exit code 0.
```

---

## 11. Architectural Compliance & Safety Guarantees

1. **Single Vercel Project & Deployment:** No extra microservices, external worker containers, or separate cloud projects were created.
2. **Git Worktree Isolation:** All coding tasks continue to run on dedicated Git worktrees under `iris/task/<task_id>-<slug>`. No execution touches `main` or uncommitted user work.
3. **No Direct Protected Branch Push:** Push endpoints reject direct pushes to base or protected branches.
4. **Safe Process Termination:** Immediate process group termination on Windows companion prevents zombie CLI processes or orphan background threads.
5. **No Terminal Form Requirements:** Users interact exclusively through natural conversation, while technical logs, diffs, and verification metrics remain accessible on demand in expandable drawers.
