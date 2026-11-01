# Reimagining IRIS

## Product Vision, Architecture, Ecosystem, and Experience Redesign

**Status:** Consolidated product direction and design decisions\
**Date:** 31 October 2026

------------------------------------------------------------------------

## 1. Executive vision

IRIS is being reimagined as a personal AI operating system: a
coordinated environment in which an intelligent assistant, a coworker
ecosystem, projects, coding agents, devices, memory, schedules, and
computer-use capabilities work together.

The redesign is not a replacement of IRIS's existing identity or core
architecture. It is an expansion of the product into a more capable,
adaptive, and user-governed system.

The central idea is:

> **IRIS is the control plane for intelligent work.** It understands the
> user's intent, chooses the right capability or coworker, coordinates
> execution, presents progress clearly, and keeps the user in control of
> permissions and important decisions.

IRIS should be able to help with ordinary conversations, manage ongoing
responsibilities, delegate substantial work to specialised coworkers,
operate approved tools and computers, coordinate coding agents, and
adapt its own workspace to the user's current needs.

The system should remain modular and provider-independent. Its core
capabilities must not depend on a mandatory proprietary cloud, paid SaaS
subscription, or closed-source component.

## 2. Product principles

1.  **One coherent IRIS:** Conversations, coworkers, projects, tasks,
    devices, memory, and automation should feel like parts of one
    operating system rather than disconnected products.
2.  **User authority:** IRIS may coordinate and act autonomously within
    granted permissions. The user retains control over access,
    approvals, overrides, and consequential decisions.
3.  **Useful autonomy:** Autonomy should reduce repetitive work, not
    make the system opaque. Show what is happening, what has changed,
    and what needs the user's attention.
4.  **Modular architecture:** Models, coding agents, computer-use
    systems, and other providers should be replaceable through adapters.
5.  **Open-source-first:** Third-party software selected for IRIS must
    be free and open-source under an acceptable licence. Avoid mandatory
    proprietary services.
6.  **Local-first where practical:** Prefer user-controlled local
    execution and storage for sensitive work. Remote or hosted execution
    should be optional and explicitly governed.
7.  **Context with boundaries:** Use relevant project, conversation, and
    agent history without indiscriminately injecting every historical
    message into every task.
8.  **Consistent identity, adaptive interface:** Preserve IRIS's
    existing logo and sphere while allowing the workspace around them to
    adapt to context and platform.
9.  **Platform-appropriate experiences:** Desktop and Android should
    share product concepts and preferences, but each should have an
    interface designed for its own form factor.
10. **Observable and recoverable execution:** Long-running work should
    have visible status, logs or summaries, pause/resume where
    supported, and a clear route to recover from errors.

------------------------------------------------------------------------

# Part I --- The coworker ecosystem

## 3. From a single assistant to an ecosystem of coworkers

IRIS should evolve beyond a single assistant that performs every task
through one general-purpose interaction loop.

The proposed model is a **coworker ecosystem**. A coworker is a
specialised AI worker with a defined role, responsibilities, tools,
workspace, and execution context. The user can delegate work to a
coworker while IRIS coordinates the overall effort.

Examples of possible coworker roles include:

-   Research coworker
-   Software development coworker
-   Project or operations coworker
-   Writing and documentation coworker
-   Data analysis coworker
-   Browser and web research coworker
-   Personal productivity coworker

These are examples, not a fixed mandatory catalogue. The ecosystem
should be extensible so that new roles can be introduced as capabilities
become available.

### 3.1 Coworker identity and responsibility

Each coworker should have a clear definition:

-   Name and role
-   Responsibility and scope
-   Available tools and capabilities
-   Workspace and relevant files
-   Permission profile
-   Current task and status
-   Relevant history and working context
-   Outputs, findings, and handoff notes

A coworker should not simply be a different chat persona. It should be a
persistent work identity that can own or continue a responsibility, use
approved tools, and report progress.

### 3.2 Coworker workspaces

A coworker may need its own working environment, including:

-   A dedicated workspace for files and intermediate work
-   Browser access where permitted
-   Approved tools and integrations
-   A task-specific context
-   A way to inspect or hand over its work
-   A way for the user to watch its activity or take control

The workspace should be isolated according to the task's risk and
permission requirements. A coworker should not automatically receive
unrestricted access to the user's entire computer or filesystem.

### 3.3 Watch and take control

The user should be able to:

-   See what a coworker is working on
-   Inspect its current status and recent actions
-   Review outputs and evidence
-   Take control when needed
-   Pause or stop work where supported
-   Provide additional instructions
-   Resume or redirect a task

The goal is transparent delegation, not a black box that disappears
after receiving an instruction.

### 3.4 Persistent responsibilities and routines

Coworkers may hold ongoing responsibilities rather than existing only
for one chat turn. Examples include maintaining a project workspace,
preparing recurring summaries, or continuing a multi-step research task.

Any recurring or conditional work must be visible and governed. The user
should be able to understand what is scheduled, what can trigger an
action, and how to stop it.

