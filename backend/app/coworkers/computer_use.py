"""Provider-neutral computer-use contract and explicitly simulated local provider."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ComputerUseEvent:
    kind: str
    detail: dict


@dataclass
class ComputerUseResult:
    provider: str
    is_mock: bool
    status: str
    evidence: list[dict] = field(default_factory=list)
    events: list[ComputerUseEvent] = field(default_factory=list)


class ComputerUseProvider(Protocol):
    async def detect(self) -> dict: ...
    async def create_environment(self, task_id: str) -> str: ...
    async def inspect(self, environment_id: str) -> dict: ...
    async def act(self, environment_id: str, action: dict) -> ComputerUseEvent: ...
    async def capture_evidence(self, environment_id: str) -> dict: ...
    async def stop(self, environment_id: str) -> None: ...
    async def release(self, environment_id: str) -> None: ...


class MockLocalComputerUse:
    """Deterministic offline contract demo; never controls a real desktop."""
    provider_id = "mock-local-computer-use"

    async def detect(self) -> dict:
        return {"available": True, "provider": self.provider_id, "is_mock": True,
                "capabilities": ["inspect", "click", "type", "capture_evidence", "stop", "release"]}

    async def create_environment(self, task_id: str) -> str:
        return f"mock-env:{task_id}"

    async def inspect(self, environment_id: str) -> dict:
        return {"environment_id":environment_id,"title":"IRIS local CUA demo page",
                "controls":[{"id":"demo-button","label":"Run harmless demo"}],"is_mock":True}

    async def act(self, environment_id: str, action: dict) -> ComputerUseEvent:
        if environment_id.startswith("mock-env:") and action.get("target") == "demo-button" and action.get("type") == "click":
            return ComputerUseEvent("action_completed",{"target":"demo-button","result":"Demo button activated","is_mock":True})
        raise ValueError("Mock computer-use provider denies actions outside its fixed demonstration.")

    async def capture_evidence(self, environment_id: str) -> dict:
        if not environment_id.startswith("mock-env:"): raise ValueError("Unknown mock environment")
        return {"kind":"simulated_ui_state","text":"Demo button activated","is_mock":True}

    async def stop(self, environment_id: str) -> None:
        if not environment_id.startswith("mock-env:"): raise ValueError("Unknown mock environment")

    async def release(self, environment_id: str) -> None:
        if not environment_id.startswith("mock-env:"): raise ValueError("Unknown mock environment")


async def run_mock_demo(task_id: str = "harmless-demo") -> ComputerUseResult:
    provider = MockLocalComputerUse()
    await provider.detect()
    environment = await provider.create_environment(task_id)
    events = [ComputerUseEvent("environment_created", {"environment_id":environment,"is_mock":True})]
    events.append(ComputerUseEvent("environment_inspected", await provider.inspect(environment)))
    events.append(await provider.act(environment,{"type":"click","target":"demo-button"}))
    evidence = await provider.capture_evidence(environment)
    events.append(ComputerUseEvent("execution_stopped",{"is_mock":True}))
    await provider.stop(environment); await provider.release(environment)
    events.append(ComputerUseEvent("environment_released",{"is_mock":True}))
    return ComputerUseResult(provider.provider_id,True,"completed",[evidence],events)
