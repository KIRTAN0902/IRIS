from enum import StrEnum


class CoworkerStatus(StrEnum):
    CREATED = "created"
    IDLE = "idle"
    ASSIGNED = "assigned"
    PLANNING = "planning"
    WORKING = "working"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_INPUT = "waiting_input"
    PAUSED = "paused"
    COMPLETED = "completed"
    COMPLETED_WITH_ISSUES = "completed_with_issues"
    FAILED = "failed"
    STOPPED = "stopped"
    INTERRUPTED = "interrupted"


TASK_TRANSITIONS = {
    "queued": {"running", "waiting_approval", "cancelled", "interrupted"},
    "running": {"waiting_approval", "waiting_input", "paused", "completed", "completed_with_issues", "failed", "cancelled", "interrupted"},
    "waiting_approval": {"running", "completed", "completed_with_issues", "cancelled", "failed", "interrupted"},
    "waiting_input": {"running", "completed", "completed_with_issues", "cancelled", "failed", "interrupted"},
    "paused": {"running", "queued", "cancelled", "interrupted"},
    "interrupted": {"running", "cancelled"},
    "completed": set(), "completed_with_issues": {"completed", "failed", "cancelled"}, "failed": set(), "cancelled": set(),
}


def transition(current: str, target: str) -> str:
    if target not in TASK_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid coworker task transition: {current} -> {target}")
    return target


COWORKER_TRANSITIONS = {
    "created": {"idle", "stopped"}, "idle": {"assigned", "stopped"},
    "assigned": {"planning", "working", "idle", "stopped"},
    "planning": {"working", "waiting_input", "failed", "stopped"},
    "working": {"waiting_approval", "waiting_input", "paused", "completed", "completed_with_issues", "failed", "idle", "stopped"},
    "waiting_approval": {"working", "paused", "stopped", "failed"},
    "waiting_input": {"working", "paused", "stopped", "failed", "completed_with_issues"},
    "paused": {"working", "idle", "stopped"}, "completed": {"idle", "assigned", "stopped"},
    "completed_with_issues": {"idle", "assigned", "stopped"},
    "failed": {"idle", "assigned", "stopped"}, "stopped": {"idle"}, "interrupted": {"idle", "assigned"},
}


def coworker_transition(current: str, target: str) -> str:
    if target not in COWORKER_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid coworker lifecycle transition: {current} -> {target}")
    return target
