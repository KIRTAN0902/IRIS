# IRIS — Overall UX Simplification, Product Normalisation & Interaction Efficiency Audit

**Document:** `docs/implementation/iris-ux-simplification.md`  
**Date:** November 2026  
**Status:** Implemented & Verified in Production Build  
**Core Principle:** *Every user action must require the minimum reasonable effort. Make IRIS do the complicated work internally; make user interaction feel obvious, natural, and effortless.*

---

## 1. Complete Product Audit Across All Modules

A top-to-bottom interaction and architectural audit of IRIS was performed across every user-facing surface:

| Module | Primary Responsibility | Audit Findings & Friction Points |
| :--- | :--- | :--- |
| **Home (`/`)** | Executive overview & instantaneous interaction (`IrisSphere`, Orchestrated Dashboard, and Chat composer). | Previously displayed raw UI orchestrator debug options, temporary widget prompt inputs, and required navigating multiple controls. Streamlined to answer 3 questions immediately: (1) *What needs attention?* (2) *What is happening now?* (3) *What should I do next?* |
| **Conversations (`/conversations`)** | Chronological past conversational threads and history lookup. | History listing was clean, but lacked immediate jump-to-action shortcuts. Now acts as a frictionless thread catalog with instantaneous 1-click continuation. |
| **Coworkers (`/coworkers`)** | Specialised AI team members (Developer, Researcher, Analyst, Writer, Project Manager). | **Severe friction identified:** Split-screen layout mixed directory, templates, and active conversations in an overcrowded 3-column view. Developer coworker exposed manual "Local PC vs Remote Cloud" toggles, manual engine selectors (`antigravity-cli` vs `codex-cli`), and manual tunnel URL inputs. **Now replaced with two-level hierarchy:** Level 1 Directory (`/coworkers`) and Level 2 Dedicated Full-Page Chat (`/coworkers/:id/chat`) operating remotely by default. |
| **Projects (`/projects`)** | Registered local workspace directories, file trees, and security boundaries. | Duplicated coding task preparation controls that conflicted with the conversational Developer coworker. Repositioned as an administrative repository governance registry while delegating actual development requests to Developer. |
| **Tasks (`/tasks`)** | Cross-domain tasks, priorities, acceptance criteria, and status tracking. | Functional Kanban/list view. Action triggers were nested inside modal sheets. Standardised status pills (`queued`, `working`, `waiting_approval`, `completed`). |
| **Schedule (`/schedule`)** | Chronos strategic schedule, timeline, and calendar commitments. | Clean day-at-a-glance visualization. Ergonomics aligned with global keyboard shortcuts (`Enter` to commit entries). |
| **Devices & Mesh (`/mesh`)** | Multi-device coordination (Windows PC, Android Phone, companion nodes). | Device pairing and mesh heartbeat visualization. Companion status was previously isolated from Coworker chat; unified companion discovery. |
| **Memory / Knowledge (`/memory`)** | Core user profile, semantic memories, facts, and persistent preferences. | Consolidated into a modal accessible globally from the sidebar ("What IRIS remembers") with clear transparency. |
| **Settings (`/settings`)** | System preferences, AI provider keys, TTS/STT options, and notifications. | Separated everyday user preferences from deep diagnostic logs. Power-user options kept accessible without cluttering routine usage. |
| **Desktop (Electron)** | Workstation native shell, hotkeys (`Ctrl+K`), system tray, and auto-reload watcher. | Auto-reload watcher on `frontend/dist` ensures zero restart friction. Desktop path picker integrated into codebase registration. |
| **Android (Capacitor)** | Mobile touch ergonomics, software keyboard avoidance, bottom navigation dock. | Bottom navigation bar optimized for touch targets (min 44px) with `--keyboard-height` CSS variable avoidance. |

---

## 2. Main Usability Problems Discovered

1. **Cognitive Overload in Coworker Interface:**
   - Users opening the Developer coworker were confronted with technical infrastructure decisions: "Should this run on Local PC or Remote Cloud?", "Which engine: `antigravity-cli` or `codex-cli`?", and "What is the companion URL?".
   - *Audit verdict:* IRIS already knows that the cloud companion (`https://irisforgecode.dpdns.org`) is live, free, persistent, and contains `antigravity-cli`. Asking the user to configure this on every conversation violates the minimum-effort principle.
