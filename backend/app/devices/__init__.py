"""IRIS Universal Device Intelligence & Execution Package.

Provides capability-driven, cross-device execution across the Windows workstation
and Android companion phone via Sovereign Mesh.
"""

from app.devices.android.executor import AndroidDeviceExecutor, android_device_executor
from app.devices.contracts import (
    CapabilityCategory,
    CapabilityRisk,
    DeviceCapability,
    DeviceExecutionRequest,
    DeviceExecutionResult,
    DeviceType,
)
from app.devices.registry import (
    DeviceCapabilityRegistry,
    RegisteredDevice,
    default_registry,
)
from app.devices.target_resolver import (
    DeviceTargetResolver,
    TargetResolutionResult,
    default_target_resolver,
)
from app.devices.windows.app_discovery import DiscoveredApp, WindowsAppDiscovery, windows_app_discovery
from app.devices.windows.browser_discovery import (
    DiscoveredBrowser,
    WindowsBrowserDiscovery,
    windows_browser_discovery,
)
from app.devices.windows.executor import WindowsDeviceExecutor
from app.devices.windows.system_control import WindowsSystemControl, windows_system_control

__all__ = [
    "CapabilityCategory",
    "CapabilityRisk",
    "DeviceCapability",
    "DeviceExecutionRequest",
    "DeviceExecutionResult",
    "DeviceType",
    "RegisteredDevice",
    "DeviceCapabilityRegistry",
    "default_registry",
    "DeviceTargetResolver",
    "TargetResolutionResult",
    "default_target_resolver",
    "DiscoveredApp",
    "WindowsAppDiscovery",
    "windows_app_discovery",
    "DiscoveredBrowser",
    "WindowsBrowserDiscovery",
    "windows_browser_discovery",
    "WindowsSystemControl",
    "windows_system_control",
    "WindowsDeviceExecutor",
    "AndroidDeviceExecutor",
    "android_device_executor",
]