## 4. Inspiration from OpenBot

The OpenBot project was explored as a reference for the coworker
concept.

Useful ideas to learn from include:

-   AI coworkers with their own browser, files, tools, and working
    environments
-   A central gateway through which actions are coordinated
-   Isolated environments for individual workers
-   The ability to watch a worker and take control
-   Persistent responsibilities and routines
-   Generative user interfaces
-   AG-UI interoperability as a possible integration direction

OpenBot should be treated as **product and architecture inspiration**,
not as a replacement for IRIS or an automatic dependency.

IRIS should retain its own supervisor, capability registry, permission
model, memory, device coordination, and user experience. Any OpenBot
code or dependency would require a separate technical and licence review
before adoption.

### 4.1 Proposed division of responsibility

-   **IRIS Supervisor:** Understands the user's request, maintains
    overall reasoning authority, and decides what should happen.
-   **Coworker orchestration:** Assigns work to specialised coworkers
    and coordinates their progress.
-   **Governance gateway:** Enforces permissions, approvals,
    auditability, and action boundaries.
-   **Coworker runtime:** Provides the worker's workspace, tools, and
    execution environment.
-   **IRIS UI:** Shows the user the workers, their activity, outputs,
    and requests for attention.

This avoids creating a second competing system that independently tries
to become IRIS's brain.

------------------------------------------------------------------------

# Part II --- Computer-use infrastructure and CUA

## 5. CUA as computer-use infrastructure

The repository `https://github.com/trycua/cua` was explored as a
possible foundation for isolated computer-use environments.

The intended role of CUA in IRIS is **computer-use and sandbox
infrastructure**, not the AI reasoning layer and not the coworker
orchestration system.

Potentially useful areas include:

-   SDKs for creating and managing computer-use environments
-   CLI and daemon-based environment management
-   Computer-use drivers for interacting with a graphical environment
-   Local or isolated execution environments where supported
-   A foundation for coworkers that need to use a computer rather than
    only call APIs

The exact fit must be validated against IRIS's target platforms,
especially the Windows host workflow and any Linux/WSL2/Docker
requirements.

### 5.1 Where CUA fits

A possible flow:

1.  The user delegates a task to a coworker.
2.  IRIS classifies the task and its risk.
3.  The execution manager selects an appropriate environment.
4.  For ordinary coding or file work, the coworker may use a selected
    local workspace.
5.  For GUI-heavy, risky, or isolated work, IRIS may provision a
    suitable CUA-backed environment if the platform supports it.
6.  The coworker performs permitted actions.
7.  IRIS captures status, outputs, and relevant evidence.
8.  The user can inspect the work, intervene, or accept the result.

### 5.2 Local workspace versus isolated computer

Not every task needs a virtual computer.

Use a selected local project directory when the task is ordinary
development or file work and the user has granted access.

Consider an isolated environment when:

-   The task involves untrusted files or websites
-   A GUI workflow needs a disposable environment
-   Parallel work should not interfere with the user's working tree
-   The user explicitly asks for isolation
-   A task has a higher risk profile

A Git worktree or cloned task workspace may be sufficient for many
software tasks. A full computer-use sandbox should be used only when it
provides a real benefit.

### 5.3 CUA licensing and adoption gate

The repository contains components with different licensing positions.
The exploration identified MIT-licensed components as candidates, while
some components such as CUA Spaces were identified as using FSL-1.1-MIT,
which is source-available but not an OSI-approved open-source licence.

Therefore:

-   Do not treat the entire CUA repository as uniformly open-source.
-   Do not adopt a component merely because it is in an open repository.
-   Verify the exact component, version, licence, and transitive
    dependencies.
-   Exclude source-available but non-OSI components under the current
    IRIS policy unless the policy is explicitly reconsidered.
-   Validate Windows compatibility, distribution terms, and runtime
    requirements before integration.

**Decision:** CUA is a candidate infrastructure layer. It is not yet a
confirmed dependency or an implemented IRIS subsystem.

------------------------------------------------------------------------

# Part III --- Coding-agent control

## 6. IRIS as a full coding-agent controller

The current coding agent in the user's workflow is **Antigravity CLI**.
The desired integration is much more than asking IRIS to generate a
prompt and then leaving the user to manage the rest.

The user selected the **full coding-agent controller** direction.

The intended experience:

1.  The user gives IRIS an instruction, for example: "IRIS, add this
    feature to Forge."
2.  IRIS resolves which project the user means.
3.  If the project is ambiguous, IRIS asks the user to select it.
4.  IRIS identifies the coding agents available for the task.
5.  If multiple agents are available, IRIS asks which one to use. The
    user may select Antigravity CLI.
6.  IRIS gathers relevant project information and relevant prior
    conversation context.
7.  IRIS prepares a detailed implementation brief or prompt.
8.  IRIS presents the brief and asks the user to approve sending it.
9.  IRIS launches or connects to the selected coding agent in the
    correct project workspace.