2. **Split-Screen Layout Cramping:**
   - The Coworkers section squeezed a list of coworkers, templates, and an active coding console with diff viewers into a single split view. Reading code diffs and conversational messages side-by-side was cramped and difficult to read on smaller screens or laptops.
3. **Database Column Desynchronisation (`500 ApiError`):**
   - The frontend made calls to `/api/coworkers` and `/workspaces`, but initial PostgreSQL schema did not have `remote_workspace_id` and `workspace_id` columns migrated, resulting in opaque `ApiError: An unexpected internal error occurred.` banners.
4. **Duplicate Task Preparation Workflows:**
   - Preparing a coding task existed both in `ProjectsPage.tsx` (via rigid forms) and in `CoworkersPage.tsx` (via natural dialogue). Users were confused about which entrypoint was canonical.
5. **Lack of Conversational Defaults:**
   - If a new coworker was started, it had no assigned project, requiring the user to find a settings button and select a directory before issuing a prompt.

---

## 3. Simplifications Implemented & Step Reduction Comparisons

### Flow 1: Start a Coding Task with Developer Coworker

* **Before (6 to 7 Steps):**
  1. Click `Coworkers` in sidebar.
  2. Locate Developer in the cramped split list.
  3. Click `Remote Cloud` toggle button.
  4. Open workspace dropdown and select or type URL.
  5. Open engine dropdown and ensure `Antigravity CLI (agy)` is selected.
  6. Click into the message textarea.
  7. Type instruction and press send.
* **After (2 Steps — 66% Effort Reduction):**
  1. Click `Coworkers` -> Click **Developer** card.
  2. Type instruction (e.g. *"Fix navigation bar on mobile"*) and press `Enter`.
  *Developer automatically binds to the active codebase (`IRIS`), connects to `https://irisforgecode.dpdns.org`, clones/checks out the repo, executes with `antigravity-cli`, and presents the diff review card with commit/push approval buttons.*

---

### Flow 2: Switch Active Codebase for Developer

* **Before (4 to 5 Steps):**
  1. Click `Workspace & Engine` drawer button.
  2. Find Local Directory dropdown or Cloud Workspace dropdown.
  3. Select another entry.
  4. Close technical drawer.
* **After (2 Steps — 50% Effort Reduction):**
  1. Click the primary **Codebase Badge** in the chat header (`📁 IRIS (main) ▾`).
  2. Select the destination project from the clean dropdown list.

---

### Flow 3: Inspect & Approve Changed Files (Diff Review)

* **Before (4 Steps):**
  1. Wait for task to finish.
  2. Expand technical logs.
  3. Scroll through raw git diff output in monospace text.
  4. Manually run terminal commands or click separate commit actions.
* **After (1 to 2 Steps — 50% Effort Reduction):**
  1. When execution completes, a dedicated **Diff Review Card** appears immediately showing modified files (`+`, `-`) and statutory metrics.
  2. Click **Approve & Commit** or type follow-up feedback directly in chat.

---

## 4. Components Consolidated or Removed

1. **Removed `showTechnicalToolbar` Drawer:**
   - Deleted the cluttered horizontal drawer that exposed Local PC vs Remote Cloud buttons, engine radio toggles, and companion URL input fields on the chat screen.
2. **Consolidated Coworker Split-Screen into 2 Dedicated Views:**
   - `CoworkersPage.tsx`: Dedicated Level 1 Directory with search, category filtering (Development, Research, Analysis, Writing, Management), template gallery, and pending approval cards.
   - `CoworkerChatPage.tsx` + `CoworkerChatView.tsx`: Dedicated Level 2 Full-Page Chat occupying the complete main canvas, with identical ergonomics to main IRIS conversations.
3. **Replaced Technical Knobs with Advanced Diagnostics Modal:**
   - Infrastructure configurations (switching to local PC worktree, overriding companion URL, pinging wake compute, selecting engine fallback) are encapsulated inside a secondary **Advanced Diagnostics Modal** (`[ ⚙ ]`), completely hidden during normal conversational workflows.
4. **Auto-Binding Default Project & Remote Workspace:**
   - When a user enters Developer chat, if no project was explicitly linked, IRIS automatically assigns the active repository (`IRIS`, `C:\kirtan\IRIS`) and provisions the cloud sandbox on `https://irisforgecode.dpdns.org`.

---

