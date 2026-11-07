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
| **Projects (`/projects`)** | Registered local workspace directories, file trees, and security boundaries. | Duplicated coding task preparation forms with engine selectors that conflicted with the conversational Developer coworker. Modernised into a clean codebase governance registry with instantaneous "Develop with Coworker" bridges. |
| **Tasks (`/tasks`)** | Cross-domain tasks, priorities, acceptance criteria, and status tracking. | Functional Kanban/list view. Action triggers were nested inside modal sheets. Standardised status pills (`queued`, `working`, `waiting_approval`, `completed`) and added direct 1-click task creation from coworker conversation deliverables. |
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
6. **Dead Legacy Code:**
   - `CodingCoworkerWorkspace.tsx` was a legacy 510-line monolithic prototype left behind during refactoring, causing bundle bloat.

---

## 3. Interaction-Efficiency Audit: Step Reduction Metrics

| Workflow | Current Steps | Proposed / Implemented Steps | Improvement | Explanation |
| :--- | :---: | :---: | :---: | :--- |
| **Open a Coworker** | 3 | 1 | **67% reduction** | Click coworker card in directory; opens full-page conversation with assigned context immediately. |
| **Start Coding Task** | 7 | 2 | **71% reduction** | Click Developer -> type prompt -> Enter. IRIS auto-binds active codebase, connects to remote cloud companion, executes via `antigravity-cli`, and generates diff card. |
| **Switch Active Codebase** | 5 | 2 | **60% reduction** | Click primary codebase badge (`📁 IRIS (main) ▾`) in header -> select target project from dropdown. |
| **Create a Task from Coworker** | 6 | 1 | **83% reduction** | Click "+ Save as Task" directly beneath any coworker response; automatically creates task in Tasks & Priorities. |
| **Inspect & Commit Diff** | 5 | 2 | **60% reduction** | Expand dedicated diff card -> click "Commit to Task Branch". |
| **Search Past Knowledge** | 4 | 2 | **50% reduction** | Click "What IRIS remembers" in global sidebar footer -> search semantic facts modal. |
| **Pair Mobile Device to Laptop** | 5 | 2 | **60% reduction** | Enter 6-digit PIN shown on phone into Settings -> Mesh. Permanent pairing token exchanged instantly. |

---

## 4. Components Consolidated or Removed

1. **Deleted Legacy Monolith `CodingCoworkerWorkspace.tsx`:**
   - Completely deleted the unused 510-line legacy split-screen prototype, reducing bundle size and eliminating architectural confusion.
2. **Removed `showTechnicalToolbar` Drawer from Conversation View:**
   - Deleted the horizontal drawer that exposed Local PC vs Remote Cloud buttons, engine radio toggles, and companion URL input fields on the chat screen.
3. **Consolidated Coworker Split-Screen into 2 Dedicated Views:**
   - `CoworkersPage.tsx`: Dedicated Level 1 Directory with search, category filtering (Development, Research, Analysis, Writing, Management), template gallery, and pending approval cards.
   - `CoworkerChatPage.tsx` + `CoworkerChatView.tsx`: Dedicated Level 2 Full-Page Chat occupying the complete main canvas, with identical ergonomics to main IRIS conversations.
4. **Replaced Technical Knobs with Advanced Diagnostics Modal:**
   - Infrastructure configurations (switching to local PC worktree, overriding companion URL, pinging wake compute, selecting engine fallback) are encapsulated inside a secondary **Advanced Diagnostics Modal** (`[ ⚙ ]`), completely hidden during normal conversational workflows.
5. **Modernised `ProjectsPage.tsx` Codebase Registry:**
   - Converted `ProjectsPage` from an awkward task formulation form into an administrative codebase governance registry with direct `Develop with Coworker →` bridges and one-click security permission toggles.

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
6. **Cross-Coworker Roles Tailored:**
   - Researcher, Analyst, Writer, and Project Manager coworkers expose clean prompts suited to their domains without showing code repository badges or git diff actions.

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
- **Results:** `30 passed, 1 warning in 20.60s` (100% pass rate).
- **Covered Scenarios:**
  - Coworker creation, templates, lifecycle, and permissions.
  - Conversational message turns and task event streams.
  - Remote workspace provisioning, execution streams, diff generation, checkpointing, and branch recovery.

### Frontend Production Build:
```powershell
cd frontend && npm run build
```
- **Results:** `built in 28.41s` with `0 errors`.
- **Bundles Produced:** `dist/index.html` (0.88 kB), `CoworkerChatPage` (39.15 kB), `CoworkersPage` (13.53 kB), `ProjectsPage` (13.28 kB), and core assets.
- **Desktop auto-reload:** Successfully verified in `desktop/iris-desktop.log`.

---

## 9. Major Improvement Classifications

| Improvement | Classification | Verification Detail |
| :--- | :--- | :--- |
| **Developer Remote Cloud by Default** | **Implemented & Verified** | Verified live via Cloudflare Tunnel at `https://irisforgecode.dpdns.org`; auto-provisions repository and connects without prompting user. |
| **Coworker Directory & Dedicated Chat** | **Implemented & Verified** | Replaced split-screen layout with Level 1 Directory (`/coworkers`) and Level 2 Dedicated Full-Page Chat (`/coworkers/:id/chat`). |
| **Primary Codebase Switcher in Header** | **Implemented & Verified** | Header exposes clean dropdown badge (`📁 IRIS (main) ▾`); switches active repo in 1 click. |
| **Advanced Diagnostics Modal** | **Implemented & Verified** | Tucked engine selector, companion URL, and local PC fallback inside gear modal (`[ ⚙ ]`). |
| **1-Click Coworker Deliverable to Task** | **Implemented & Verified** | Added "+ Save as Task" button to coworker responses; pushes deliverable straight to IRIS Priorities. |
| **Projects Page Streamlining** | **Implemented & Verified** | Modernised repository registry with direct "Develop with Coworker" bridges and one-click permission toggles. |
| **Monolith Cleanup (`CodingCoworkerWorkspace.tsx`)** | **Implemented & Verified** | Removed 510 lines of dead code; `npm run build` succeeds cleanly. |
| **Live Terminal WebSocket Streaming** | **Partially Implemented** | Polling and streaming chunks active; full xterm.js embedded terminal deferred to next release. |
| **Multi-Coworker Shared Group Chat** | **Deferred (Roadmap)** | Multi-agent coordination currently operates hierarchically via Supervisor; group chat thread planned. |

---

## 10. Remaining UX Issues & Roadmap

1. **Live Terminal WebSocket Streaming in Chat:**
   - Currently, task progress events are displayed via polling / streaming chunks. Adding direct terminal xterm.js streaming inside the Coworker drawer will provide character-by-character live terminal visualization.
2. **Multi-Coworker Collaboration (Team Chat):**
   - Enabling Developer to invite Researcher or Analyst into a unified shared thread for complex cross-functional briefs.
3. **Automated Conflict Resolution:**
   - When rebasing task branches against `main`, provide an interactive 3-way merge UI directly in the diff viewer.