10. IRIS manages the execution session, monitors output and progress,
    and handles supported follow-up interactions.
11. If the agent asks for an approval or additional instruction, IRIS
    surfaces the request to the user.
12. IRIS reports the outcome, relevant changes, errors, and verification
    evidence.

The user can still open Antigravity manually at any time. IRIS should be
the orchestration layer, not a barrier to direct use of the coding
agent.

## 7. Project registry and project resolution

IRIS needs a project registry that maps user-friendly project names to
actual project directories.

A project entry may contain:

-   Project name and optional aliases
-   Local directory
-   Description and tags
-   Preferred coding agent, if configured
-   Relevant Git repository information, if available
-   Workspace trust and access settings
-   Recent tasks and agent sessions

The registry should not be a hardcoded list of a few projects. The user
should be able to browse to and select any directory they choose,
subject to platform permissions.

When a user names a project, the Project Resolver should:

-   Match the name or alias against registered projects
-   Use conversation context to disambiguate
-   Ask the user if more than one project is plausible
-   Offer directory selection if the project is not registered
-   Confirm the resolved project before a consequential action when
    ambiguity remains

## 8. Coding-agent adapter architecture

IRIS should not be hardwired to Antigravity CLI.

Create a generic Coding Agent Adapter Registry. Each supported agent has
an adapter that translates IRIS's common execution lifecycle into that
agent's supported interface.

A conceptual adapter contract:

-   `detect()` --- determine whether the agent is installed and
    available
-   `launch()` --- start or attach to an agent session
-   `send_prompt()` --- submit the approved task brief
-   `resume_session()` --- reconnect to a supported existing session
-   `get_status()` --- retrieve current state where supported
-   `get_output()` --- collect output, logs, or events where supported
-   `stop()` --- request a stop or terminate a session according to the
    agent's capabilities

These are conceptual responsibilities, not claims that every agent
exposes these exact operations.

Antigravity CLI is the first intended adapter. Other coding agents can
be added later without changing the overall project workflow.

### 8.1 Execution manager

The Execution Manager should own the lifecycle of a coding-agent task:

-   Resolve the project workspace
-   Verify the selected agent is available
-   Launch the agent with the selected project as its working directory
-   Send only the user-approved task brief
-   Capture output and execution state
-   Track session identifiers where the agent exposes them
-   Support pause, resume, stop, and follow-up where technically
    supported
-   Surface permission or approval requests
-   Preserve a task summary and completion report

The selected project directory should be the agent's working directory.
This is preferable to making IRIS imitate a user by opening Explorer and
navigating through the GUI.

A process launch such as `subprocess.Popen(..., cwd=project_directory)`
is an illustrative implementation pattern only. The exact Antigravity
executable, arguments, session flags, streaming protocol, and approval
behaviour must be verified against the installed CLI version and its
documentation before implementation.

### 8.2 Agent session manager

Each session should record, as applicable:

-   Agent and adapter version
-   Project and working directory
-   Task description and approved prompt
-   Session identifier supplied by the agent
-   Start time and current status
-   Output and relevant events
-   User approvals and instructions
-   Files or outputs reported by the agent
-   Verification results
-   Final summary and unresolved issues

IRIS should distinguish between what the coding agent reports and what
IRIS has independently verified. It must not claim tests passed unless
there is evidence that they ran and passed.

### 8.3 Relevant context retrieval

IRIS should be able to use relevant previous IRIS conversations and
agent history.

However, it should not dump every historical conversation into a coding
prompt. Context retrieval should be selective:

-   Retrieve conversations relevant to the named project or feature.
-   Retrieve relevant architecture decisions and constraints.
-   Retrieve the latest task or agent session when continuing work.
-   Include user-approved project instructions and documentation.
-   Avoid unrelated personal or project context.
-   Show or summarise important context included in the brief when
    useful.

This allows IRIS to carry continuity across conversations without
creating bloated, noisy prompts.

## 9. Workspace access and safety

"Any project directory" means the user can select any directory they
want IRIS to work with. It does not mean every agent receives blanket
access to every drive.

Recommended model:

-   Explicit user selection of a directory
-   Per-project access grants
-   Clear indication of the active working directory
-   Separate permissions for reading, writing, executing commands, and
    accessing external resources where practical
-   More restrictive isolation for untrusted or high-risk work
-   Git worktrees or task-specific copies for parallel or risky changes
-   Clear user approval before IRIS sends the implementation brief to
    the coding agent

The user may open the agent manually, while IRIS continues to manage the
task when the supported process/session interface allows it.

------------------------------------------------------------------------

# Part IV --- Shared IRIS architecture

## 10. Keep the existing IRIS core; add coordinated layers

The redesign should extend the existing IRIS architecture rather than
duplicate or replace core services.

Existing concepts such as the IRIS Supervisor, capability registry,
memory, device execution, voice, vision, and Mesh remain relevant. Their
actual implementation status must be checked against the current
repository; historical architecture notes may be stale.

A proposed high-level structure:

``` text
                         USER
                          |
                  IRIS EXPERIENCE
             Desktop Renderer / Android Renderer
                          |
                  SHARED UI ORCHESTRATOR
              /           |             \
       Context Engine  Layout Engine  Widget Engine
              \           |             /
                   Preference Engine
                          |
                    IRIS SUPERVISOR
                          |
             Intent, planning and delegation
                          |
       +------------------+-------------------+
       |                  |                   |
  Coworker System   Coding Agent System   Capability Registry
       |                  |                   |
  Coworker Runtime   Agent Adapters       Tools / Services
       |                  |                   |
  Workspace / Tools  Execution Manager    Device / Mesh
       |                  |                   |
       +------------------+-------------------+
                          |
               Governance / Permission Layer
                          |
             Audit, approval, verification,
                session and task state
```

This is a conceptual architecture, not a diagram of currently
implemented code.

## 11. Core responsibilities

### IRIS Supervisor

-   Understand user intent and conversation context
-   Decide whether to answer, act, delegate, or ask a question
-   Maintain overall reasoning and coordination authority
-   Route work to the right capability, coworker, or coding agent
-   Integrate results and communicate the outcome

### Capability Registry

-   Describe available tools and capabilities
-   Advertise platform and permission requirements
-   Allow the supervisor and coworkers to discover supported actions
-   Avoid duplicating capabilities already provided by existing services

### Coworker Orchestrator

-   Select and assign coworkers
-   Manage coworker tasks and handoffs
-   Track progress and dependencies
-   Coordinate results
-   Apply coworker-specific permissions and workspace policies

### Coding Agent System

-   Resolve projects
-   Discover coding agents
-   Select adapters
-   Manage coding-agent sessions
-   Capture outputs and verification evidence

### Governance and execution layer

-   Enforce user permissions
-   Manage approvals
-   Record consequential actions
-   Apply workspace isolation
-   Support pause, stop, recovery, and error reporting
-   Separate requested actions from completed and verified actions

------------------------------------------------------------------------

# Part V --- Product-wide UI redesign

## 12. Visual identity and theme

The visual direction has changed from the earlier dark, matte-black and
neon-white concept.

### Current theme direction

-   Matte white background
-   Coloured neon accents, used with restraint
-   Mostly neutral, readable text
-   Comfortable contrast and legibility
-   Subtle shadows and layered surfaces
-   Balanced information density
-   Minimal functional animations outside the existing sphere

The intended look is clean and modern, with colour used to communicate
state and emphasis rather than to decorate every surface.

### 12.1 Preserve IRIS identity

The existing IRIS logo and sphere are core identity assets.

-   Do not replace the logo.
-   Do not reinvent or redesign the sphere.
-   Preserve the sphere's existing animation identity and demonstrated
    behaviour.
-   The sphere may be repositioned or integrated differently into the
    new layout.
-   The surrounding interface can change to support the new matte-white
    theme.

The previously supplied sphere video is an animation reference, not a
requirement to retain its old black background.

### 12.2 Effects and motion

-   Keep motion purposeful and restrained.
-   Use animation to communicate state, progress, transitions, or
    hierarchy.
-   Avoid a flashy holographic aesthetic.
-   Use 3D only where it improves clarity, depth, or spatial
    understanding.
-   Preserve the existing sphere effects rather than inventing a
    replacement.

## 13. Desktop application layout

Desktop should use a hybrid workspace-and-assistant model. The workspace
and visual management experience are as important as conversation.

### 13.1 Global structure

-   Collapsible left sidebar, expanded by default
-   Central workspace
-   Global top bar
-   Page-specific content and contextual controls

### 13.2 Sidebar navigation

The proposed primary navigation:

1.  Home
2.  Conversations
3.  Coworkers
4.  Projects
5.  Schedule
6.  Tasks
7.  Devices & Mesh
8.  Memory
9.  Settings

The navigation should make the operating-system nature of IRIS visible
without overcrowding the interface.

### 13.3 Global top bar

The top bar contains:

-   Global search
-   Notifications
-   One compact system-health icon
-   Settings access

The system-health icon opens a detailed system overview when selected.
The overview should cover:

-   Mesh connectivity
-   Connected devices
-   Active model and provider
-   Backend availability
-   Core service status
-   Connectivity problems and errors

The Home dashboard itself should not contain a separate system-health
dashboard or duplicate health cards. System health belongs in the top
bar and its detail view.

Notifications are also global and should not be duplicated as a Home
dashboard section.

## 14. Home dashboard

Home combines personal productivity with IRIS's current work context.

The four agreed dashboard areas are:

1.  **Priorities**
2.  **Schedule**
3.  **Routines**
4.  **Agents / Coworkers**

There should not be a separate notifications section on Home.

### 14.1 Priorities

-   The user sets and owns their priorities.
-   IRIS may recommend additions.
-   IRIS may warn when an important responsibility appears to have been
    overlooked.
-   The user remains in control of the priority list.

### 14.2 Schedule

