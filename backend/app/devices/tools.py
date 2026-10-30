"""IRIS Capability-Driven Device Agent Tools.

Exposes universal device intelligence to the IRIS Agent and reasoning loop:
- UniversalAppTool (cross-device dynamic app launch with browser fallback)
- GetDeviceCapabilitiesTool (device & capability discovery)
- GetDeviceBatteryTool (real-time power telemetry)
- LockWorkstationCapabilityTool (workstation security with verification)
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import Tool
from app.devices.android.executor import android_device_executor
from app.devices.contracts import (
    DeviceExecutionRequest,
    DeviceType,
)
from app.devices.registry import default_registry
from app.devices.target_resolver import default_target_resolver
from app.devices.windows.executor import WindowsDeviceExecutor
from app.models.user import User

logger = logging.getLogger(__name__)

_windows_executor = WindowsDeviceExecutor()


class UniversalAppParams(BaseModel):
    app: str = Field(
        ...,
        description="Name of the application or service (e.g. 'VS Code', 'Chrome', 'Google Drive', 'WhatsApp', 'Notion', 'Terminal')",
    )
    target_device: str | None = Field(
        default=None,
        description="Target device override ('laptop', 'phone', or null for automatic capability discovery)",
    )
    arguments: str | None = Field(
        default=None,
        description="Optional command-line arguments, URL, or working directory",
    )


class UniversalAppTool(Tool):
    """Universal cross-device application and service launcher."""

    name = "universal_app_launcher"
    description = (
        "Launch an application or web destination on Windows laptop or Android companion phone. "
        "Dynamically discovers installed applications, resolves target device, and automatically "
        "falls back to web browser for online services (e.g. Google Drive, Docs, Notion)."
    )
    parameters_schema = UniversalAppParams
    read_only = False

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        raw_app = kwargs.get("app", "").strip()
        target_override = kwargs.get("target_device")
        arguments = kwargs.get("arguments")

        if not raw_app:
            return ToolResult(tool_name=self.name, success=False, error="Application name is required.")

        # Resolve target device and entity
        resolution = default_target_resolver.resolve(f"Open {raw_app} on {target_override}" if target_override else f"Open {raw_app}")
        target_device = resolution.target_device

        # If user explicitly overrode target device in kwargs
        if target_override:
            low_override = target_override.lower()
            if "phone" in low_override or "mobile" in low_override or "android" in low_override:
                target_device = DeviceType.ANDROID_PHONE
            elif "laptop" in low_override or "pc" in low_override or "windows" in low_override:
                target_device = DeviceType.WINDOWS_LAPTOP

        clean_entity = resolution.cleaned_query or raw_app

        # --- Branch 1: Android Companion ---
        if target_device == DeviceType.ANDROID_PHONE:
            req = DeviceExecutionRequest(
                target_device_id="phone_android",
                target_device_type=DeviceType.ANDROID_PHONE,
                capability_id="android.app.launch",
                parameters={"app_name": clean_entity, "package_name": None},
                metadata={"user_id": str(user.id)},
            )
            exec_res = await android_device_executor.execute_async(req, db=db, user_id=str(user.id))
            if exec_res.success:
                summary = f"📱 Opened **{clean_entity.title()}** on your Android phone."
                return ToolResult(tool_name=self.name, success=True, data=exec_res.data, summary=summary)
            else:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=exec_res.error,
                    summary=f"⚠️ {exec_res.error}",
                )

        # --- Branch 2: Windows Laptop Workstation ---
        req = DeviceExecutionRequest(
            target_device_id="laptop_windows",
            target_device_type=DeviceType.WINDOWS_LAPTOP,
            capability_id="windows.app.launch",
            parameters={"app_name": clean_entity, "argument": arguments},
            metadata={"user_id": str(user.id)},
        )
        exec_res = _windows_executor.execute(req)

        if exec_res.success:
            data = exec_res.data or {}
            if "browser" in data:
                summary = f"🌐 Opened **{clean_entity.title()}** in {data.get('browser')} at `{data.get('url')}` on your Windows laptop."
            else:
                summary = f"💻 Opened **{data.get('app_name', clean_entity.title())}** on your Windows laptop."
            return ToolResult(tool_name=self.name, success=True, data=data, summary=summary)
        else:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=exec_res.error,
                summary=f"⚠️ {exec_res.error}",
            )


class DeviceCapabilitiesParams(BaseModel):
    device_type: str | None = Field(
        default=None,
        description="Filter capabilities by device ('laptop', 'phone', or null for all)",
    )


class GetDeviceCapabilitiesTool(Tool):
    """Inspects connected devices and dynamically discovered capabilities."""

    name = "get_device_capabilities"
    description = (
        "Inspect connected hardware devices (Windows workstation, Android phone) "
        "and discover their available execution capabilities, online status, and battery telemetry."
    )
    parameters_schema = DeviceCapabilitiesParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        device_filter = kwargs.get("device_type")
        filter_type = None
        if device_filter:
            low = device_filter.lower()
            if "laptop" in low or "windows" in low:
                filter_type = DeviceType.WINDOWS_LAPTOP
            elif "phone" in low or "android" in low:
                filter_type = DeviceType.ANDROID_PHONE

        devices = default_registry.list_devices()
        output_devices = []

        for dev in devices:
            if filter_type and dev.device_type != filter_type:
                continue
            is_online = default_registry.is_device_online(dev.device_type, db=db, user_id=str(user.id))
            caps = default_registry.get_capabilities(dev.device_type)
            output_devices.append({
                "device_id": dev.device_id,
                "device_name": dev.device_name,
                "device_type": dev.device_type.value,
                "is_online": is_online,
                "telemetry": dev.telemetry,
                "capabilities": [c.capability_id for c in caps],
            })

        summary = f"Discovered {len(output_devices)} connected hardware endpoint(s) across Sovereign Mesh."
        return ToolResult(tool_name=self.name, success=True, data={"devices": output_devices}, summary=summary)


class DeviceBatteryParams(BaseModel):
    target_device: str | None = Field(
        default=None,
        description="Target device ('laptop', 'phone', or null for both)",
    )


class GetDeviceBatteryTool(Tool):
    """Reads battery telemetry across connected devices."""

    name = "get_device_battery"
    description = (
        "Read live battery percentage and power telemetry from the Windows laptop workstation "
        "or connected Android phone."
    )
    parameters_schema = DeviceBatteryParams
    read_only = True

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        target = (kwargs.get("target_device") or "").lower()
        results: dict[str, Any] = {}
        summary_lines = []

        # 1. Windows Workstation
        if not target or "laptop" in target or "pc" in target or "windows" in target:
            req_win = DeviceExecutionRequest(
                target_device_id="laptop_windows",
                target_device_type=DeviceType.WINDOWS_LAPTOP,
                capability_id="windows.system.battery",
            )
            win_res = _windows_executor.execute(req_win)
            if win_res.success and win_res.data:
                pct = win_res.data.get("battery_level_percent")
                charging = win_res.data.get("is_charging")
                state = "Charging" if charging else "Discharging"
                results["laptop"] = win_res.data
                summary_lines.append(f"💻 **Laptop**: {pct}% ({state})" if pct is not None else "💻 **Laptop**: Power status available (AC plugged in).")

        # 2. Android Phone
        if not target or "phone" in target or "mobile" in target or "android" in target:
            req_android = DeviceExecutionRequest(
                target_device_id="phone_android",
                target_device_type=DeviceType.ANDROID_PHONE,
                capability_id="android.system.battery",
            )
            phone_res = await android_device_executor.execute_async(req_android, db=db, user_id=str(user.id))
            if phone_res.success and phone_res.data:
                pct = phone_res.data.get("battery_level")
                charging = phone_res.data.get("is_charging")
                state = "Charging" if charging else "On Battery"
                results["phone"] = phone_res.data
                summary_lines.append(f"📱 **Phone**: {pct}% ({state})" if pct is not None else "📱 **Phone**: Telemetry pending from companion.")

        summary = "\n".join(summary_lines) if summary_lines else "Battery telemetry could not be retrieved."
        return ToolResult(tool_name=self.name, success=bool(results), data=results, summary=summary)


def device_tools() -> list[Tool]:
    """Factory returning universal device intelligence tools."""
    return [
        UniversalAppTool(),
        GetDeviceCapabilitiesTool(),
        GetDeviceBatteryTool(),
    ]
