# IRIS Milestone D — Desktop & Android Experience

**Status:** Implemented; build-verified; desktop and Android runtime verification unavailable in this environment
**Started:** 2026-11-01
**Scope:** Product experience and cross-platform integration on the existing React/Vite, Electron, Capacitor, FastAPI, and Milestone C UI Orchestrator stack.

## 1. Executive summary

Milestone D's desktop and mobile-first experience is implemented on the existing IRIS stack. Both platforms share the matte design system, navigation model, global status/search/notification surface, persisted theme preference, and shell-owned voice session. Home uses the existing approved widget registry with a fixed, Home-only sphere/composer dock. Frontend production build, Android APK build, desktop asset sync, focused backend tests, lint, and the regression suite were executed. Build checks passed; the regression suite has four verified Windows host/environment failures. Actual desktop UI and Android device runtime checks could not be completed because the available environment has no usable browser/device runner and blocks the configured backend database/network.

## 2. Milestone D objectives and scope

The objective is a cohesive, usable Windows desktop and mobile-first Android experience that reuses IRIS's existing backend, identity, domain services, and Shared UI Orchestrator. Scope includes the design system, application shell, navigation, Home widgets, sphere/composer, destination completeness, synchronization, accessibility, security, performance, and build/runtime verification.

## 3. Initial repository and architecture assessment

- Current branch `main` is at `0709cbd` and matches `origin/main`; the Milestone A/B/C implementation is committed in that tree.
- Frontend: React 18, Vite 6, React Router, TanStack Query, Tailwind CSS v4, Zustand, and Capacitor 8. Existing interface is a near-black, narrow-column shell with a desktop sidebar and mobile bottom navigation.
- Desktop: Electron 33 main/preload process; the app loads the Vite frontend. Existing native project-directory selection and window controls are in the preload bridge.
- Android: Capacitor project plus substantial native voice-assistant, screen-capture, launcher, notification, and widget code. Initial config defaulted to a hosted `server.url`; default APK builds now use bundled frontend assets, with the hosted-WebView behavior available only when explicitly configured.
- Home: Milestone C's `OrchestratedDashboard` renders five approved widgets and has separately versioned platform layouts. The existing `IrisSphere` and voice flow are in Home; the composer and global Ask IRIS surface are currently split across Home and the app shell.
- Existing routes include Home, Today, Tasks, Goals, Schedule, Projects, Coworkers, Diary, Finance, Gym, Focus, Laptop/Phone continuity, Antigravity, Settings, Startup, College, Internship, Insights, and Modules. There is not yet a dedicated Conversations, Devices & Mesh, or Memory destination in the primary navigation; existing implementations are available through chat history, Settings, Mesh, and the Memory modal.
- Milestone C provides `/api/ui-orchestrator/{catalog,state,context,preferences,layouts,proposals,rollback}`, database versioning, locks, approval, rollback, context-led coworker prompts, and bounded opt-in order learning. It has no UI-specific event stream; D uses foreground refetch/focus refresh rather than claiming push-based synchronization.
- Authentication remains the existing single-user identity stub. Domain APIs and backend authorization remain authoritative.

## 4. Milestone C foundation reused

The existing UI Orchestrator, approved widget definitions, platform-specific layout records, version conflicts, lock checks, preference history, proposal review, rollback, temporary widget lifecycle, and context service are retained as the source of truth. Existing situation, habits, tasks, schedule, coworkers, mesh, chat, memory, voice, vision, project registry, and system-health APIs are reused. No replacement orchestration service or widget execution model is planned.

## 5. Desktop application architecture

The existing Electron main/preload architecture and local backend proxy remain intact. `AppShell` hosts the responsive global top bar above a scrolling workspace; its width is no longer clamped for every destination. Desktop navigation exposes Home, Conversations, Coworkers, Projects, Schedule, Tasks, Devices & Mesh, Memory, and Settings. The sidebar retains collapse/expand behavior and legacy destinations are under More. The top bar opens the existing Ask IRIS console from global search, shows attention and pending coworker approvals, and reports actual `/health`, AI status/provider/model, and `/mesh/devices` responses with unavailable states. Electron window and loading backgrounds match the matte light surface. Frontend assets synchronized into the existing desktop distribution successfully; actual desktop interaction was not runtime-verified because the packaged app already had an active single-instance process and available computer-use launch/browser access timed out. An isolated launch attempt produced an untargetable Electron application error, so no pass is claimed.

