# CUA Evaluation

**Snapshot date:** 2026-11-01  
**Decision:** Reject real CUA integration for this Milestone B host; keep a provider-neutral interface and explicit mock demonstration.

## Components considered

The `trycua/cua` repository is a monorepo, not a single uniform product. The reviewed upstream `main` materials list the Python `cua-sandbox` package at **0.9.1** with optional `cua-driver==0.37.0`; its direct dependency ranges include `cua>=0.2.0`, `cua-core>=0.1.18,<0.4.0`, HTTPX, ORAS, vncdotool, Paramiko, grpcio, protobuf, and pycdlib. These are upstream versions/specifications, not installed IRIS dependencies.

| Component | Observed version/licence boundary | Relevance and assessment |
| --- | --- | --- |
| CUA SDK / `cua` CLI / local runtimes | Repo licensing section identifies these as MIT except directories with their own licence; `cua-sandbox` metadata is MIT, version 0.9.1. | Promising provider-neutral sandbox API. Local sandbox runtime uses local container/VM mechanisms; quickstart demonstrates `cua sb create` and local Python sandbox. Exact resolved transitive dependency versions were not locked or added to IRIS. |
| Cua Driver | Upstream README calls the base Driver MIT; current Python extra pins `cua-driver==0.37.0`. | Supports Windows GUI automation but requires an interactive logged-in console/RDP session for its Windows GUI tests. It drives the current host desktop, not an isolated desktop by itself. That is too much host authority for a coworker prototype. |
| Cua Spaces and `cua-spacesd` | **FSL-1.1-MIT**, source-available. FSL is not an OSI-approved open-source licence; each release converts to MIT after two years. | Excluded under IRIS policy. Cua Spaces also offers paid plans and supports self-hosted cloud arrangements. No mandatory hosted service is acceptable. |
| Cua Driver Bench | Current repo licensing marks it FSL-1.1-MIT; versions published before 2026-10-11 were MIT. | Not used by IRIS. Benchmark content is not needed for the runtime. |
| Optional `cua-perception` | Not MIT; includes an AGPL-3.0-only OmniParser model artifact, Apache-2.0 OCR artifacts and separately packaged ONNX Runtime. | Excluded. Requires separate artifact and dependency review before redistribution/hosting. |
| Deprecated `cuabot`, `cua-computer`, `cua-computer-server`, `cua-agent`, `cua-som` | Upstream marks packages deprecated; `cua-som` is separately AGPL-3.0-or-later. | Excluded, especially because upstream warns `cuabot` has known security issues. |
| CUA-S1 | Source MIT, weights/datasets live separately and have artifact-specific terms. | Not a runtime requirement; no weights were downloaded. |
| Cua Bench | Repository currently lists FSL-1.1-MIT for Cua Driver Bench. | Not adopted as a dependency or evaluation runtime. |

The MIT `cua-sandbox` manifest names direct packages and version ranges, but did not resolve an exact lockfile for this host. Therefore IRIS does not import or bundle those dependencies. Before any adoption, pin the full lock graph and audit each resolved license and artifact. No CUA package was added to `backend/requirements.txt` or the frontend.

## Windows and runtime verification

The IRIS host is Windows. Local command detection on 2026-11-01 found `cua`, `docker`, and `cargo` unavailable; `wsl.exe` exists. The official repo provides a Windows PowerShell installer for the SDK/CLI and documents Windows support for Cua Driver, but that does not establish that the local host has a usable isolated runtime. The CUA SDK/CLI was not installed, so no real CUA sandbox, daemon, driver, desktop permission, or browser/GUI interaction was run.

The Driver has a different security boundary than the sandbox SDK: its Windows native automation runs in the interactive host session. A proper IRIS integration would need a supported isolated guest/runtime plus an audited provider bridge, not direct control of the user's host desktop. CUA Spaces could provide full desktop VMs, but the app/server portions are FSL-1.1-MIT and are excluded.

## Security and integration decision

The IRIS architecture defines a `ComputerUseProvider` interface with detect, create, inspect, act, capture-evidence, stop and release operations. It is independent of Supervisor, coworker scheduling and coding execution. A safe local mock provider is exposed in the Coworkers experience and verifies the lifecycle, but **is explicitly simulated and does not control any desktop**.

No CUA adapter is wired into production task execution. The real prototype acceptance criteria (isolated environment, GUI event execution and screenshot evidence) were not demonstrated. This is recorded as an environment and platform limitation, not as successful real computer use. The mock test verifies only the provider-neutral contract and safe denial boundary.

## Sources

- [CUA repository README and component/licence matrix](https://github.com/trycua/cua/blob/main/README.md)
- [Cua Sandbox manifest, version, declared licence and dependencies](https://github.com/trycua/cua/blob/main/libs/python/cua-sandbox/pyproject.toml)
- [Cua Driver platform and GUI test requirements](https://github.com/trycua/cua/blob/main/libs/cua-driver/README.md)
- [Cua Spaces daemon licence and security/runtime details](https://github.com/trycua/cua/blob/main/libs/cua-spacesd/README.md)