Show relevant upcoming commitments and time-based context in a useful
format. The presentation can adapt to the day---for example, a timeline
when the day is busy and a compact summary when it is quiet.

### 14.3 Routines

Show recurring personal or work routines in a compact, actionable way.
The interface should help the user understand what is planned and what
remains, without turning the dashboard into a wall of reminders.

### 14.4 Agent and coworker activity

This section shows ongoing work, not notifications.

-   **Activity** means a coworker or agent is currently working.
-   **Notification** means a result, request, completion, or issue needs
    the user's attention.

If there is no active coworker or agent work, the section should
collapse or remain compact. Empty sections should never become large
empty cards.

### 14.5 Initial and adaptive layout

-   IRIS chooses the initial dashboard arrangement based on screen size.
-   The user can rearrange and resize sections.
-   The user can lock individual sections' position and size.
-   IRIS can restore a previous or preferred layout.
-   The user can create custom widgets or sections.

### 14.6 Layout adaptation and approval

IRIS should be capable of suggesting a better arrangement when the
user's context changes.

For dashboard layout changes:

1.  IRIS identifies a meaningful reason to change the layout.
2.  It prepares a before-and-after preview.
3.  It explains the significant change.
4.  The user approves or rejects the proposed layout.
5.  The user can later override, lock, or restore the arrangement.

This approval requirement remains in place even though IRIS has broad
autonomy over UI orchestration. Full UI autonomy does not mean silently
overriding a layout decision that the user is explicitly asked to
approve.

## 15. Situation-led widgets

The dashboard should not be limited to a permanently fixed collection of
widgets.

IRIS should select, configure, and create widgets based on the user's
current situation.

Examples:

-   Priority timeline when deadlines are approaching
-   Project progress widget while a project is active
-   Agent activity monitor while coworkers are working
-   Schedule-focused view on a busy day
-   Research progress widget during a research task
-   A new project widget when a project becomes active
-   A quieter, minimal dashboard when there is little to surface

Widgets may be temporary or persistent depending on their usefulness.

### 15.1 Natural-language widget creation

The user should be able to request a widget in natural language. IRIS
translates the request into a supported widget definition using the
approved component system.

### 15.2 Widget autonomy and boundaries

IRIS may autonomously:

-   Select and configure suitable widgets
-   Create, modify, or remove UI widgets
-   Change presentation patterns
-   Organise workspace information
-   Adapt widget density and emphasis
-   Learn from user interaction

These actions concern the interface and its presentation. They do not
grant permission to delete underlying user data or perform unrelated
destructive operations.

### 15.3 Controlled widget architecture

Do not let the model generate and execute arbitrary UI code as the
normal widget mechanism.

Instead:

-   Maintain an approved UI Component Registry.
-   Use declarative widget definitions.
-   Validate widget configuration and data bindings.
-   Enforce platform compatibility and permissions.
-   Apply layout constraints and error handling.
-   Provide safe fallback components when a widget cannot render.

This preserves adaptability while protecting security, consistency,
performance, and maintainability.

## 16. Preference learning

IRIS should learn the user's interface preferences over time.

Areas to learn include:

-   Preferred layout and arrangement
-   Widget patterns: cards, lists, timelines, tables, or compact
    summaries
-   Information density
-   Interaction patterns
-   Visual emphasis and colour preferences
-   Workflow and context-specific presentation choices

Signals may include widgets the user keeps, modifies, ignores, locks, or
removes.

Preference learning should improve the experience without making the
interface unpredictable. The user must retain the ability to override or
reset preferences.

------------------------------------------------------------------------

# Part VI --- Sphere, assistant, and interaction model

## 17. Sphere and composer placement

The assistant sphere and chat composer appear **only on Home**.

Other pages should use the full workspace rather than permanently
reserving a large assistant panel.

On Home:

-   The sphere is fixed at the bottom centre.
-   It is visually substantial and prominent.
-   It continuously rotates while idle, preserving its existing
    behaviour.
-   The composer sits directly below the sphere.
-   The composer is always visible on Home.
-   The Home workspace reserves sufficient space for the dock so content
    is not obscured.

The chosen approach combines a fixed dock with a floating-overlay visual
treatment: the sphere and composer remain anchored while the Home
content scrolls, but the workspace accounts for their footprint.

Clicking the sphere starts listening in place. It must not open a new
window, popup, or side panel.

## 18. Composer capabilities

The Home composer should support:

-   Text input
-   Voice interaction
-   File attachments
-   Images
-   Screen sharing

The exact platform permissions and implementation differ between desktop
and Android.

## 19. Sphere interaction states

The sphere should communicate the assistant's current state. The agreed
state model includes:

-   Idle
-   Listening
-   Paused
-   Thinking
-   Speaking
-   Executing
-   Approval required
-   Completed

Errors and interruptions should also be represented clearly.

Clicking the sphere while it is listening temporarily pauses listening;
it does not terminate the interaction.

The existing sphere animation language should be preserved and mapped to
these states wherever the current effects support it. Any additional
state treatment should extend, not replace, the existing identity.

