"""Device intelligence and capability contracts for IRIS P2.

Defines the shared, typed contract across Windows and Android:
- DeviceType & CapabilityCategory
- DeviceCapability definition
- DeviceExecutionRequest & DeviceExecutionResult
- Risk classifications & verification strategies
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DeviceType(str, Enum):
    """Supported device types across the Sovereign Mesh."""

    WINDOWS_LAPTOP = "laptop_windows"
    ANDROID_PHONE = "phone_android"
    LOCAL_AGENT = "local_agent"
    UNKNOWN = "unknown"


class CapabilityCategory(str, Enum):
    """Functional categories of device capabilities."""

    APPLICATION = "application"
    BROWSER = "browser"
    OS_CONTROL = "os_control"
    FILESYSTEM = "filesystem"
    SYSTEM_INFO = "system_info"
    TELEMETRY = "telemetry"
    AUTOMATION = "automation"


class CapabilityRisk(str, Enum):
    """Risk and permission boundaries for capability execution."""

    READ_ONLY = "READ_ONLY"
    REVERSIBLE = "REVERSIBLE"
    ORDINARY_WRITE = "ORDINARY_WRITE"
    SENSITIVE = "SENSITIVE"
    CRITICAL = "CRITICAL"


class DeviceCapability(BaseModel):
    """Specification of an operation a connected device can execute."""

    capability_id: str = Field(..., description="Unique capability identifier, e.g. 'windows.app.launch'")
    name: str = Field(..., description="Human-readable capability name")
    description: str = Field(..., description="Detailed explanation of what the capability accomplishes")
    device_type: DeviceType = Field(..., description="Operating system / platform supporting this capability")
    category: CapabilityCategory = Field(..., description="Functional category")
    input_schema: dict[str, Any] = Field(default_factory=dict, description="JSON schema defining required and optional parameters")
    output_schema: dict[str, Any] = Field(default_factory=dict, description="JSON schema defining return payload")
    risk_level: CapabilityRisk = Field(default=CapabilityRisk.ORDINARY_WRITE)
    requires_approval: bool = Field(default=False, description="Whether execution requires explicit confirmation token")
    verification_strategy: str = Field(default="process_detection", description="Mechanism used to verify postconditions")
    is_available: bool = Field(default=True, description="Whether currently usable on the target device")
    execution_timeout_seconds: float = Field(default=30.0, description="Max execution time before timeout")
    idempotent: bool = Field(default=False, description="Whether repeated identical executions are safe without side effects")
    version: str = Field(default="1.0.0", description="Capability contract version")


class DeviceExecutionRequest(BaseModel):
    """Standardized request envelope for executing a capability on any device."""

    request_id: str = Field(default_factory=lambda: f"dreq_{uuid.uuid4().hex[:12]}")
    correlation_id: str = Field(default_factory=lambda: f"corr_{uuid.uuid4().hex[:12]}")
    target_device_id: str = Field(..., description="Target device ID in Sovereign Mesh")
    target_device_type: DeviceType = Field(default=DeviceType.UNKNOWN)
    capability_id: str = Field(..., description="Capability to execute")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Validated arguments matching capability input schema")
    timestamp: float = Field(default_factory=time.time)
    expires_at: float = Field(default_factory=lambda: time.time() + 60.0)
    approval_token: str | None = Field(default=None, description="Approval token if authorizing sensitive action")
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeviceExecutionResult(BaseModel):
    """Standardized execution result envelope returned from any device."""

    request_id: str
    correlation_id: str = ""
    device_id: str
    capability_id: str
    success: bool
    data: Any = None
    error: str | None = None
    verified: bool = False
    verification_details: str | None = None
    duration_ms: int = 0
    executed_at: float = Field(default_factory=time.time)