## 6. Android application architecture

Capacitor continues to select the existing Android dashboard renderer and native bridges. Android bottom navigation gives direct Home, Conversations, Schedule, Coworkers, and More access; More includes Tasks and all remaining primary and legacy routes. Default Capacitor configuration packages the built frontend; an explicit `CAPACITOR_SERVER_URL` remains available. The APK workflow compiles the configured remote API base (default deployment API, overridable with `IRIS_API_URL`). Backend CORS explicitly includes only Capacitor local origins (`https://localhost` and `capacitor://localhost`) needed by bundled assets. Shell safe-area fallback remains and the fixed Home dock accounts for safe bottom and visual viewport keyboard height. `cap:build` and Gradle `assembleDebug` passed; generated debug APK is 12,243,424 bytes. `adb` is absent and no emulator/physical device is attached, so Android runtime, keyboard, permissions, and reconnection are not claimed as verified.

## 7. Shared UI Orchestrator integration

`OrchestratedDashboard` remains the single dashboard renderer. The registry's Priorities, Schedule, Routines, Coworkers, and Progress widgets bind to existing Situation, Habits, and UI Context APIs. Layout versions, platform isolation, locking, proposal previews, approval/rejection, history and rollback remain API-backed. Users can reorder, hide/restore, lock, resize desktop widgets, and propose add/show/hide/resize/reorder operations in natural language; all natural-language changes go through the existing preview/approval mechanism. The preference record now includes a versioned `theme` value (`light`, `dark`, `system`) in its existing JSON field; no new table or migration is needed. State/context queries refetch in the foreground to pick up other-device changes. Error UI asks the user to refresh on version conflicts or failed saves.

## 8. Navigation and information architecture

Added `/conversations`, `/devices`, and `/memory` routes. Conversations reuse existing chat history and route to the Home thread; Devices reuses the existing MeshPage; Memory reuses the searchable, editable memory/pattern modal. `/mesh` remains a compatibility redirect to `/devices`. Existing Projects, Schedule, Tasks, Coworkers, and Settings pages remain mounted rather than replaced. Routes are lazy-loaded except Home and shell.

## 9. Home dashboard implementation

The four primary sections are the registered Priorities, Schedule, Routines, and Coworkers widgets; Progress remains available in the registry. Existing user-defined priorities are displayed without being rewritten by IRIS. Routine rows can check/uncheck through the existing Habits mutation; each widget links to its owning destination. Loading skeletons, empty states, and retry states use live API data. Desktop starts in a two-column grid with supported wide cards; Android uses a single-column renderer. Layout arrangement exposes direct ordering, visibility, lock, and desktop size controls. Suggestions use overdue attention count, schedule presence, and scheduled habits. The backend does not currently supply an active project context to UI Context, so project-aware automatic suggestions are not claimed.

## 10. Sphere and composer implementation

The existing `IrisSphere` canvas is preserved and now remains visibly animated at rest using the same rotating mesh identity with the IRIS accent on light surfaces. Home alone displays it in a fixed bottom-centre dock directly above the existing text/image/screen-capture composer; the workspace reserves dock space. Existing voice states are retained and a real paused state now disables/re-enables the active microphone tracks while keeping the session open. A shell-level VoiceSessionProvider owns the microphone and chat send loop, so route changes no longer unmount the voice hook. On non-Home routes the top bar shows Listening/Paused/Thinking/Speaking state and returns to Home. Composer image upload validation and actual screen-capture path remain. Runtime microphone/OS-permission behavior has not yet been exercised.

## 11. Widget rendering and responsive behaviour

Priorities show overdue/in-progress/due-today task rows; Schedule shows now/next or today's live agenda; Routines bind to active scheduled habits and provide check controls; Coworkers show live active-task count and route to task/approval review; Progress derives completion from Situation and Habits. All remain bounded declarative registry widgets. Empty/loading/error behavior is implemented where data endpoints can fail. Dashboard state refreshes every 20 seconds and context every 30 seconds in foreground; approval notifications refresh every 30 seconds. No UI-specific WebSocket is present.

## 12. Theme and design system