## 20. Interactions while away from Home

Ongoing voice interactions should continue when the user navigates away
from Home, subject to platform permissions and the relevant
background-execution capabilities.

Outside Home:

-   Do not display the full sphere controller.
-   Show a compact global activity indicator.
-   The indicator communicates the current state, such as Listening,
    Thinking, or Speaking.
-   Selecting or returning to Home restores the full sphere interface
    with the current interaction state.

Background listening must always be governed by explicit microphone
permission and user controls.

------------------------------------------------------------------------

# Part VII --- Android experience

## 21. Android is a separate experience, not compressed desktop

Android should have its own responsive interaction design. It should not
simply render the desktop layout at a smaller width.

The Android experience should include:

-   Mobile-first navigation
-   Touch-friendly controls
-   Responsive widgets
-   Mobile-appropriate information density
-   Clear navigation between Home, conversations, coworkers, projects,
    tasks, devices, memory, and settings
-   Appropriate handling of permissions and background activity

### 21.1 Android Home

The Android Home screen should preserve the same product concepts:

-   Priorities
-   Schedule
-   Routines
-   Agent and coworker activity
-   Contextual widgets
-   Assistant sphere and composer dock

The sphere and composer remain bottom-centred, adapted to the available
mobile dimensions.

### 21.2 Shared preferences, separate renderers

Desktop and Android should share applicable preferences and definitions,
including:

-   Widget definitions and configuration
-   Dashboard personalisation
-   Theme and visual preferences
-   Relevant layout preferences
-   User-level interaction preferences

However, desktop and Android should have separate renderers so each
platform can arrange and present the same concepts appropriately.

------------------------------------------------------------------------

# Part VIII --- Shared UI architecture

## 22. One shared UI Orchestrator, two platform renderers

The agreed architecture is a **central shared UI Orchestrator with
separate Desktop and Android renderers**.

The shared layer decides what the interface should communicate and which
supported components should be used. Each platform renderer decides how
to present that interface in a platform-appropriate way.

### 22.1 Shared UI Orchestrator

The shared orchestrator coordinates:

-   Current context
-   User preferences
-   Widget selection and configuration
-   Layout decisions
-   Dashboard adaptation proposals
-   UI state
-   Widget lifecycle
-   Platform-neutral presentation definitions

### 22.2 Supporting services

**Context Engine** - Collects the relevant current state from IRIS
services. - Determines which information is useful for the current page
and situation.

**Preference Engine** - Stores and applies user interface preferences. -
Learns from user interactions within defined boundaries.

**Layout Engine** - Selects placement, sizing, ordering, and responsive
layout rules. - Respects locked sections and platform constraints. -
Supports previews and restoration.

**Widget Engine** - Creates and configures widgets from approved
component definitions. - Manages temporary and persistent widget
lifecycles.

**UI Component Registry** - Contains approved reusable components. -
Defines supported properties, data requirements, and platform
compatibility.

**Desktop Renderer** - Presents the shared UI definition using
desktop-native layout and interaction patterns.

**Android Renderer** - Presents the shared UI definition using
mobile-native layout and touch patterns.

### 22.3 Reliability and user control

The UI architecture should include:

-   Preference storage and versioning
-   Layout history and rollback
-   Approval and permission checks
-   Widget-definition validation
-   UI state synchronisation
-   Platform-specific fallback layouts
-   Error handling for unavailable data or unsupported widgets
-   Clear handling of locked sections and user overrides

The UI Orchestrator should integrate with existing IRIS services rather
than creating duplicate sources of truth.

------------------------------------------------------------------------

# Part IX --- Open-source and deployment policy

## 23. Non-negotiable dependency policy

The user explicitly requires all third-party components selected for
IRIS to be completely free and open-source.

The preferred licence direction is OSI-approved licences such as:

-   MIT
-   Apache-2.0
-   Other OSI-approved licences after compatibility review

The project must distinguish:

-   **Open-source:** Licence meets the project's open-source
    requirements.
-   **Source-available:** Source can be inspected, but the licence may
    restrict use and may not be OSI-approved.
-   **Free of charge:** No payment is required, but this does not
    establish that the software is open-source.
-   **Paid hosted service:** A service may charge for usage even when
    some client or server code is open-source.

A free tier is not sufficient evidence that a dependency meets the IRIS
policy.

### 23.1 Adoption checklist

Before adopting a third-party component, verify:

1.  Exact repository and component
2.  Exact version or commit
3.  Licence of the component
4.  Licences of transitive dependencies
5.  Whether the component requires a proprietary hosted service
6.  Whether it requires a paid subscription or licence
7.  Whether it can be self-hosted or run locally
8.  Windows and Android compatibility, where relevant
9.  Data handling and security implications
10. Whether an open-source alternative exists

### 23.2 Model providers and inference costs

Software licensing and model inference costs are separate concerns.

IRIS should keep its model-provider interface interchangeable. A model
API may have usage charges even when IRIS's own software and integration
code are open-source.

