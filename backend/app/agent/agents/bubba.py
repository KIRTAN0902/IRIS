"""BUBBA Agent Migration Shim.

MIGRATION NOTICE:
BUBBA has been migrated into IRIS Core and the specialized Workspace coworker.
- Workspace operations (Gmail, Google Drive, Slack) are now owned by `WorkspaceAgent`.
- Operational management, task coordination, and planning are owned directly by IRIS Core.
This module is maintained as a backward-compatible shim.
"""

from __future__ import annotations

from app.agent.agents.workspace import WorkspaceAgent, get_workspace_agent

# Backward compatibility alias
BubbaAgent = WorkspaceAgent
get_bubba_agent = get_workspace_agent

