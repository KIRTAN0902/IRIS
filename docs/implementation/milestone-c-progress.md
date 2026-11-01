# IRIS Milestone C — Shared UI Orchestrator

**Status:** Implemented and integrated; verification complete  
**Date:** 2026-11-01  
**Architecture basis:** Part VIII, section 22 and Phase 5 of `Reimagining_IRIS.md`

## Delivered

### Shared contract and approved component registry

- Added a backend UI Orchestrator API with a versioned widget catalog, a small Home context snapshot assembled from the existing Situation service and coworker task records, and user-scoped preferences/layout state.
- The only renderable widgets are `priorities`, `schedule`, `routines`, `coworkers`, and `progress`. Their supported sizes, required IRIS data, and desktop/Android compatibility are described by the registry.
- Widget definitions contain IDs and bounded declarative configuration. The API rejects unknown widgets, duplicate entries, unsupported sizes, oversized configuration, and malformed platform names. It does not accept executable component code.
- Added a separately versioned desktop and Android layout. The frontend selects an Android renderer in Capacitor or Android browser contexts and a desktop renderer elsewhere. Both use the shared component definitions, data services, preferences, layout controls, and approval model.

### Preferences, user control, and recovery

- Layouts and UI preferences persist by IRIS user in SQLAlchemy tables. Preferences include density, week start, and an opt-in interaction-learning setting. When enabled, user-selected widget ordering is stored as bounded observations and informs future proposal ordering; it never applies a layout by itself. Layout writes use optimistic version checks to prevent silent cross-device overwrites.
- Home supports arranging widgets, reordering, hiding/restoring, and locking individual widgets. Locked widget properties and positions are enforced by the API, including for approved proposals.
- IRIS can propose a change from the supported component vocabulary. The Home UI shows before/after layouts, reason, and explicit approve/reject controls. A proposal does not alter the active layout until approved.
- Every accepted layout/preference change records a bounded snapshot history. The user can restore the prior configuration; rollback itself is versioned.
- A context-led coworker activity prompt offers a proposal when activity exists but its widget is hidden. The prompt is dismissible and does not change the user's layout on its own.
- Widgets support persistent and temporary lifecycles. Temporary widgets carry a timezone-aware expiry, disappear from rendering after expiry, and are validated as future-dated by the API; natural-language requests can ask for a temporary widget.

### Integration and persistence

- Replaced the Home page's monolithic dashboard entry with the shared widget orchestrator. Existing Situation, Habits, and Coworker data services remain the sources of truth.
- Added migration `j3b4c5d6e7f8_shared_ui_orchestrator.py`, following the current Milestone B migration head `i2a3b4c5d6e7`.
- Added API tests for registry/context, state persistence, invalid definitions, version conflicts, lock behavior, proposal approval/rejection, preference versioning, and rollback.

## Verification evidence

- `backend/.venv/Scripts/python.exe -m pytest tests/api/test_ui_orchestrator.py -q --basetemp=.pytest-milestone-c-postformat -p no:cacheprovider` — **5 passed** after final formatting and implementation changes.
- Full backend regression, `python -m pytest -q --tb=short --basetemp=.pytest-milestone-c-full -p no:cacheprovider` — **526 passed, 4 failed**. All four failures are existing host/environment-bound Windows desktop checks: VS Code is unavailable, Brave path access is denied, and Windows Terminal alias access is denied. The focused Orchestrator suite was rerun after the final opt-in learning change and passed **5/5**.
- `backend/.venv/Scripts/python.exe -m compileall -q app` — passed.
- Ruff check on the new backend route, model, and API tests — passed.
- `MIGRATION_DATABASE_URL=sqlite:///:memory: python -m alembic upgrade head` — the full migration chain upgraded through `j3b4c5d6e7f8` on isolated SQLite.
- `frontend/npm.cmd run cap:build` — TypeScript check and Vite production build passed; Capacitor synced the new web assets and Android plugins successfully.
- `frontend/android/gradlew.bat assembleDebug` — native Android debug APK build passed (Gradle 8.14.3).
- `git diff --check` — passed.

## Known boundaries

- The current identity model is IRIS's existing single-user identity stub. The new records are scoped to the resolved user and are ready to follow the authentication model when that changes.
- Natural-language widget requests resolve against the approved registry vocabulary and create a reviewable proposal. They do not generate new executable widgets or arbitrary code.
- Interaction learning is opt-in and bounded to widget order observations. Layout history is maintained separately for rollback. All learned-order suggestions remain proposals that require user approval; automatic layout mutation is not enabled.
- Existing Vite warnings remain for the shared screen-capture module being statically and dynamically imported and for the large main bundle; the production build succeeds.