No core IRIS workflow should be permanently locked to one proprietary
model provider. Local models and alternative providers should remain
possible where practical.

### 23.3 No mandatory proprietary cloud

Core IRIS functionality should not require:

-   A mandatory proprietary cloud platform
-   A mandatory paid coworker service
-   A mandatory closed-source computer-use service
-   A mandatory subscription to operate the core product

Optional hosted services may be considered only if a practical
self-hosted or open-source path remains available for the relevant core
capability.

------------------------------------------------------------------------

# Part X --- Governance, safety, and observability

## 24. Permission model

Permissions should be explicit, understandable, and scoped.

Examples of distinct permission areas:

-   Project directory access
-   File read and write
-   Command execution
-   Browser access
-   Computer-use access
-   Microphone and screen capture
-   Device and Mesh actions
-   Coworker tool access
-   External service access

A user selecting one project directory should not silently grant access
to unrelated directories.

## 25. Approval model

The system should distinguish between:

-   Actions that are permitted to run automatically
-   Actions that require user approval
-   Actions that are not allowed

The user explicitly approved the following interaction principle for
coding tasks: IRIS prepares a detailed implementation brief and asks
before sending it to the selected coding agent.

The dashboard layout adaptation flow also requires a before-and-after
preview and user approval.

Other approval requirements should be determined by action risk and the
user's configured permissions. Do not infer blanket approval from the
user's preference for autonomous UI orchestration.

## 26. Activity, notifications, and audit

Keep three concepts distinct:

-   **Activity:** Work currently in progress.
-   **Notification:** Something has happened or needs the user's
    attention.
-   **Audit/history:** A record of what was requested, approved,
    executed, and reported.

For consequential actions, retain enough information to understand:

-   Who or what initiated the action
-   Which coworker, agent, or capability performed it
-   Which workspace or device was involved
-   What permission or approval applied
-   What result was reported
-   What was independently verified

## 27. Verification and truthful reporting

IRIS must distinguish:

-   Prompt prepared
-   Prompt approved
-   Agent launched
-   Work in progress
-   Agent reported completion
-   Tests or checks actually executed
-   Results independently verified
-   Task completed with unresolved issues

Do not represent an agent's claim as independent verification. If a test
was not run, say so. If an integration cannot expose reliable process
status, communicate that limitation rather than inventing a status.

------------------------------------------------------------------------

# Part XI --- Suggested delivery sequence

## 28. Build in coherent phases

The following is a suggested sequence for planning. It is not a
declaration that these phases have been implemented or that every
dependency is already validated.

### Phase 1 --- Architecture and foundations

-   Audit the current IRIS repository and existing services.
-   Confirm which historical architecture elements still exist.
-   Define shared contracts for tasks, sessions, permissions, coworkers,
    and UI definitions.
-   Establish dependency and licence review procedures.
-   Define project registry and workspace permission boundaries.

### Phase 2 --- Coding-agent controller

-   Implement project registration and directory selection.
-   Define the generic coding-agent adapter contract.
-   Verify Antigravity CLI's actual supported launch, session, input,
    output, and approval mechanisms.
-   Build session lifecycle and progress reporting.
-   Add relevant IRIS conversation and project context retrieval.
-   Test pause, resume, stop, and error behaviour where supported.

### Phase 3 --- Coworker foundation

-   Define coworker identity, role, responsibility, and permission
    models.
-   Build coworker task assignment and handoff.
-   Add isolated or dedicated workspaces.
-   Add watch, inspect, and take-control experiences.
-   Add persistent responsibility support where appropriate.

### Phase 4 --- Computer-use infrastructure

-   Validate CUA components and licences individually.
-   Confirm Windows host compatibility and runtime prerequisites.
-   Prototype isolated computer provisioning and driver interaction.
-   Integrate CUA only for tasks that benefit from computer-use
    isolation.
-   Keep non-CUA local workspace execution available.

### Phase 5 --- Shared UI Orchestrator

-   Define the approved component registry and declarative widget
    schema.
-   Implement context, preference, layout, and widget services.
-   Build layout preview, approval, lock, and rollback.
-   Add temporary and persistent situation-led widgets.
-   Add safe fallback rendering and validation.

### Phase 6 --- Desktop and Android redesign

-   Implement the matte-white visual system with restrained neon
    accents.
-   Preserve the existing logo and sphere.
-   Build the desktop sidebar, top bar, Home dashboard, and full
    workspace pages.
-   Build a separate Android renderer and mobile navigation.
-   Integrate the Home sphere and composer dock on both platforms.
-   Synchronise applicable preferences and widget definitions.

### Phase 7 --- Integration and hardening

-   Connect coworkers, coding agents, capabilities, Mesh, devices, and
    UI state.
-   Test permission boundaries and approval flows.
-   Test recovery from interrupted sessions and unavailable services.
-   Validate performance and accessibility.
-   Audit all shipped dependencies and licences.
-   Verify all claims of completion with actual execution evidence.

