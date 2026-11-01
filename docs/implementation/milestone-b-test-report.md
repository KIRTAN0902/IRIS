# Milestone B Verification Report

**Run date:** 2026-11-01  
**Environment:** Windows host, Python 3.13, backend virtual environment, Node/Vite frontend

## Backend

- `backend/.venv/Scripts/python.exe -m pytest tests/api/test_coworkers.py -q --basetemp=.pytest-milestone-b-final-focus2 -p no:cacheprovider` — **16 passed**. Covers coworker creation/templates, lifecycle rules, task persistence/assignment, narrow approval, denied host capability, restart recovery, developer handoff, deliverable review, Supervisor recommendation, dependency failure, archive retention and explicit CUA mock evidence.
- `backend/.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.pytest-milestone-b-complete -p no:cacheprovider` — **521 passed, 4 failed, 4 warnings**. The four failures are environment-bound existing desktop tests, not coworker failures:
  - `tests/agent/test_desktop_tools.py::test_supervisor_fast_path_open_vscode_repo`: VS Code is not installed on this Windows host.
  - `tests/devices/test_device_acceptance.py::test_c_browser_fallback`: Brave executable exists in discovery metadata but Windows denies access to its path.
  - `tests/services/test_mesh_service.py::test_launch_windows_app_antigravity_cli_vs_ide` and `::test_launch_windows_app_terminal_home_vs_target`: access to the Windows Terminal `WindowsApps\wt.exe` alias is denied.
- The first full-suite attempt used pytest's default temp root and produced 20 setup errors because `C:\Users\shahk\AppData\Local\Temp\pytest-of-shahk` was inaccessible. Rerunning with the workspace-local `--basetemp` removed those fixture errors.
- The finance regression test initially used hard-coded October 2026 dates and failed after the system date moved to November. Its fixture now creates entries within the current month; the focused test passes. Product finance behavior was not changed.
- `python -m compileall -q app` — passed.
- `python -m alembic upgrade head` against configured PostgreSQL — applied `h1a2b3c4d5e6 -> i2a3b4c5d6e7` successfully.
- `python -m alembic current` — `i2a3b4c5d6e7 (head)`.
- `python -m alembic upgrade head` against an isolated SQLite validation database — full migration chain completed through `i2a3b4c5d6e7`.

## Frontend and Android shell

- `frontend/npm run build` — passed TypeScript and Vite production builds.
- `frontend/npm run cap:build` — passed TypeScript/Vite build and `cap sync android`; Capacitor copied web assets and updated Android plugins/config.
- Existing Vite warnings remain: `screenCapture.ts` is both dynamically and statically imported, and the main bundle exceeds 500 kB. These were not introduced as runtime failures by the Coworkers page.
- No browser-driven UI test framework is configured in the repository. API behavior, TypeScript compilation and Capacitor asset sync were verified; individual visual interactions were not automated.

## CUA prototype

- `backend/tests/api/test_coworkers.py::test_computer_use_demo_endpoint_labels_simulation` and `test_mock_computer_use_demo_is_explicitly_simulated` — passed as part of the 16-test focused run.
- These tests validate only the safe mock contract. No real CUA driver, VM, browser or desktop control was run; see `cua-evaluation.md`.

## Warnings and remaining limits

- Four non-blocking existing warnings include a Starlette HTTP status deprecation and `datetime.utcnow()` deprecations in existing tests.
- The four Windows desktop failures require host apps/permissions unavailable in the test environment. They were not skipped or weakened.
- Active generic model calls cannot be provider-paused or forcibly cancelled. They are persisted and marked interrupted after restart; retry is explicit.
- A `completed` task with no unresolved actions or criteria evidences a non-empty persisted deliverable only. Tasks with unchecked criteria require explicit user review; that review is recorded as a user attestation and does not claim independent verification.
- No CUA package or additional runtime dependency was installed.