`frontend/src/styles/tokens.css` now defines matte off-white backgrounds, white surfaces, neutral readable text, restrained violet accent, semantic status colors, focus outline, spacing-compatible radii, and reduced-motion behavior. Light is default; dark/system override the same CSS variables. Shared theme is persisted through the existing Orchestrator preferences record, not local-only storage. Electron native background, HTML meta theme, loading screen, primary application cards, and sidebar use the shared palette. The pre-existing sphere animation and reduced-motion behavior remain. Detailed automated contrast ratios are not yet measured.

## 13. Cross-platform state synchronisation

Shared theme, density, learning preference, and week-start remain in the user preference object. Desktop and Android layout records stay separate. Foreground REST refetch (20-second layout, 30-second context/approval) plus focus refetch is the actual cross-device propagation mechanism; the backend has no UI-change event/WebSocket feed, so near-real-time delivery is not claimed. Existing optimistic version checks and lock validation are preserved. On failed fetch the previous layout is kept when available; an error banner and refresh action are shown. Writes are server-confirmed before the UI considers them saved, and failed writes surface instead of being silently discarded.

## 14. Accessibility and interaction design

Search, navigation, notification, health, widget controls, theme, and sphere controls have accessible names/status. Global keyboard search retains Ctrl/Cmd+K. Focus-visible outlines remain shared. Main mobile controls use a 40–44 px minimum target where implemented; safe-area and visual viewport changes adjust the dock. The mobile More panel is scrollable and touch-friendly. Reduced-motion turns off the sphere's rotation and status lamp pulse. Desktop/Android runtime accessibility inspection remains pending.

## 15. Security and permissions

Widget display and visibility do not grant backend access; all data continues through existing API client and service authorization. The only new backend mutation is theme validation in the existing Orchestrator preference endpoint; it is scoped to current user/version. Approval decisions and layout governance still execute server-side. Android CORS adds exact Capacitor local origins for bundled-app API calls; it does not add wildcard origins. Microphone, screen capture, camera and notification native permissions are not broadened. The existing single-user identity stub remains an architectural limitation from Milestone C.

## 16. Files and database changes

Files changed: `frontend/src/styles/tokens.css`, `frontend/src/modules/registry.ts`, `frontend/src/components/layout/{AppShell,GlobalTopBar,TopStrip}.tsx`, `frontend/src/app/App.tsx`, `frontend/src/features/chat/ConversationsPage.tsx`, `frontend/src/api/client.ts`, `frontend/src/features/agy/AgyDrawer.tsx`, and `frontend/src/features/ai/AskIrisConsole.tsx`, `frontend/src/features/home/{HomePage,IrisSphere,MemoryPage,OrchestratedDashboard,uiOrchestratorApi,useUIOrchestrator,VoiceSession,voice}.ts(x)`, `frontend/src/features/mesh/MeshPage.tsx`, `frontend/src/features/settings/SettingsPage.tsx`, `frontend/index.html`, `frontend/capacitor.config.ts`, `.github/workflows/build-apk.yml`, `backend/app/api/routes/ui_orchestrator.py`, `backend/app/main.py`, `backend/tests/api/test_ui_orchestrator.py`, `desktop/main.cjs`, and `desktop/loading.html`. No package dependency was added, and no database migration was created.

## 17. API and frontend changes

Frontend routes are lazy loaded to split destination bundles; the Ask IRIS console loads only when opened. Home capture and voice capture use the existing lazy screen-capture module. Orchestrator state/context foreground refetch intervals were tightened for connected-device consistency. Backend `/ui-orchestrator/preferences` now validates `theme` without adding a schema/table. Capacitor build config now defaults to bundled assets; the APK workflow accepts an explicit hosted WebView URL and independently sets `VITE_API_URL` (default production API or `IRIS_API_URL`).

## 18. Testing strategy and exact results

Commands and exact results:

- `npm.cmd run cap:build` from `frontend` — passed TypeScript, Vite production build, and Capacitor sync. Final main JS: 430.70 kB minified / 134.85 kB gzip; largest lazy route chunk (Insights): 398.78 kB / 109.65 kB gzip. No Vite warnings.
- `npm.cmd run sync-desktop` from the repository root — passed; synchronized generated frontend assets to the existing desktop distribution.
- `.\\gradlew.bat assembleDebug` from `frontend/android` — passed; debug APK at `frontend/android/app/build/outputs/apk/debug/app-debug.apk` (12,243,424 bytes). Gradle emitted its existing `flatDir` and deprecation warnings.
- `.\\.venv\\Scripts\\python.exe -m pytest tests/api/test_ui_orchestrator.py -q --basetemp=.pytest-milestone-d-focused-final -p no:cacheprovider` from `backend` — **7 passed**.
- `.\\.venv\\Scripts\\python.exe -m ruff check app/api/routes/ui_orchestrator.py app/main.py tests/api/test_ui_orchestrator.py` from `backend` — passed: “All checks passed!”.
- `.\\.venv\\Scripts\\python.exe -m pytest -q --tb=short --basetemp=.pytest-milestone-d-final -p no:cacheprovider` from `backend` — **528 passed, 4 failed, 4 warnings** in 162.61 seconds. The failures are `test_supervisor_fast_path_open_vscode_repo` (VS Code is not installed), `test_c_browser_fallback` (Windows access denied launching Brave), `test_launch_windows_app_antigravity_cli_vs_ide` and `test_launch_windows_app_terminal_home_vs_target` (Windows access denied to `wt.exe`). These are host executable/permission failures, consistent with Milestone C environment-dependent failures; no product assertion failure was reported. Warnings are existing Starlette HTTP_422 and `datetime.utcnow` deprecations.
- Backend runtime startup was attempted but the configured Supabase database connection was denied and binding the local server failed with `WinError 10013`; API runtime smoke checks could not be performed.
- Android runtime was not tested: `adb` is unavailable and no emulator or device is attached.
- Desktop UI runtime was not verified. The packaged app already had a single-instance process; computer-use launch/browser access timed out, and an isolated Electron launch produced an untargetable application error. Only builds and asset synchronization are reported as passed.

## 19. Performance and responsiveness observations

Lazy route splitting and dynamic capture imports removed both prior Vite warnings. Main entry chunk is 430.70 kB minified / 134.85 kB gzip; routes load on demand. Largest lazy chunk is Insights at 398.78 kB / 109.65 kB gzip. No package dependency was added. Runtime CPU/memory and interactive narrow-window measurements remain unavailable.

## 20. Known limitations and unresolved issues

UI-specific backend push events are absent, so synchronization uses periodic foreground refetch/focus events (20-second layout, 30-second context/approval). Android device and microphone permission behavior could not be checked. Desktop UI interaction was not verified. Backend runtime smoke testing was blocked by denied database/network access. The single-user identity stub remains. Android background listening is not claimed. There is no offline mutation queue; failed saves remain visible and are not marked saved.

## 21. Verification evidence

Build and test evidence is listed in §18. Capacitor production build, Android debug APK build, and desktop asset synchronization passed. Focused backend tests and lint passed. The full backend suite produced 528 passes and four verified environment-dependent desktop executable failures. No application runtime check is claimed from build evidence. No adb/device was present, computer-use browser access was unavailable, and the backend could not connect to its configured database in this environment.

## 22. Final acceptance checklist

- [x] Desktop shell, navigation, and destination implementations are present; [ ] desktop UI runtime behavior is verified.
- [x] Dedicated mobile-first shell and navigation are implemented; [ ] Android UI runtime behavior is verified on an emulator/device.
- [x] Home uses the existing Shared UI Orchestrator and all five approved widgets have live data/error/loading states in code.
- [x] Shared preferences and distinct platform layouts use the existing API and persistence.
- [x] Proposal/approval/lock/rollback paths remain routed through existing backend governance.
- [x] Sphere and composer use the existing voice, image, and screen-capture paths; [ ] OS permission/runtime behavior is verified.
- [x] Navigation, health, notifications, coworker activity, devices/mesh, and memory surfaces are implemented against existing routes/services; [ ] desktop runtime interaction is verified.
- [x] Accessibility, responsiveness, offline errors, and security constraints are documented; runtime visual/accessibility inspection remains unavailable.
- [x] Frontend, Capacitor sync, Android APK, desktop asset sync, focused API tests, and lint passed. [ ] Full backend suite is entirely green (four host-dependent failures remain).
- [x] All Milestone D documentation is contained in this file.

## 23. Milestone E readiness

The implementation and available builds are ready for a Milestone E review. Milestone E should begin after desktop and Android runtime smoke tests are run on a machine with the desktop app available, an Android emulator/device, and database/network access; the four host-dependent Windows regression failures should also be independently handled or explicitly accepted. Accordingly, the code and build work is complete, but not every runtime-oriented Definition of Done item could be verified in this environment.