------------------------------------------------------------------------

# Part XII --- Decisions register

## 29. Confirmed product decisions

  -----------------------------------------------------------------------
  Area                                Decision
  ----------------------------------- -----------------------------------
  Product direction                   IRIS evolves into a personal AI
                                      operating system and coworker
                                      ecosystem.

  Coworkers                           Specialised workers with roles,
                                      responsibilities, tools,
                                      workspaces, and persistent context.

  OpenBot                             Inspiration for coworker workflows;
                                      not a wholesale replacement for
                                      IRIS.

  CUA                                 Candidate computer-use and sandbox
                                      infrastructure, subject to platform
                                      and licence validation.

  Coding agents                       Full coding-agent controller, not
                                      merely a prompt generator.

  First coding agent                  Antigravity CLI.

  Agent architecture                  Generic adapter registry so more
                                      coding agents can be supported
                                      later.

  Project access                      User can select any project
                                      directory; access remains scoped
                                      and permissioned.

  Coding workflow                     Resolve project, select agent,
                                      prepare brief, obtain approval,
                                      manage execution and report
                                      results.

  Context                             Retrieve relevant prior IRIS
                                      conversations and agent history,
                                      not all history indiscriminately.

  Visual theme                        Matte white background with
                                      restrained coloured neon accents
                                      and neutral readable text.

  Existing identity                   Preserve the existing IRIS logo and
                                      sphere.

  Desktop layout                      Collapsible left sidebar, central
                                      workspace, global top bar.

  Home sections                       Priorities, Schedule, Routines,
                                      Agents/Coworkers.

  Notifications                       Global top bar, not a Home
                                      dashboard section.

  System health                       Compact top-bar icon opening a
                                      detailed health overview.

  Dashboard autonomy                  IRIS can orchestrate and adapt the
                                      UI; layout proposals show
                                      before/after and await user
                                      approval.

  Widgets                             Situation-led, temporary or
                                      persistent, and creatable through
                                      natural language.

  Widget safety                       Use an approved component registry
                                      and declarative definitions, not
                                      arbitrary generated executable UI
                                      code.

  Preference learning                 Learn layout, widget patterns,
                                      density, interaction, and workflow
                                      preferences.

  Assistant placement                 Sphere and composer appear only on
                                      Home.

  Sphere interaction                  Fixed bottom-centre dock on Home;
                                      click to listen; click while
                                      listening to pause.

  Navigation away                     Ongoing voice interaction continues
                                      where supported; compact global
                                      state indicator outside Home.

  Android                             Separate mobile-first experience,
                                      not a compressed desktop layout.

  UI architecture                     One shared UI Orchestrator with
                                      separate Desktop and Android
                                      renderers.

  Third-party dependencies            Must be free and open-source under
                                      an acceptable licence; verify exact
                                      licences and dependencies.

  Cloud dependency                    No mandatory proprietary cloud,
                                      paid SaaS, or subscription for core
                                      functionality.

  Model providers                     Keep provider interchangeable;
                                      distinguish inference costs from
                                      software licensing.
  -----------------------------------------------------------------------

## 30. Open validation items (not yet confirmed)

The following require repository inspection, technical prototypes, or
current documentation before implementation decisions are finalised:

-   Current state of the existing IRIS Supervisor, capability registry,
    memory, voice, vision, Mesh, and Android services.
-   Exact Antigravity CLI invocation and supported session-continuation
    behaviour.
-   How Antigravity CLI accepts input, streams output, and exposes
    approval requests in the installed version.
-   Whether the required process lifecycle can be reliably controlled by
    IRIS.
-   Exact CUA component licences and transitive dependency licences for
    the versions considered.
-   CUA's Windows host compatibility and runtime requirements in the
    intended deployment.
-   Which CUA components, if any, are necessary for the first release.
-   Coworker isolation strategy and workspace lifecycle.
-   Shared widget schema and the exact set of approved UI components.
-   Desktop and Android synchronisation strategy and conflict handling.
-   Which UI-only changes may be autonomous by default and which
    user-configured safeguards are needed.
-   Storage, audit retention, and backup policies for coworker and
    coding-agent sessions.

------------------------------------------------------------------------

# 31. Final product statement

The reimagined IRIS is a unified, adaptive AI operating system.

It has a persistent assistant at its centre, a coordinated ecosystem of
specialised coworkers, a full coding-agent control system, optional
isolated computer-use environments, and a workspace that reshapes itself
around the user's current work.

Its intelligence is coordinated by IRIS rather than scattered across
disconnected agents. Its interface is adaptive but governed. Its desktop
and Android experiences share one product vision without being forced
into identical layouts. Its existing sphere and logo remain recognisably
IRIS. Its infrastructure is open-source-first, modular, and designed to
avoid mandatory proprietary services.

**The goal is not simply to make IRIS answer better. The goal is to make
IRIS a system that can understand, organise, delegate, execute, observe,
and help complete work---while remaining transparent and under the
user's control.**
