# Dependency and license audit (Phase 0)

Scope: checked-in root, backend, frontend and desktop manifests. This is a manifest-level inventory, not a complete SBOM. Version ranges and lockfiles may contain transitive packages; exact installed transitive licenses were not verified. No dependencies were added or replaced.

## Direct dependency groups

| Area | Direct dependencies observed | License evidence / concern |
|---|---|---|
| Backend runtime | FastAPI, Uvicorn, Pydantic, pydantic-settings, SQLAlchemy, Alembic, email-validator, google-genai, python-dotenv, httpx, tzdata, psycopg[binary], segno, Pillow, pywinpty (Windows) | These projects are generally published under permissive open-source licenses (MIT/BSD/Apache); package versions are ranges. Verify exact pinned package metadata and transitive licenses when producing a lock/SBOM. |
| Backend coding agent | `google-antigravity>=0.1.21` was present in `backend/requirements.txt`; removed during Milestone A because the SDK path is deprecated and Antigravity CLI is invoked as an optional installed executable. | No new Python SDK dependency is required for the CLI adapter. Antigravity itself remains an external Google service with its own terms; see below. |
| Backend development | pytest, pytest-cov, ruff, black, pytest-asyncio | Commonly permissive licenses; exact resolved versions and transitive license inventory not recorded. |
| Frontend runtime | React, React DOM, Vite, Capacitor Android/CLI/core, Radix UI, TanStack Query, fonts, class-variance-authority, clsx, date-fns, html2canvas, lucide-react, React Router, Recharts, tailwind-merge, Zustand | Dependencies are open-source ecosystem packages; verify exact lockfile package licenses in a generated inventory before release. Fonts have individual license files/terms to retain. |
| Frontend development | Tailwind Vite plugin, React types, Vite React plugin, puppeteer-core, Tailwind, TypeScript, Vite | License files should be checked from resolved package metadata; no proprietary hosted service is evident in manifests. |
| Desktop | Electron | MIT-licensed upstream project; packaged runtime also contains Chromium/Node components with their own notices. Preserve Electron distribution notices. |

## Repository observations

- `backend/requirements.txt` and root `requirements.txt` differ: root manifest includes `segno`, Pillow and conditional `pywinpty`; backend manifest lacks those entries.
- Python dependencies are unpinned lower bounds, so reproducible license review is not possible from requirements files alone.
- npm lockfiles exist for frontend and desktop, but no generated license report was found during repository listing.
- Existing model-provider settings include hosted provider endpoints, but these are optional configurations, not dependencies mandated by package manifests. Their usage can incur provider charges and is not an OSS licensing issue by itself.

## Recommended follow-up

Before release, verify the exact Antigravity CLI distribution license and service terms against the accepted product policy. Generate a license inventory from the exact resolved lockfiles and retain upstream notices. No package replacement was introduced.

## Antigravity CLI validation (2026-10-31)

The installed executable is `C:\Users\shahk\AppData\Local\agy\bin\agy.exe`, version `1.4.12`; local `agy --help` confirms interactive mode, `--prompt-interactive`, print/headless `--print`, stream-json output, `--continue`, `--conversation`, `--sandbox`, and a dangerous permission bypass flag. The adapter must never set the bypass flag. Official CLI reference documents the flags, request-review default, and sandbox behavior; it also warns sandbox has no effect if unavailable. The installed help does not prove sandbox is enabled or OS enforcement is effective, so runtime verification is still needed. Official conversation docs describe `--continue` workspace scoping and `/resume`.

Official repository README states use entails Google collection/use of interaction data under Google's Terms and Privacy Policy (opt-out is noted there). Therefore Antigravity is not a self-hosted/open-source service. Its current distribution and service terms do not establish compliance with IRIS's no mandatory proprietary service rule. Keep it an optional user-selected adapter and disclose this dependency; do not make it a mandatory core dependency. Repository provenance/license and software license were not verifiably established from its GitHub landing page; package `google-antigravity` needs separate exact metadata review.
