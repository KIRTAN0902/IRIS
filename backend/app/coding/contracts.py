"""Provider-neutral coding execution contracts and lifecycle validation."""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_USER = "waiting_for_user"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


TASK_TRANSITIONS = {
    TaskStatus.DRAFT: {TaskStatus.AWAITING_APPROVAL, TaskStatus.CANCELLED},
    TaskStatus.AWAITING_APPROVAL: {TaskStatus.QUEUED, TaskStatus.CANCELLED},
    TaskStatus.QUEUED: {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.RUNNING: {TaskStatus.WAITING_FOR_USER, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.INTERRUPTED},
    TaskStatus.WAITING_FOR_USER: {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.INTERRUPTED},
    TaskStatus.INTERRUPTED: {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(), TaskStatus.FAILED: set(), TaskStatus.CANCELLED: set(),
}


def validate_transition(before: TaskStatus, after: TaskStatus) -> None:
    if after not in TASK_TRANSITIONS[before]:
        raise ValueError(f"Invalid coding task transition: {before} -> {after}")


class TaskBrief(BaseModel):
    objective: str = Field(min_length=3)
    project_id: int
    agent_id: str
    architecture: str = ""
    relevant_decisions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    implementation: str = ""
    expected_behavior: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    restrictions: list[str] = Field(default_factory=list)

    def render(self, project_name: str, directory: str) -> str:
        sections = [f"Objective\n{self.objective}", f"Project\n{project_name}\nWorkspace: {directory}",
                    f"Architecture\n{self.architecture}", f"Relevant decisions\n" + "\n".join(self.relevant_decisions),
                    f"Constraints\n" + "\n".join(self.constraints), f"Required implementation\n{self.implementation}",
                    f"Expected behavior\n{self.expected_behavior}", f"Acceptance criteria\n" + "\n".join(self.acceptance_criteria),
                    f"Testing expectations\n" + "\n".join(self.tests), f"Restrictions\n" + "\n".join(self.restrictions)]
        return "\n\n".join(sections)


class AgentCapabilities(BaseModel):
    interactive: bool = False
    prompt_submission: bool = False
    streaming_output: bool = False
    resume: bool = False
    stop: bool = False
    follow_up: bool = False
    structured_events: bool = False


class CodingAgentAdapter(Protocol):
    agent_id: str
    capabilities: AgentCapabilities
    def detect(self) -> dict[str, Any]: ...
    def launch(self, directory: str, prompt: str, session_id: str) -> Any: ...
    def send_prompt(self, session_id: str, prompt: str) -> Any: ...
    def resume_session(self, directory: str, conversation_id: str) -> Any: ...
    def get_status(self, session_id: str) -> dict[str, Any]: ...
    def get_output(self, session_id: str) -> str: ...
    def stop(self, session_id: str) -> bool: ...
