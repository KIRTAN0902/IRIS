# IRIS — Complete System Architecture & Knowledge Transfer Specification

> **System Designation**: IRIS (*Intelligent Responsive Information System*)  
> **Repository**: `C:\kirtan\IRIS`  
> **Version**: 6.0 (P4 JARVIS-Style Ambient Activation & Always-Available Operating System: Realme GT 7T Native Voice Interaction Service & Translucent Overlay, Glowing Dynamic Edge-to-Edge Visual Border, Real-Time Audio-Amplitude Pulsing State Machine, On-Demand 24kHz Bi-directional Audio Streaming via /api/voice/live, Zero-Surveillance Background Policy, 1x1 Glowing Home Widget & Quick Tile, Zero Regressions across 487 Test Cases)  
> **Target Audience**: Core Engineers, Systems Architects, and Technical Maintainers  

---

## Table of Contents
1. [Executive Summary & What IRIS Is](#1-executive-summary--what-iris-is)
2. [Core Principles & Design Philosophy](#2-core-principles--design-philosophy)
3. [End-to-End System Architecture](#3-end-to-end-system-architecture)
4. [The Multi-Agent Swarm & Supervisor](#4-the-multi-agent-swarm--supervisor)
5. [Universal Device Intelligence & Capability-Driven Execution (P2)](#5-universal-device-intelligence--capability-driven-execution-p2)
6. [Ephemeral Multimodal Vision Pipeline](#6-ephemeral-multimodal-vision-pipeline)
7. [Voice Engine & Situational Awareness](#7-voice-engine--situational-awareness)
8. [Sovereign Mesh Network & Remote Desktop Mirroring](#8-sovereign-mesh-network--remote-desktop-mirroring)
9. [JARVIS-Style Ambient Activation & Always-Available Operating System (P4)](#9-jarvis-style-ambient-activation--always-available-operating-system-p4)
10. [Comprehensive Tech Stack Breakdown](#10-comprehensive-tech-stack-breakdown)
11. [Hosting, Environments & Deployment Topologies](#11-hosting-environments--deployment-topologies)
12. [Codebase Anatomy & Directory Tree](#12-codebase-anatomy--directory-tree)
13. [Operational Runbook & Developer Cheatsheet](#13-operational-runbook--developer-cheatsheet)

---

## 1. Executive Summary & What IRIS Is

### What is IRIS?
**IRIS** is not a generic to-do list, and it is not a simplistic chatbot wrapper. It is a **Sovereign Personal Operating System (Personal OS) and Executive Command Center** engineered for a single high-output operator managing four concurrent life pillars:
- 🎓 **COLLEGE**: Academic deadlines, course assignments, lab deliverables, exam prep.
- 💼 **INTERNSHIP**: Paid software engineering deliverables, code reviews, standups.
- 🚀 **STARTUP (Strategic Priority)**: Customer prospecting, outreach pipeline, investor/customer demos, product shipping.
- 🧘 **PERSONAL**: Health, weightlifting routines, daily all-week yoga asanas, habit streaks, personal finance & cash flow.

In standard workflows, productivity is fragmented: tasks in Todoist, calendar in Google Calendar, workouts in fitness apps, finance in Notion/Splitwise, code in IDEs, and notes in Obsidian. 

**IRIS unifies all four life domains** into a single, cohesive, self-hosted intelligence fabric answering four existential operational questions in real time:
1. **What matters today?** (High-leverage focus vs trivial busyness)
2. **What should I do right now?** (Deterministic constraint-aware recommendation)
3. **Is anything urgent or falling behind?** (Deadlines, pipeline follow-ups, habit consistency)
4. **Am I making meaningful progress?** (Real outcomes: customers, replies, code shipped, workouts finished — *Progress > Activity*)

```mermaid
flowchart TD
    subgraph LifeAreas ["Four Life Pillars"]
        A["🎓 College"]
        B["💼 Internship"]
        C["🚀 Startup (Strategic Priority)"]
        D["🧘 Personal (Health, Yoga, Finance)"]
    end

    subgraph IRISCore ["IRIS Intelligence Engine"]
        FastPath["Deterministic Fast-Path Engine<br/>(0ms Latency, 0 API Cost, Spoken Prefix Normalizer)"]
        Supervisor["IrisSupervisor Orchestrator & Dynamic Peer Dispatcher"]
        LLM["Google Gemini 3.1 Flash-Lite Engine<br/>(Multi-Tier Fallback: Groq / Gemma 4 / NVIDIA)"]
        Vision["Ephemeral Multimodal Vision<br/>(Batch & Resilient Serial Fallback)"]
        LiveVoice["Gemini Live Sovereign Voice<br/>(gemini-3.8-live + Registered Native Tools)"]
    end

    subgraph Surfaces ["Unified Client Surfaces"]
        Desktop["🖥️ Native Windows Desktop (Electron + Single-Instance)"]
        Mobile["📱 Mobile Companion App (Capacitor Android Launcher)"]
        Mesh["🌐 Sovereign Mesh & WebRTC Screen Mirror"]
        Voice["🎙️ Bidirectional Audio & Live Tool Calling"]
    end

    LifeAreas --> IRISCore
    IRISCore --> Surfaces
```

---

## 2. Core Principles & Design Philosophy

1. **Progress > Activity**:
   Success is measured by concrete results (prospects contacted, replies, meetings booked, code merged, workouts completed), not hours seated at a desk.
2. **Deterministic Truth, AI Reasoning**:
   Deterministic engines handle truth (time constraints, availability, hard deadlines, status queries, completions). Machine learning provides reasoning, synthesis, and creative assistance. IRIS never hallucinates facts when deterministic truth is available.
3. **Zero-Latency Fast-Paths (Jev Principle)**:
   Any request with a known deterministic answer (e.g. *"what should I do now?"*, *"gym done"*, *"lock workstation"*, *"open terminal"*, *"open whatsapp"*) bypasses the LLM completely. It responds in `< 15ms` with zero token consumption and zero rate-limit exposure.
4. **Multi-Layer Context Caching**:
   Against remote PostgreSQL databases (e.g. Supabase), decision context, personal profiles, and situations are cached for 60 seconds per user, eliminating 6.6s of sequential SQL queries on every turn. Write tools automatically invalidate the cache.
5. **Zero-Image-Storage Guarantee**:
   Uploaded images exist strictly in RAM for ephemeral visual extraction. Image bytes are never written to disk, databases, or logs. Only extracted context, OCR, and actionable items survive as durable memory.
6. **Sovereign Cross-Device Peer Interoperability**:
   Laptop and mobile phone operate as peer execution nodes across the IRIS Mesh. Commands spoken or typed on phone can spawn apps and shell sessions on laptop, and laptop commands can trigger native Android apps on phone in milliseconds.
7. **Cognitive Obsidian UI/UX**:
   Surfaces are rendered in deep obsidian (`#080A0F`, `#0D1117`, `#151B23`) with high-contrast typography (Chakra Petch display, Barlow body, JetBrains Mono telemetry). Luminous status beacons indicate AI activity without visual clutter.
8. **Sovereign Ownership & $0 Ongoing Cloud Cost**:
   The entire system runs on your local workstation and personal devices, relying on free-tier Supabase PostgreSQL and Google Gemini endpoints. No recurring SaaS subscriptions.

---

## 3. End-to-End System Architecture

```mermaid
flowchart TB
    subgraph Clients ["Client Layer"]
        Electron["🖥️ Native Windows Desktop<br/>(Electron 33, iris://app, Single-Instance Lock)"]
        MobileApp["📱 Android Native Companion<br/>(Capacitor 6 + Native AppLauncher)"]
        Browser["🌐 Web Browser Dashboard (Vercel Edge)"]
    end

    subgraph Gateway ["Transport & Protocol Layer"]
        CustomProto["Electron Transparent /api Proxy"]
        VercelEdge["Vercel Edge Gateway (Production)"]
        FastAPIRouter["FastAPI 0.115 Engine (:8000)"]
        LiveWS["/api/voice/live WebSocket<br/>(Gemini Live Full-Duplex PCM + Tool Calling)"]
    end

    subgraph Intelligence ["Multi-Agent Reasoning Core"]
        Supervisor["IrisSupervisor Orchestrator & Peer Dispatcher"]
        FastPath["Fast-Path Deterministic Interceptor<br/>(Spoken Prefix Normalization)"]
        Router["System 1 Intent Classifier (Gemma 4 31B)"]
        Operator["Operator Agent (CLI, Files, Apps, AGY Coding)"]
        Planner["Planner Agent (Chronos, Schedule, Tasks)"]
        Scribe["Scribe Agent (Notes, Gym, Yoga, Finance, CRM)"]
        BUBBA["BUBBA Agent (Gmail, Google Drive)"]
        Vision["Vision Service (Gemini 3.1 Flash-Lite / Serial Fallback)"]
    end

    subgraph MeshRelay ["Sovereign Mesh Fabric"]
        MeshService["Local Windows Mesh Service<br/>(MSS Screen Capture, Win32 Input, App Launcher)"]
        RelayService["Mesh Relay Service (Database Queue)<br/>(300s Symmetric Clock-Drift Resiliency)"]
        NativeCapacitor["Native Android App Launcher<br/>(Capacitor Plugin: launchPhoneApp)"]
    end

    subgraph Storage ["Persistence & Data Fabric"]
        SQLite["Local SQLite (iris.db, WAL Mode)"]
        Supabase["Supabase PostgreSQL 17<br/>(aws-0-ap-southeast-1)"]
        ContextCache["60s User Context Cache"]
        Memory["Contextual Memory Engine"]
    end

    Clients --> Gateway
    Gateway --> FastAPIRouter & LiveWS
    FastAPIRouter --> Supervisor & Vision
    LiveWS --> Supervisor & MeshRelay
    Supervisor --> FastPath
    Supervisor --> Router
    Router --> Operator & Planner & Scribe & BUBBA
    Operator & Planner & Scribe & BUBBA --> Storage & MeshRelay
    FastPath --> Storage & MeshRelay
    MeshRelay --> MeshService & NativeCapacitor
```

---

## 4. The Multi-Agent Swarm & Supervisor

At the center of IRIS's intelligence is `IrisSupervisor` ([`supervisor.py`](file:///C:/kirtan/IRIS/backend/app/agent/supervisor.py)), orchestrating domain specialists under an inverted single-front-door paradigm. The user speaks solely with IRIS; IRIS routes and delegates.

### 1. Deterministic Fast-Path Interceptor
Before any prompt touches an LLM API, `try_fast_path()` analyzes user intent with conversational speech normalization:
- **Natural Spoken Normalization (`norm_msg`)**: Strips conversational speech prefixes (`"hey iris"`, `"can you please"`, `"could you please"`, `"would you"`, `"please"`, etc.) before pattern matching.
- **Universal Dynamic Peer Action Dispatcher (Zero Hardcoding, Millisecond Execution)**:
  - Dynamically routes app launch commands to the target device (Windows Laptop vs Android Phone).
  - Target Resolution: Spoken indicators (`"on my laptop"`, `"on my phone"`) or device heuristics (mobile apps: WhatsApp, Camera, Instagram, GPay, Uber, Swiggy; desktop apps: Terminal, AGY CLI, VS Code, Explorer).
  - Millisecond execution without LLM roundtrips.
- **Time & Date**: Instant local timestamp formatting (~1.1s turn total).
- **Today's Tasks Checklist** (*"what are my today's tasks"*, *"today's tasks"*, *"show today's tasks"*): Returns an immediate formatted Markdown checklist with priority emojis (🔴 CRITICAL, 🟡 HIGH, ⚪ MEDIUM, 🟢 LOW), deadlines, and completed items in `< 15ms`.
- **Direct Task Creation** (*"create task [title]"*, *"add daily task [title]"*): Instantly creates tasks in the database with contextual area defaults and automatic end-of-day deadline.
- **Top Priority Task** (*"what's my task"*, *"what should I do"*): Calls `deterministic_decision(db, user)` to score all open tasks against deadlines, project weighting, and available schedule blocks.
- **Task Completion** (*"task done"*, *"completed task"*): Marks top open task complete and returns the next highest-leverage task.
- **Fitness & Yoga Checkoffs** (*"gym done"*, *"yoga done"*, *"asana done"*): Instantly marks daily workout / yoga routines and habits complete.
- **Workstation Commands** (*"lock pc"*, *"lock laptop"*, *"ring phone"*, *"open terminal"*, *"launch agy"*): Executes native commands instantly across the mesh.
- **Contextual Memory Search** (*"what do you remember about me"*): Retrieves stored key-value memories directly from the database.

### 2. Two-Tier Intent Routing
If the request requires complex execution:
1. **Tier 1 (Deterministic Keyword Match, 0ms)**: Instant rule-based classification.
2. **Tier 2 (System 1 Decision Engine, ~400ms)**: Uses Google Gemma 4 31B (`gemma-4-31b-it`) in a single forward pass with `temperature=0.0` and zero tool schema clutter to categorize into:
   - `[A]` **Operator**
   - `[B]` **Planner**
   - `[C]` **Scribe**
   - `[D]` **BUBBA**
   - `[E]` **Chat / Orchestrator**

### 3. Specialized Sub-Agents

| Sub-Agent | Primary Responsibilities | Available Tools |
|---|---|---|
| **Operator** | Workstation OS actions, controlled PowerShell/CLI execution, background tasks, directory navigation, file reading/writing/searching, process & port inspection, Antigravity (AGY) ConPTY autonomous coding dispatch, Windows app launching, and mobile app launching. | `execute_desktop_command`, `get_background_job_status`, `cancel_background_job`, `inspect_desktop_process`, `find_latest_laptop_file`, `run_laptop_terminal_command`, `read_laptop_file`, `write_laptop_file`, `search_laptop_files`, `launch_laptop_app`, `launch_mobile_app`, `start_autonomous_coding` |
| **Planner** | Chronos dynamic availability engine, schedule time-blocking, task hierarchies, subtask breakdown, project milestone tracking, daily review generation. | `create_task`, `update_task`, `complete_task`, `get_today_tasks`, `get_tasks`, `create_timeblock`, `get_daily_schedule`, `plan_day_draft` |
| **Scribe** | Personal knowledge & daily task management, journal entries, Gym lifting splits, daily all-week Yoga routines & asana tracking, habit streaks, personal finance (expenses, cash flow, budgets), startup CRM outreach pipeline. | `get_today_tasks`, `get_tasks`, `get_task`, `create_task`, `update_task`, `complete_task`, `delete_task`, `log_diary_entry`, `read_diary`, `log_workout`, `check_yoga_asana`, `log_expense`, `get_finances`, `update_lead_status` |
| **BUBBA** | Google Workspace ecosystem integration: Gmail inbox reading, thread triage, drafting replies, sending emails; Google Drive search and document analysis. | `list_unread_emails`, `search_emails`, `draft_email`, `send_email`, `search_drive_files`, `read_drive_document` |

### 4. Gemini 3.x Thought Signature Preservation
Gemini 3.x models emit provider-specific `extra_content.google.thought_signature` tokens on tool calls. The harness preserves these signatures on `ToolCallRequest` and echoes them back during multi-turn execution, while safely stripping them during failover to non-Gemini models (Gemma, Groq) to avoid HTTP 400 parameter errors.

### 5. Unified 10-Stage Agentic Reasoning Loop (`UnifiedReasoningEngine`)
In Version 3.4, IRIS has fundamentally evolved from a keyword/regex command router into a genuinely generative, reasoning-driven, context-aware autonomous personal intelligence system.

```mermaid
flowchart LR
    S1["1. Understand"] --> S2["2. Contextualize"]
    S2 --> S3["3. Reason"]
    S3 --> S4["4. Plan"]
    S4 --> S5["5. Select Capabilities"]
    S5 --> S6["6. Execute"]
    S6 --> S7["7. Observe"]
    S7 --> S8["8. Verify"]
    S8 --> S9["9. Adapt"]
    S9 --> S10["10. Respond"]
```

1. **Understand**: Interprets complex objectives, handles natural phrasing variations, resolves entity referents across conversation history ("the second one", "that task"), and detects queries answerable directly from context without calling unnecessary tools.
2. **Contextualize**: Synthesizes active personal model, situational context, and bounded long-term memories from `memory_service`.
3. **Reason**: Evaluates dependencies, risks, and feasibility before choosing an approach.
4. **Plan**: Formulates step-by-step execution workflows with verification checkpoints.
5. **Select Capabilities**: Matches required steps against the tool registry and validates execution policies.
6. **Execute**: Dispatches calls through `AgentHarness` (`native_tools` or `structured_json`).
7. **Observe**: Captures return data, exit codes, and side effects.
8. **Verify**: Authoritatively queries real state (database records, filesystem, running processes).
9. **Adapt**: Diagnoses errors (parameter error, transient, missing entity, unverified postcondition) and adapts parameters or reports discrepancies honestly.
10. **Respond**: Constructs evidence-grounded final reply. Never claims an action succeeded if postcondition verification failed.

### 6. Authoritative Postcondition Verification & Policy Gate
- **Tool Metadata Contract (`Tool`)**:
  - `risk_level`: `READ_ONLY`, `REVERSIBLE`, `ORDINARY_WRITE`, `SENSITIVE`
  - `verification_strategy`: `NONE`, `DB_CHECK`, `FILE_CHECK`, `PROCESS_CHECK`, `CUSTOM`
  - `requires_approval`: bool
  - `verify(db, user, result, **params)`: Authoritative postcondition check method.
- **Verification Enforcement**:
  - `CreateTaskTool` / `UpdateTaskTool`: Validates entity exists in database with matching attributes.
  - `CompleteTaskTool`: Validates entity is in `COMPLETED` status.
  - `DeleteTaskTool`: Validates entity is deleted and no longer present.
  - `CreateTimeBlockTool`: Validates block exists in schedule.
  - Unverified mutating actions (`verified: false`) are excluded from `actions_summary` and reported honestly.
- **Deterministic Approval Gate**:
  - Sensitive / destructive actions require cryptographic approval tokens (`appr_...`).
  - Without an approval token, tool execution halts with `APPROVAL_REQUIRED` and supplies a single-use token.
  - Execution proceeds only once the user replies with authorization (`approve <token>`).

### 7. Cross-Domain Orchestration & Subagent Context Continuity
- **Unstarved Core Agent**: `IrisAgent` possesses full capabilities across all domains (College, Internship, Startup, Personal, Desktop CLI, Mesh, Diary, Workouts, Email, Coding, and Finance). Cross-domain workflows are handled seamlessly by IRIS Core.
- **Context-Preserving Subagents**: When specialized single-domain subagents are dispatched (`Operator`, `Planner`, `Scribe`, `BUBBA`), the full conversation history is passed, eliminating the previous stateless `history=[]` context loss.

---

## 5. Universal Device Intelligence & Capability-Driven Execution (P2)

The P2 architecture fundamentally transforms IRIS from a system reliant on hardcoded device command dictionaries into an **autonomous, capability-driven cross-device personal operating system**.

### 1. The Core Principle
> **"IRIS must discover device capabilities rather than depend on hardcoded device-command mappings."**

When a user requests *"Open Google Drive on my laptop"*, IRIS:
1. Understands the user's objective and target device (`laptop_windows`).
2. Discovers whether Google Drive has a native desktop application installed.
3. Upon discovering no native `.exe` exists, avoids throwing a shell error and instead resolves the official web service destination (`https://drive.google.com`).
4. Discovers installed web browsers on the machine (Chrome, Edge, Brave, Firefox).
5. Launches the preferred browser navigating to the validated URL.
6. Verifies browser process initialization and reports verified success.

### 2. Typed Device Capability Contracts (`backend/app/devices/contracts.py`)
- **`DeviceType`**: `WINDOWS_LAPTOP` (`laptop_windows`), `ANDROID_PHONE` (`phone_android`), `LOCAL_AGENT`, `UNKNOWN`.
- **`CapabilityCategory`**: `APPLICATION`, `BROWSER`, `OS_CONTROL`, `FILESYSTEM`, `SYSTEM_INFO`, `TELEMETRY`, `AUTOMATION`.
- **`CapabilityRisk`**: `READ_ONLY`, `REVERSIBLE`, `ORDINARY_WRITE`, `SENSITIVE`, `CRITICAL`.
- **`DeviceExecutionRequest`**: Typed execution envelope with `request_id`, `correlation_id`, `target_device_id`, `capability_id`, `parameters`, `idempotency_token`, and `approval_token`.
- **`DeviceExecutionResult`**: Verified result envelope with `success`, `data`, `error`, `verified` boolean, `verification_details`, and `duration_ms`.

### 3. Windows Workstation Execution Engine (`backend/app/devices/windows/`)
- **Dynamic Application Discovery (`WindowsAppDiscovery`)**:
  - Automatically indexes 100% of installed desktop and store applications from:
    1. System-wide Start Menu shortcuts (`%ProgramData%\Microsoft\Windows\Start Menu\Programs\*.lnk`)
    2. User Start Menu shortcuts (`%AppData%\Microsoft\Windows\Start Menu\Programs\*.lnk`)
    3. Windows Registry App Paths (`HKLM` & `HKCU` `SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths`)
    4. Common Windows built-ins (`wt.exe`, `powershell.exe`, `cmd.exe`, `notepad.exe`, `calc.exe`, `explorer.exe`, `taskmgr.exe`, `ms-settings:`)
  - No static app dictionaries required. Automatically discovers newly installed applications at runtime.
- **Dynamic Browser Discovery & Service Fallback (`WindowsBrowserDiscovery`)**:
  - Dynamically detects available Windows browsers (Edge, Chrome, Brave, Firefox).
  - Enforces strict URL scheme validation (`http`/`https` only).
  - Resolves online productivity and enterprise destinations (`COMMON_SERVICE_URLS`: Google Drive, Google Docs, Google Sheets, Notion, Figma, GitHub, Linear, Trello, Spotify, etc.).
- **Native Win32 System Control (`WindowsSystemControl`)**:
  - Direct Win32 `LockWorkStation` API via `ctypes.windll.user32.LockWorkStation()`.
  - Native power telemetry via `Kernel32.GetSystemPowerStatus` (AC Line status, battery percentage, charging state).
  - OS architecture, memory, and filesystem queries.
- **Postcondition Verification (`WindowsDeviceExecutor`)**:
  - Verifies process creation, PID assignment, and survival past initial startup.
  - Bypasses Windows Foreground Lock Timeout by attaching thread input to bring requested windows directly to the top.

### 4. Android Companion Engine & Sovereign Mesh Transport (`backend/app/devices/android/`)
- **`AndroidDeviceExecutor`**:
  - Dispatches execution requests to the Realme GT 7T companion via Sovereign Mesh WebSockets (`MeshHub`) and DB relay queue.
  - **Offline Device Protection**: Queries live presence in registry and relay heartbeat; if phone is unreachable, returns structured error and **does not fake success**.
  - **Idempotency Protection**: Intercepts duplicate tokens, preventing redundant app launches or alert chimes.
- **Capacitor Native Bridge (`AppLauncherPlugin.java`)**:
  - Dynamic Intent package search (matches label dynamically if package unlisted).
  - Native `openUrl` capability for Android browser navigation.
  - Native `getBatteryStatus` via sticky `ACTION_BATTERY_CHANGED` intent.
  - Native `getNetworkStatus` via Android `ConnectivityManager` (WiFi vs Cellular).

### 5. Dynamic Device Target Resolver (`backend/app/devices/target_resolver.py`)
Intelligently resolves target device without rigid intent branches:
1. **Explicit Cues**: *"on my phone"*, *"on my mobile"* -> `ANDROID_PHONE`; *"on my laptop"*, *"on my computer"* -> `WINDOWS_LAPTOP` (confidence 0.98).
2. **Device-Exclusive Actions**: *"lock workstation"* -> `WINDOWS_LAPTOP` (confidence 1.0); *"ring phone"* -> `ANDROID_PHONE` (confidence 1.0).
3. **Application Affinity**: Mobile-first apps (WhatsApp, PhonePe, GPay, Camera) -> `ANDROID_PHONE`; Workstation dev tools (VS Code, Terminal, Antigravity IDE) -> `WINDOWS_LAPTOP`.
4. **Presence Awareness**: If ambiguous, defaults to active client surface.

### 6. Acceptance Testing Matrix (Tests A through J)
The entire P2 test suite ([`test_device_acceptance.py`](file:///C:/kirtan/IRIS/backend/tests/devices/test_device_acceptance.py)) passes with 100% compliance:
- **Test A (Android App Discovery)**: "Open WhatsApp on my phone" -> routes to phone, dispatches launch intent.
- **Test B (Windows App Discovery)**: "Open Chrome on my laptop" -> discovers app dynamically without hardcoding, launches and verifies.
- **Test C (Browser Fallback)**: "Open Google Drive on my laptop" -> detects no desktop `.exe` -> discovers browser -> navigates to `https://drive.google.com` -> verified.
- **Test D (Unlisted App)**: Newly installed application discovered and executed dynamically without code edits.
- **Test E (Target Resolution)**: Accurately resolves phone, laptop, battery, and workstation locking.
- **Test F (Missing Application)**: Uninstalled application accurately reports failure and **does not fake success**.
- **Test G (Offline Device)**: Unreachable companion safely returns error and **does not fake success**.
- **Test H (Permission Enforcement)**: Sensitive/destructive commands rejected without approval tokens.
- **Test I (Idempotency)**: Replay execution tokens suppressed.
- **Test J (Cross-Device Verification)**: End-to-end execution and result flow across Sovereign Mesh.

---

## 6. Ephemeral Multimodal Vision Pipeline

The vision pipeline ([`vision_service.py`](file:///C:/kirtan/IRIS/backend/app/services/vision_service.py)) provides ephemeral visual comprehension for receipts, invoices, error screens, syllabi, and documents.

```mermaid
flowchart TD
    UserUpload["User attaches 1–5 images"] --> ClientReader["FileReader -> RAM Data URIs"]
    ClientReader --> APIRoute["POST /api/chat/.../messages or /api/vision/ingest"]
    APIRoute --> VisionService["VisionService.analyze_ephemeral_images()"]
    
    VisionService --> BatchTry{"Attempt Batch Mode<br/>(Gemini 3.1 Flash-Lite)"}
    BatchTry -- "Success (~3.7s)" --> ParseJSON["Parse Structured Output"]
    BatchTry -- "Fails / 429 Rate Limit / 413 Payload" --> SerialMode["Serial Processing Mode<br/>(Image-by-Image with 0.5s pause)"]
    
    SerialMode --> SingleImgCall["Process Image i with 429 Backoff & Fallback"]
    SingleImgCall --> MergeResults["_merge_results():<br/>Combine OCR, Actions, Facts & Domain"]
    ParseJSON --> MergeResults
    
    MergeResults --> StoreContext["store_visual_context():<br/>Save extracted facts to memory (0 image bytes)"]
    StoreContext --> AgentEnrich["Enrich Agent Context with [📷 Visual Context]"]
    AgentEnrich --> AgentTurn["Agent Run Turn -> Final User Response"]
```

### Key Engineering Features:
1. **Multi-Image Support**: Accepts single `image_base64` or a list of `images: [ImageAttachment]` up to 10 MB per image.
2. **Resilient Serial Fallback**:
   - Tries fast batch analysis first (~3.7s).
   - If batch mode encounters an **HTTP 429 (rate limit)**, **HTTP 413 (payload too large)**, or timeout, it automatically pivots to serial mode without crashing.
   - In serial mode, each image is analyzed individually with an exponential backoff buffer, and all OCR text, actions, and facts are merged.
3. **Provider Failover**: Primary vision runs on `gemini-3.1-flash-lite`, automatically failing over to `nvidia/nemotron-3.5-super-vl-120b-a12b` if the Google endpoint is unavailable.
4. **Client Object URL Lifetime**: Object URLs in React are tracked via `useRef<Set<string>>` and revoked strictly on component unmount or explicit removal, eliminating premature thumbnail revocation.

---

## 7. Unified Voice Intelligence & Real-Time Screen Perception (P3)

IRIS unifies voice, text, and visual interactions into a single intelligence, memory, reasoning, permissions, and capability execution pipeline. There is no isolated voice assistant or restricted tool subset: spoken requests, conversational screen queries, and text chat share the identical P1 Supervisor, P2 Universal Device Capability Registry, and situational memory.

```mermaid
flowchart TD
    subgraph MultiModalInputs ["Multimodal User Inputs"]
        VoiceStream["Spoken Speech (Gemini Live Audio / STT)"]
        ChatText["Chat Text Message"]
        ScreenQuery["Visual Screen Query ('What's on my screen?')"]
    end

    subgraph NormalizationLayer ["Context & Voice Bridge Layer"]
        VoiceBridge["UnifiedVoiceBridge<br/>(/api/voice/live WebSocket Dispatcher)"]
        ScreenService["ScreenPerceptionService<br/>(Cross-Device Hardware Capture & Cache)"]
    end

    subgraph ReasoningLayer ["P1 Supervisor & Agentic Core"]
        Supervisor["IrisSupervisor.process()<br/>(Deterministic Fast-Paths & Multi-Agent Routing)"]
        IrisAgent["IrisAgent.run_turn()<br/>(Gemini 3.1 Flash-Lite + Multi-Agent Swarm)"]
        ActivePerceptionCache["ActiveVisualPerception Cache<br/>(120s Freshness Window, Zero Disk Storage)"]
    end

    subgraph ExecutionLayer ["P2 Universal Device Execution Layer"]
        P2Resolver["DeviceTargetResolver (Laptop vs Phone)"]
        WinExecutor["WindowsDeviceExecutor (App Discovery, Browser Fallback)"]
        AndroidExecutor["AndroidDeviceExecutor (Sovereign Mesh Remote Relay)"]
    end

    VoiceStream --> VoiceBridge
    ChatText --> Supervisor
    ScreenQuery --> ScreenService

    VoiceBridge --> Supervisor
    VoiceBridge --> P2Resolver
    ScreenService --> ActivePerceptionCache
    ActivePerceptionCache -.->|Injects Context| Supervisor
    ActivePerceptionCache -.->|Injects Context| IrisAgent

    Supervisor --> IrisAgent
    IrisAgent --> P2Resolver
    P2Resolver --> WinExecutor
    P2Resolver --> AndroidExecutor
```

### 1. Unified Voice Bridge (`UnifiedVoiceBridge`)
- **Zero-Silo Architecture**: Eliminates the previous hardcoded 9-function voice silo. Every voice request is dispatched to the unified P1/P2 infrastructure:
  - Spoken natural language commands route directly into `IrisSupervisor.process()`.
  - Application launches route to `UnifiedVoiceBridge.open_application()` with dynamic target resolution and browser fallback (e.g. *"Open Google Drive on my laptop"* launches Chrome or Edge at `https://drive.google.com` if native Drive is not installed).
  - Workstation controls route to `windows.system.lock` and `windows.system.battery`.
  - Task commands route to core `task_service`.
  - Screen perception queries route to `ScreenPerceptionService`.
- **Gemini Live Bidirectional Streaming (`/api/voice/live`)**:
  - Full-duplex conversational audio streaming with `gemini-3.8-live` and the `Enceladus` voice.
  - Dynamically registers typed callable tools via `bridge.get_callable_tools()` into `types.LiveConnectConfig`.
  - Complete backwards-compatible function interceptor in `gemini_to_client()` ensuring all legacy function names (`launch_laptop_app`, `launch_mobile_app`, `execute_terminal_command`, `get_laptop_status`, `lock_laptop`, `create_daily_task`, `get_today_tasks`, `complete_task`, `inspect_current_screen`) resolve to modern capability executors.

### 2. Universal Screen Perception (`ScreenPerceptionService`)
- **Cross-Device Dynamic Capture**:
  - **Windows Workstation**: Ephemeral GDI hardware buffer capture via native Win32/MSS API.
  - **Android Companion**: Real-time screen capture via Sovereign Mesh WebSocket and native `AppLauncher.captureScreen` (PixelCopy).
- **Zero-Image-Storage Guarantee**: Raw screenshots exist strictly in RAM during analysis (`VisionService.analyze_ephemeral_images`) and are immediately purged. No raw image bytes are persisted to disk, the database, conversation logs, or telemetry.
- **Active Visual Perception Cache (`ActiveVisualPerception`)**:
  - Holds structured OCR text, UI elements, bounding coordinates, detected domain, and visual summary.
  - Formatted into `[📷 ACTIVE VISUAL CONTEXT]` and injected into conversational prompts in `IrisSupervisor` and `IrisAgent._build_system_prompt()`.
- **Visual Freshness & Change Detection**:
  - Enforces a 120-second validity window. If a follow-up is asked after 120 seconds or after screen contents change, IRIS explicitly advises the user: *"My previous view of your screen is X minutes old and may have changed. Please ask me to inspect your screen again so I can give you an accurate, up-to-date answer."*
- **Grounded Visual Follow-ups**: Follow-up questions (*"Which button should I click to proceed?"*, *"What does this error mean?"*) use the active visual perception to pinpoint elements accurately without hallucinating fake actions.

### 3. Mandatory Acceptance Test Verification (Tests A through L)
Full acceptance test suite located at `backend/tests/voice_vision/test_voice_vision_acceptance.py`:
- **Test A: Voice and Chat Equivalence**: Spoken and chat commands (*"Open WhatsApp on my phone"*) execute through identical target resolution, capability selection, and verification semantics.
- **Test B: Windows Voice Control**: Spoken *"Open Chrome on my laptop"* executes Windows app launch and returns confirmation.
- **Test C: Browser Fallback Through Voice**: Spoken *"Open Google Drive on my laptop"* discovers Chrome, opens Drive URL, and confirms cleanly without error.
- **Test D: Voice Follow-Up Context**: Multi-turn spoken task creation, daily task listing, and task completion verified with real database state changes.
- **Test E: Android Screen Perception**: Mobile screen captured via WebSocket/PixelCopy, analyzed ephemerally with zero files written to disk.
- **Test F: Windows Screen Perception**: Windows workstation screen captured via in-memory buffer with zero files written to disk.
- **Test G: Visual Follow-Up**: Accurately identifies button elements (*"Proceed to Pay"*) from active visual context without fake clicks.
- **Test H: Visual Change Detection**: Successfully detects stale context (> 120s) and prompts for a fresh look.
- **Test I: Permission Denial**: Gracefully handles screen capture permission denial or cancellation without hallucination.
- **Test J: Mesh Disconnection**: Safely reports offline laptop status when unreachable on Sovereign Mesh.
- **Test K: Multimodal Execution**: Ephemeral screen error capture (*"Connection refused port 5432"*) grounds the turn to provide targeted remediation.
- **Test L: Gemini Live Tool Dispatch**: Verifies backward-compatible dispatch across all 9 legacy functions.
- **Regression Safety**: All 476 backend tests pass with 0 regressions.

---

## 8. Sovereign Mesh Network & Remote Desktop Mirroring

The **Sovereign Mesh** connects your mobile phone (on any 5G network or hotel Wi-Fi) with your Windows laptop workstation at **$0 cloud cost**, without open router ports, dynamic DNS, or third-party paid tunnels (like ngrok).

```mermaid
flowchart LR
    subgraph Phone ["📱 Mobile Companion (5G Cellular)"]
        PhoneUI["/companion or More → Mesh"]
        DisplayPIN["1. Displays 6-Digit PIN (e.g. 582 109)"]
        SaveToken["3. Saves Permanent Token to localStorage"]
        StreamDisplay["4. WebRTC Video View & Touch Canvas"]
    end

    subgraph CloudRelay ["☁️ Supabase Cloud Relay ($0 Managed)"]
        PairingsTable["mesh_pairings"]
        MessagesTable["mesh_relay_messages"]
        STUNGW["Google Public STUN (stun.l.google.com:19302)"]
    end

    subgraph LaptopHost ["💻 Windows Workstation (Local Daemon)"]
        EnterPIN["2. Enters PIN on /mesh & Clicks Pair"]
        RelayDaemon["LaptopRelayDaemon (1.0s Polling Loop)"]
        GDIScreen["Desktop Capture (MSS / GDI 30 FPS)"]
        Win32Input["Win32 Input (mouse_event / keybd_event)"]
        OSControl["Windows Lock / App Launchers"]
    end

    DisplayPIN --> PairingsTable
    EnterPIN --> PairingsTable
    PairingsTable -- "Activated" --> SaveToken
    PhoneUI -- "LOCK_PC / LAUNCH_APP / Terminal" --> MessagesTable
    MessagesTable --> RelayDaemon
    RelayDaemon --> OSControl & Win32Input
    GDIScreen -- "P2P WebRTC Stream (via STUN)" --> StreamDisplay
    StreamDisplay -- "Touch Coordinates (X, Y)" --> MessagesTable
    MessagesTable --> RelayDaemon
    RelayDaemon --> Win32Input
```

### The 3-Step Zero-QR Handshake
1. **Phone Opens Pairing**: On phone, navigate to `https://iris.example.com/companion` (or **More &rarr; Mesh**). The phone creates an active invite and renders a bold 6-digit PIN.
2. **Laptop Verifies**: On your laptop, open `/mesh`, type the 6-digit PIN, and click **"Pair Phone Forever"**.
3. **Mutual Handshake**: Supabase marks the pairing record active. The phone immediately receives the verification and saves `iris_pair_token` to `localStorage`. Both devices are linked indefinitely.

### Remote Workstation Capabilities Over Mesh
- **Workstation Security**: Instant remote lock (`LockWorkstation` / Sovereign Privacy Shield).
- **Find My Phone**: Ring phone at 100% volume through web audio even if set on silent.
- **Universal Clipboard**: Instant two-way copy/paste synchronization.
- **Autonomous Coding Task Dispatch**: Start background coding tasks via Antigravity CLI from your phone while away from your desk.
- **WebRTC Remote Desktop Mirroring**: Stream your Windows desktop at 30 FPS to your phone with touch-to-click and mobile keyboard input.
- **Bidirectional Native App Launching**:
  - *Phone to Laptop*: Launch Terminal, Antigravity IDE, VS Code, or custom shell commands on your Windows PC.
  - *Laptop to Phone*: Trigger native Android intents to launch WhatsApp, Camera, Settings, GPay, Uber, etc.
- **Hardware Telemetry & Battery Monitoring**: Real-time battery level percentage and charging state tracked and spoken by the agent.

### 4. Clock-Drift Resilient Telemetry Engine
In asymmetric networks (Vercel serverless cloud + Windows laptop + Android 5G), minor NTP system clock skews can cause false-positive offline states.
- **Symmetric Clock-Drift Window**: Uses `abs(now - last_seen) < 300.0s`, allowing symmetric clock drift up to 5 minutes between serverless functions and client devices.
- **Active Heartbeat & Relay Sync**: The laptop daemon updates `last_seen` every 3 seconds while actively processing commands, guaranteeing continuous availability reporting.

---

## 9. JARVIS-Style Ambient Activation & Always-Available Operating System (P4)

In P4, IRIS completes its evolution from an application-based assistant into a **JARVIS-style ambient personal operating system**. Rather than opening an application, switching tabs, and clicking buttons, IRIS is accessible on-demand from any Android screen (Realme GT 7T) or Windows workspace.

```mermaid
flowchart TD
    subgraph TriggerSurfaces ["P4 Activation Surfaces (Realme GT 7T)"]
        T1["Power Button Long Press<br/>(Realme UI Voice Assistant)"]
        T2["Bottom-Corner Inward Swipe<br/>(System Navigation Gesture)"]
        T3["Quick Settings Tile<br/>(IrisQuickTileService)"]
        T4["1x1 Glowing Home Widget<br/>(IrisWidgetProvider)"]
        T5["Launcher App Shortcuts<br/>(shortcuts.xml)"]
    end

    subgraph NativeAndroidSystem ["Native Android Layer (Realme UI / ColorOS)"]
        VIS["IrisVoiceInteractionService<br/>(ROLE_ASSISTANT)"]
        VISS["IrisVoiceInteractionSession<br/>(System Window Floating Layer)"]
        TransAct["AssistantActivity<br/>(AppTheme.Translucent Edge-to-Edge)"]
        OverlaySvc["IrisAmbientService<br/>(ForegroundServiceType: Microphone)"]
    end

    subgraph AmbientUIUX ["Luminous Visual & Audio Experience"]
        EdgeGlow["IrisOverlayView<br/>• Edge-to-Edge Border Glow<br/>• Amplitude-Reactive Pulse<br/>• State Machine (Idle→Listen→Think→Speak)"]
        VoiceClient["IrisAmbientVoiceManager<br/>• 24kHz Mono 16-bit PCM AudioRecord<br/>• WebSocket Client (irisai.runs-on.dev / Local)<br/>• AudioTrack 24kHz Direct Playback<br/>• Direct Tool Dispatcher (App Launch, Screen)"]
    end

    subgraph IRISCoreMesh ["IRIS Sovereign Core & Mesh"]
        VoiceWS["FastAPI /api/voice/live<br/>(Gemini Live / Sovereign Supervisor)"]
        P1Supervisor["IrisSupervisor<br/>• Goal Breakdown & Re-planning<br/>• Deterministic Fast Paths"]
        P2Registry["Capability Registry<br/>• UniversalAppTool<br/>• WindowsDeviceExecutor<br/>• AndroidDeviceExecutor"]
        P3Perception["ScreenPerceptionService<br/>• Ephemeral Capture<br/>• Zero Storage"]
    end

    TriggerSurfaces --> VIS & TransAct & OverlaySvc
    VIS --> VISS
    VISS & TransAct & OverlaySvc --> EdgeGlow & VoiceClient
    VoiceClient <-->|Bi-directional PCM & Events| VoiceWS
    VoiceWS <--> P1Supervisor
    P1Supervisor --> P2Registry & P3Perception
```

### 1. Realme GT 7T Hardware & OS Integration Feasibility
- **Default Digital Assistant (`ROLE_ASSISTANT`)**: Registered via `IrisVoiceInteractionService` with `android.permission.BIND_VOICE_INTERACTION`. Setting IRIS as the Default Digital Assistant in Realme UI allows instant zero-overhead activation.
- **Hardware Power Key Long-Press**: Configured in Realme UI (`Settings > Additional Settings > Power Button > Voice Assistant`) to invoke the system assistant directly.
- **Bottom-Corner Navigation Swipe**: System-wide gesture navigation corner swipe automatically routes to `IrisVoiceInteractionSession`.
- **Quick Settings Tile**: `IrisQuickTileService` placed in notification drawer for one-tap system-wide invocation.
- **1x1 Glowing Home Widget**: `IrisWidgetProvider` for instantaneous one-touch launcher entry.
- **OEM Back-Tap Notice**: ColorOS/Realme UI restricts back-tap gestures to built-in system apps (Flashlight, Camera) without exposing a public third-party Android API. Simulating back-tap via continuous accelerometer polling causes severe battery drain and is actively terminated by OEM power managers. Therefore, native Power Button, Corner Swipe, and Quick Tile are the certified, zero-drain activation mechanisms.

### 2. Floating IRIS Voice Sphere & Ambient Visual Engine

#### A. Floating IRIS Voice Sphere (`IrisSphereView.java`, `IrisSphereService.java`, `IrisSphereActivity.java`)
- **Primary Ambient Experience**: Replaces full-application activation with a compact 68dp holographic orb floating directly on the Android `WindowManager` (`TYPE_APPLICATION_OVERLAY`).
- **Zero Full-App Interruption**: Calling `IrisSphereActivity` launches `IrisSphereService`, triggers `moveTaskToBack(true)`, and finishes immediately. The underlying application (e.g. WhatsApp, Chrome, YouTube) remains uninterrupted on screen while the sphere hovers above it.
- **Immediate Listening**: Upon appearance, `IrisAmbientVoiceManager` starts audio capture immediately without requiring any secondary user tap.
- **Visual Design & Physics**:
  - *Multi-Layer Depth*: Deep dark glass disc (`#141724`), central glowing nucleus (`#00E5FF`), rotating orbital energy ring (`#7C4DFF`), dynamic particle glow.
  - *State Machine*: Reacts to conversational state (`STATE_LISTENING`, `STATE_PROCESSING`, `STATE_SPEAKING`, `STATE_EXECUTING`, `STATE_IDLE`).
  - *Audio Amplitude Pulsing*: Nucleus and orbital rings pulse in real-time with incoming/outgoing microphone and speaker RMS levels.
  - *Interactive Physics*: Smooth dragging with display boundary clamping, velocity flicking, and magnetic snapping to the nearest screen edge (left or right).
  - *Micro-Gestures*: Single tap toggles listening/pause; long-press or fling downward dismisses the sphere.
- **Realme GT 7T Gesture Integration**:
  - `IrisSphereActivity` is registered with `category.LAUNCHER` under the label `"IRIS Voice Sphere"`.
  - In Realme UI (*Settings → Special features → Gestures & motions → Screen-off gestures → Draw M → Open an app*), selecting **IRIS Voice Sphere** activates the voice orb directly from the lock screen upon unlock.

#### B. Luminous Edge-Glow Visual Engine (`IrisOverlayView.java`)
- **Google Assistant-Inspired Aesthetics**: Displays a full-perimeter animated luminous glow around display edges without obscuring the underlying application content.
- **Real-Time Audio Amplitude Modulation**: Real-time microphone RMS amplitude modulates border thickness and glow intensity dynamically during speech (`setAudioAmplitude`).
- **State Machine**:
  - `STATE_LISTENING`: Luminous cyan (`#00E5FF`) and electric blue (`#00B0FF`).
  - `STATE_PROCESSING`: Deep violet (`#7C4DFF`) and pulse wave.
  - `STATE_EXECUTING`: Warm amber / gold (`#FFB300`) indicating device or workstation execution.
  - `STATE_SPEAKING`: High-intensity cyan wave synchronized to incoming audio chunks.
  - `STATE_ERROR`: Crimson (`#FF5252`) indication.
- **Fluid Dismissal**: Tapping outside or swiping down instantly dismisses the overlay and terminates audio pipelines.

### 3. Screen Perception Architecture & Hardware Framebuffer Capture (`IrisScreenCaptureManager.java`)
- **Dual-Path Hardware Framebuffer Engine**:
  1. *VoiceInteractionSession Path*: When running as the default system digital assistant, uses Android's native `VoiceInteractionSession.onHandleScreenshot(Bitmap screenshot)` hook to obtain unoccluded hardware framebuffer snapshots directly from the window manager without user prompts.
  2. *MediaProjection / VirtualDisplay Path*: Uses Android's `MediaProjection` API paired with an `ImageReader` (`PixelFormat.RGBA_8888`) and `VirtualDisplay` to capture display output in 1080p, converting downsampled framebuffers into JPEG byte arrays.
- **Native Android Bridge Fallback Fix**:
  - Standard web browsers support `navigator.mediaDevices.getDisplayMedia()`, but Android WebView Chromium does not, producing the error `"screen perception is not supported by this browser engine"`.
  - `screenCapture.ts` cleanly separates environments: native Android routes directly to `IrisAmbient.captureScreenNative()` and `AppLauncher.captureScreen()`, while desktop Chrome / Electron uses `getDisplayMedia()`.
- **WebSocket Roundtrip Protocol**:
  1. Spoken query *"What is on my screen?"* triggers Gemini Live / P1 Supervisor tool `inspect_screen`.
  2. Backend `ScreenPerceptionService` emits WebSocket message `{"type": "request_screen_capture", "request_id": "cap_xyz"}`.
  3. `IrisAmbientVoiceManager` captures the hardware framebuffer via `IrisScreenCaptureManager.captureCurrentDisplay` and replies with `{"type": "screen_capture_response", "request_id": "cap_xyz", "image_base64": "..."}`.
  4. Backend fulfills the pending future, analyzes the buffer ephemerally through `VisionService`, and updates `ActiveVisualPerception`.
- **Zero-Image-Storage Guarantee**:
  - Raw image bytes exist strictly in RAM during model inference; no screenshots are saved to disk, object stores, or databases.
  - Only structured text summaries, extracted code, and UI elements are retained in the 120s active visual perception cache.
- **Change Detection & Grounded Follow-up**:
  - Follow-up questions asked within 120 seconds are grounded directly in the active visual context without taking redundant screenshots.
  - Queries after 120 seconds trigger change detection, prompting the user: *"My previous view of your screen is X minute(s) old and may have changed. Please ask me to inspect your screen again."*

### 4. Audio Streaming, Zero Surveillance & Privacy Architecture (`IrisAmbientVoiceManager.java`)
- **Zero Background Surveillance**: Microphone hardware is **never** accessed while idle. Audio hardware is opened only on user-initiated activation and immediately stopped and released upon turn completion or dismissal. Fully complies with Android 14/15 `FOREGROUND_SERVICE_MICROPHONE` enforcement.
- **Audio Pipeline**: 24,000 Hz, 16-bit mono PCM capture and playback.
- **Direct WebSocket Link**: Streams directly to `/api/voice/live` on the production cloud or local daemon.
- **Autonomous Local Tool Dispatching**: If the multi-agent supervisor instructs a local mobile action (e.g. `launch_mobile_app` or screen capture), the native manager dispatches directly to `AppLauncherPlugin` or `ScreenPerceptionService` without WebView roundtrips.

---

## 10. Comprehensive Tech Stack Breakdown

### Frontend (User Interface)
- **Framework**: React 18.3 Single Page Application (SPA) with TypeScript 5.6.
- **Mobile Container**: Capacitor 6 (`@capacitor/core`, `@capacitor/android`) with custom native plugins for app launching (`AppLauncher`) and system settings.
- **Bundler & Tooling**: Vite 6.4 with `@vitejs/plugin-react` and `vite-plugin-pwa`.
- **Styling**: Tailwind CSS 3.4 with custom "Cognitive Obsidian" palette variables.
- **State & Server Cache**: TanStack React Query v5 (`@tanstack/react-query`) with automatic query key invalidation and optimistic mutations.
- **Routing**: Lightweight history-based custom router with hash navigation support and URL synchronization.
- **Iconography**: Lucide React (`lucide-react`).

### Backend (API & Intelligence Server)
- **Framework**: FastAPI 0.115 on Python 3.13.
- **ASGI Server**: Uvicorn with async event loops.
- **ORM & Data Layer**: SQLAlchemy 2.0 with both synchronous (`Session`) and connection-pooled execution modes.
- **Database Driver**: `psycopg 3` (PostgreSQL) and native `sqlite3` (SQLite).
- **Schema Migrations**: Alembic 1.14.
- **Data Validation**: Pydantic v2.

### AI & Reasoning Engine
- **Active Chat & Multi-Agent Core**: Google Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite`) with multi-tier failover across Groq (`qwen/qwen3.8-27b`), `gemma-4-26b-a4b-it`, and `gemini-3.5-flash`.
- **Router Model**: Google Gemma 4 31B (`gemini:gemma-4-31b-it`) for zero-overhead single-token JEV classification.
- **Ephemeral Vision**: `gemini-3.1-flash-lite` (batch + serial fallback) with fallback to `nvidia/nemotron-3.5-super-vl-120b-a12b`.
- **Live Bidirectional Audio Engine**: Google GenAI SDK (`google.genai` Live API, `gemini-3.8-live`) with registered sovereign tools (`launch_laptop_app`, `launch_mobile_app`, `execute_terminal_command`, `get_laptop_status`, `lock_laptop`) and real-time `tool_call` response handling.
- **Voice STT**: `gemini-3.5-transcribe` / Groq Whisper / HTML5 Web Speech.
- **Voice TTS**: `gemini-3.8-flash-tts` with `Enceladus` voice.
- **Autonomous Coding**: Antigravity (AGY) ConPTY PTY bridge.

### Native Desktop Packaging
- **Runtime**: Electron 33.
- **Distribution**: Standalone Windows package in `desktop/dist/IRIS-win32-x64/IRIS.exe`.
- **Dual-Mode Serving**: Automatically loads production URL for zero-friction OTA updates while seamlessly falling back to local `dist-frontend`.
- **Single-Instance Lock**: Prevents duplicate processes; automatically restores and focuses existing window when relaunched.
- **API Proxy**: In-process proxying of `/api/*` requests to the local FastAPI backend daemon on `127.0.0.1:8000`.
- **System Tray**: Windows system tray integration with background minimization, global hotkeys (`Alt+I`), and an auto-resurrecting backend watchdog.

---

## 10. Hosting, Environments & Deployment Topologies

### Topology A: Native Windows Desktop Workstation (Current Daily Driver)
- **Backend**: Runs locally as a silent Windows background process via `start-mesh-silent.vbs` on port 8000.
- **Frontend**: Served directly through Electron (`iris://app/index.html`) reading precompiled static assets from `desktop/dist-frontend`.
- **Database**: Local `backend/iris.db` (SQLite with WAL mode) or remote Supabase PostgreSQL.
- **Launcher**: Double-click [`start-iris-app.bat`](file:///C:/kirtan/IRIS/start-iris-app.bat) or press `Alt+I`.

### Topology B: Cloud Serverless (Vercel + Supabase)
- **Frontend**: Hosted globally on Vercel's Edge Network (`/` &rarr; `frontend/dist`).
- **Backend**: Serverless FastAPI execution via `api/index.py` (`/api/*`).
- **Database**: Supabase Managed PostgreSQL 17 connected via Transaction Pooler (`:6543`) with SQLAlchemy `NullPool`.
- **Configuration**: Documented in [`VERCEL.md`](file:///C:/kirtan/IRIS/VERCEL.md).

### Topology C: Self-Hosted VPS (Coolify / Docker Compose)
- **Containers**: Two Docker containers (Frontend Nginx + Backend FastAPI) connected over an internal bridge network.
- **Reverse Proxy**: Coolify / Traefik providing automatic Let's Encrypt SSL on a single domain.
- **Database**: Persistent SQLite volume mounted at `/app/data/iris.db` with automated Alembic migrations on container startup.
- **Configuration**: Documented in [`COOLIFY.md`](file:///C:/kirtan/IRIS/COOLIFY.md) and [`docker-compose.yml`](file:///C:/kirtan/IRIS/docker-compose.yml).

### Topology D: Managed Cloud Container (Render + Supabase)
- **Backend**: Render Web Service running Uvicorn workers with `alembic upgrade head` pre-deploy hook.
- **Database**: Supabase PostgreSQL connected via Session Pooler (`:5432`).
- **Configuration**: Documented in [`SUPABASE.md`](file:///C:/kirtan/IRIS/SUPABASE.md).

---

## 11. Codebase Anatomy & Directory Tree

```text
C:\kirtan\IRIS\
├── api/                        # Vercel serverless entrypoint
│   └── index.py                # Serverless FastAPI adapter
├── backend/                    # Core Python intelligence backend
│   ├── app/
│   │   ├── agent/              # Multi-agent system
│   │   │   ├── agents/         # Sub-agents (operator, planner, scribe, bubba)
│   │   │   ├── tools/          # Discrete agent tools (tasks, mesh, finance, workouts)
│   │   │   ├── supervisor.py   # IrisSupervisor orchestrator & fast-paths
│   │   │   └── harness.py      # LLM invocation harness & retries
│   │   ├── ai/                 # Multi-provider AI abstractions (Gemini, NVIDIA, Groq)
│   │   │   ├── capabilities.py # Model feature profiles & token limits
│   │   │   ├── factory.py      # Dynamic provider instantiator & failover chains
│   │   │   └── providers/      # Provider implementations
│   │   ├── api/routes/         # FastAPI REST endpoints (chat, vision, mesh, voice)
│   │   ├── core/               # Configuration, security, database session setup
│   │   ├── intelligence/       # Deterministic priority engine & time allocator
│   │   ├── models/             # SQLAlchemy ORM models (Task, Goal, Workout, Mesh)
│   │   ├── services/           # Business logic (vision, mesh_relay, screen, memory)
│   │   └── main.py             # FastAPI app instantiation & lifespan
│   ├── alembic/                # Database schema migrations
│   ├── run_daemon.py           # Workstation daemon runner
│   └── requirements.txt        # Python dependency manifest
├── frontend/                   # React 18 / Vite SPA
│   ├── src/
│   │   ├── components/         # Reusable UI primitives (dialogs, buttons, cards)
│   │   ├── features/           # Domain feature views
│   │   │   ├── ai/             # Ask IRIS overlay console
│   │   │   ├── gym/            # Gym splits & dedicated all-week Yoga flow
│   │   │   ├── home/           # Today dashboard, priority recommendations, and voice live
│   │   │   ├── mesh/           # Sovereign mesh manager & screen mirroring
│   │   │   ├── schedule/       # Chronos calendar & time blocks
│   │   │   └── startup/        # Outreach CRM & experiment pipeline
│   │   ├── hooks/              # TanStack Query hooks (useWorkouts, useTasks)
│   │   ├── lib/                # Shared utilities & Capacitor native bridges (appLauncher.ts)
│   │   └── modules/            # Navigation registry & module metadata
│   └── package.json            # Frontend dependency manifest
├── desktop/                    # Native Electron application
│   ├── dist/                   # Standalone packaged distribution
│   │   └── IRIS-win32-x64/     # Prebuilt Windows portable binary
│   │       └── IRIS.exe        # Standalone executable
│   ├── dist-frontend/          # Synchronized production frontend bundle
│   ├── main.cjs                # Electron main process (iris:// protocol & tray)
│   └── package.json            # Desktop Electron dependencies
├── scripts/                    # Maintenance & automation scripts
│   ├── install-desktop.ps1     # Automated Electron packager & frontend asset copier
│   └── migrate_to_supabase.py  # SQLite to Supabase database migration script
├── reinstall-desktop.bat       # One-click clean reinstall of desktop app
├── start-iris-app.bat          # Workstation desktop app launcher
├── start-mesh-silent.vbs       # Silent background backend daemon launcher
├── COOLIFY.md                  # VPS production deployment instructions
├── SUPABASE.md                 # PostgreSQL migration & Supabase guide
└── VERCEL.md                   # Serverless deployment guide
```

---

## 12. Operational Runbook & Developer Cheatsheet

### 1. Launching IRIS on the Windows Workstation
```powershell
# Quick Launch (Starts background daemon & launches native Electron UI):
C:\kirtan\IRIS\start-iris-app.bat
```

### 2. Running Local Development Servers Manually
```powershell
# Terminal 1: Start Backend (FastAPI on Port 8000)
cd C:\kirtan\IRIS\backend
.\.venv\Scripts\Activate.ps1
python run_daemon.py

# Terminal 2: Start Frontend (Vite on Port 5173)
cd C:\kirtan\IRIS\frontend
npm run dev
```

### 3. Running Test Suites
```powershell
# Backend Pytest Suite (464 passed)
cd C:\kirtan\IRIS\backend
.\.venv\Scripts\python.exe -m pytest -q

# Frontend Typecheck & Build
cd C:\kirtan\IRIS\frontend
npm run build
```

### 4. Applying Database Migrations
```powershell
cd C:\kirtan\IRIS\backend
alembic upgrade head
```

### 5. Synchronizing Frontend Build into Desktop App
Whenever frontend code in `frontend/src` is modified, rebuild and sync into Electron:
```powershell
cd C:\kirtan\IRIS\frontend
npm run build
Copy-Item -Recurse -Force "dist\*" "..\desktop\dist\IRIS-win32-x64\resources\app\dist-frontend\"
```

### 6. Clean Desktop App Reinstallation
To wipe stale Electron processes and reinstall the native desktop executable from scratch:
```bat
C:\kirtan\IRIS\reinstall-desktop.bat
```

### 7. Over-the-Air (OTA) Zero-APK Mobile Updates
Because the Android app is powered by a modern Capacitor WebView pointing to your production web deployment, code updates require zero Android Studio re-compilations:
```powershell
# 1. Commit and push to main
git push origin main
# 2. Vercel automatically deploys the updated frontend and serverless API
# 3. Open the IRIS app on your Android phone — the new features appear instantly!
```

---
*IRIS Architecture Specification & Knowledge Transfer Guide — Maintained by Core Engineering.*
