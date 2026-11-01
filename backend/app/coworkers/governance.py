"""Backend permission gateway shared by coworker tool invocation endpoints."""
from dataclasses import dataclass
from typing import Any

from app.agent.registry import create_default_registry
from app.models.coding_project import CodingProject
from app.models.coworker import Coworker, CoworkerTask
from app.agent.registry import ToolRegistry
from app.agent.schemas import ToolResult
from app.models.coworker import CoworkerEvent


@dataclass
class CapabilityDecision:
    allowed: bool
    requires_approval: bool
    reason: str
    tool: Any = None


def evaluate_capability(db, user, coworker: Coworker, task: CoworkerTask, name: str, args: dict[str, Any]) -> CapabilityDecision:
    if "approval_token" in args:
        return CapabilityDecision(False, False, "Approval tokens are issued only by IRIS after the user approves the action.")
    if name not in (coworker.allowed_capabilities or []):
        return CapabilityDecision(False, False, "Capability was not granted to this coworker.")
    if task.required_capabilities and name not in task.required_capabilities:
        return CapabilityDecision(False, False, "Capability was not granted to this task.")
    registry = create_default_registry()
    tool = registry.get(name)
    if tool is None:
        return CapabilityDecision(False, False, "Capability is not registered in this IRIS environment.")
    # The existing IRIS registry includes tools that access host processes,
    # email, cloud drives, devices and networks without coworker-specific
    # confinement. These remain unavailable until a scoped adapter exists.
    protected_prefixes = ("agy_", "desktop_", "run_", "execute_", "send_email", "draft_email",
                          "drive_", "mesh_", "device_", "coding_", "delete_", "finance_")
    protected_categories = {"email", "drive", "desktop", "mesh", "device", "coding", "finance"}
    if name.startswith(protected_prefixes) or str(getattr(tool, "category", "")).lower() in protected_categories:
        return CapabilityDecision(False, False, "Capability lacks a coworker-scoped isolation adapter and is denied.")
    if task.project_id:
        project = db.query(CodingProject).filter_by(id=task.project_id, user_id=user.id, active=True).first()
        if project is None or not project.read_access:
            return CapabilityDecision(False, False, "Task workspace is not owned by this user or lacks read permission.")
        if tool.mutates_state and not project.write_access:
            return CapabilityDecision(False, False, "Task workspace does not grant write access.")
    if tool.mutates_state:
        return CapabilityDecision(True, True, "State-changing capability requires approval for this exact action.", tool)
    if name in {"run_command", "desktop_execute", "agy_command", "mesh_command"}:
        return CapabilityDecision(False, False, "Host command and desktop capabilities are not available to coworker tasks.")
    return CapabilityDecision(True, False, "Read-only capability is within the coworker's granted scope.", tool)


class GovernedCoworkerRegistry(ToolRegistry):
    """Filtered adapter applying the permission gateway on every model tool call."""

    def __init__(self, db, user, coworker: Coworker, task: CoworkerTask):
        super().__init__()
        self.db, self.user, self.coworker, self.task = db, user, coworker, task

    async def execute(self, name, db, user, parameters=None):
        args = parameters or {}
        decision = evaluate_capability(self.db, self.user, self.coworker, self.task, name, args)
        if not decision.allowed or decision.requires_approval:
            reason = decision.reason if not decision.allowed else "This action must be requested through the approval gateway."
            self.db.add(CoworkerEvent(user_id=self.user.id, coworker_id=self.coworker.id,
                task_id=self.task.id, event_type="capability_denied", payload={"capability":name,"reason":reason}))
            return ToolResult(tool_name=name, success=False, error=reason, summary=reason, verified=False)
        result = await decision.tool.execute(self.db, self.user, **args)
        self.db.add(CoworkerEvent(user_id=self.user.id, coworker_id=self.coworker.id,
            task_id=self.task.id, event_type="tool_invoked", payload={"capability":name,
            "success":result.success,"verified":result.verified}))
        return result