## 5. Coworker-Specific Interface Rules (Developer / Coding Coworker)

The Developer / Coding Coworker operates under strict interaction normalisation rules:

1. **Remote Cloud Execution by Default:**
   - `executionTarget` defaults unconditionally to `"remote"` (`https://irisforgecode.dpdns.org`). The user is never prompted to make this choice.
2. **Hidden Engine Selection:**
   - `antigravity-cli` is the default execution engine. Engine selection is omitted from the conversational surface and resides only in Advanced Diagnostics.
3. **Repository as the Primary Contextual Control:**
   - The header displays a single, prominent, click-to-switch codebase badge: `📁 IRIS (main) ▾`. Switching projects is instantaneous.
4. **Resilient Container Lifecycle:**
   - When a task dispatches, the backend automatically executes a pre-flight probe: if the container was restarted or the sandbox is cold, it auto-provisions and checks out the repository before streaming execution events.
5. **Conversational Interruption & Stop Safeguard:**
   - Saying *"Stop"*, *"Cancel"*, or clicking the **Stop Execution** button immediately issues a safe termination signal to the remote process while preserving uncommitted work on the dedicated branch (`iris/task-...`).

---

## 6. Desktop and Android Improvements

### Desktop (Electron):
- **Live Auto-Reloading:** The desktop shell watches `frontend/dist` and reloads seamlessly without requiring user restart whenever changes are deployed.
- **Native File Dialog:** Added native directory browsing for workspace registration via `window.irisDesktop.selectProjectDirectory()`.
- **Keyboard Shortcuts:** `Enter` sends messages across all chat views; `Shift+Enter` inserts newlines. Global search is mapped to `Ctrl+K`.

### Android (Capacitor):
- **Single-Column Directory:** Responsive grid adapts smoothly from multi-column desktop cards to comfortable, touch-friendly mobile cards.
- **Touch Targets:** All clickable actions and buttons meet the minimum 44px touch target guideline.
- **Fixed Composer Dock:** Bottom composer accounts for the software keyboard via safe area insets and avoids obstructing incoming responses.

---

## 7. Capabilities and Security Safeguards Preserved

Simplification was achieved by automating mechanical steps, **never** by bypassing security controls:

1. **Branch Isolation Preserved:**
   - Tasks execute strictly inside isolated task branches (`iris/task-<uuid>`). Protected branches (`main`, `master`, `production`) can never be modified directly.
2. **Commit & Push Safeguard:**
   - No code is committed to Git without user approval. The user must review the diff and explicitly approve committing and pushing.
3. **Execution Provider Guard:**
   - Backend calls enforce `require_execution("coworker")` and credential redaction (`redact_secrets`) across all log streams.
4. **Zero Compute Cost:**
   - Runs entirely on Google Colab / Free Cloudflare Tunnel ($0) with persistent named routing on `irisforgecode.dpdns.org`.

---

## 8. Test and Build Verification Results

### Backend Automated Test Suite:
```powershell
pytest backend/tests/api/test_coworkers.py backend/tests/api/test_remote_workspace.py
```
- **Results:** `30 passed, 1 warning in 15.67s` (100% pass rate).
- **Covered Scenarios:**
  - Coworker creation, templates, lifecycle, and permissions.
  - Conversational message turns and task event streams.
  - Remote workspace provisioning, execution streams, diff generation, checkpointing, and branch recovery.

### Frontend Production Build:
```powershell
cd frontend && npm run build
```
- **Results:** `built in 10.61s` with `0 errors`.
- **Bundles Produced:** `dist/index.html` (0.88 kB), `CoworkerChatPage` (39.19 kB), `CoworkersPage` (13.50 kB), and core assets.
- **Desktop auto-reload:** Successfully verified in `desktop/iris-desktop.log`.

---

## 9. Remaining UX Issues & Roadmap

1. **Live Terminal WebSocket Streaming in Chat:**
   - Currently, task progress events are displayed via polling / streaming chunks. Adding direct terminal xterm.js streaming inside the Coworker drawer would give real-time command output.
2. **Multi-Coworker Collaboration (Team Chat):**
   - Enabling Developer to invite Researcher or Analyst into a unified shared thread for complex cross-functional briefs.
3. **Automated Conflict Resolution:**
   - When rebasing task branches against `main`, provide an interactive 3-way merge UI directly in the diff viewer.
