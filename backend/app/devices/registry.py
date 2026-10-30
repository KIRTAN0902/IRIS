"""IRIS Device Capability Registry: Central registry for device discovery, capabilities, and telemetry.

Maintains live state of registered devices (Windows laptop workstation, Android companion phone),
registered typed capabilities, online/offline presence, telemetry, and dynamically discovered applications.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from pydantic import BaseModel, Field

from app.devices.contracts import (
    CapabilityCategory,
    CapabilityRisk,
    DeviceCapability,
    DeviceType,
)

logger = logging.getLogger(__name__)


class RegisteredDevice(BaseModel):
    """Represents a connected or paired hardware endpoint in Sovereign Mesh."""

    device_id: str = Field(..., description="Unique device ID (e.g. 'laptop_windows' or mesh device UUID)")
    device_type: DeviceType = Field(..., description="Device operating system and form factor")
    device_name: str = Field(..., description="Friendly human-readable device name")
    status: str = Field(default="offline", description="'online', 'offline', 'standby', 'unreachable'")
    last_seen: float = Field(default_factory=time.time)
    latency_ms: float | None = Field(default=None)
    telemetry: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, DeviceCapability] = Field(default_factory=dict)
    installed_apps: list[str] = Field(default_factory=list, description="Normalized lowercase app names/labels")
    installed_apps_metadata: list[dict[str, str]] = Field(default_factory=list, description="App details (name, package/path)")


class DeviceCapabilityRegistry:
    """Singleton registry coordinating multi-device discovery, capabilities, and telemetry."""

    _instance: DeviceCapabilityRegistry | None = None
    _lock = threading.RLock()

    def __new__(cls) -> DeviceCapabilityRegistry:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._devices: dict[str, RegisteredDevice] = {}
        self._capabilities_by_type: dict[DeviceType, dict[str, DeviceCapability]] = {
            DeviceType.WINDOWS_LAPTOP: {},
            DeviceType.ANDROID_PHONE: {},
        }
        self._init_standard_capabilities()
        self._init_default_devices()
        self._initialized = True

    def _init_standard_capabilities(self) -> None:
        """Initializes the baseline typed capabilities for Windows and Android."""
        # --- Windows Capabilities ---
        win_caps = [
            DeviceCapability(
                capability_id="windows.app.launch",
                name="Launch Windows Application",
                description="Dynamically discovers and launches any desktop, UWP, or CLI application on Windows.",
                device_type=DeviceType.WINDOWS_LAPTOP,
                category=CapabilityCategory.APPLICATION,
                input_schema={
                    "type": "object",
                    "properties": {
                        "app_name": {"type": "string", "description": "Application name or query"},
                        "arguments": {"type": "string", "description": "Optional CLI arguments or path"},
                        "target_directory": {"type": "string", "description": "Working directory for launch"},
                    },
                    "required": ["app_name"],
                },
                risk_level=CapabilityRisk.ORDINARY_WRITE,
                verification_strategy="process_and_window_detection",
                idempotent=False,
            ),
            DeviceCapability(
                capability_id="windows.browser.open_url",
                name="Open URL in Windows Browser",
                description="Opens a secure web URL in the user's default or specified Windows browser.",
                device_type=DeviceType.WINDOWS_LAPTOP,
                category=CapabilityCategory.BROWSER,
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target HTTP/HTTPS URL"},
                        "browser": {"type": "string", "description": "Optional browser id (chrome, edge, brave)"},
                    },
                    "required": ["url"],
                },
                risk_level=CapabilityRisk.ORDINARY_WRITE,
                verification_strategy="browser_process_detection",
                idempotent=True,
            ),
            DeviceCapability(
                capability_id="windows.system.lock",
                name="Lock Windows Workstation",
                description="Immediately locks the Windows desktop session for privacy.",
                device_type=DeviceType.WINDOWS_LAPTOP,
                category=CapabilityCategory.OS_CONTROL,
                input_schema={"type": "object"},
                risk_level=CapabilityRisk.REVERSIBLE,
                requires_approval=False,
                verification_strategy="session_locked_query",
                idempotent=True,
            ),
            DeviceCapability(
                capability_id="windows.system.battery",
                name="Read Windows Laptop Battery",
                description="Fetches live battery level, charging status, and AC power supply state.",
                device_type=DeviceType.WINDOWS_LAPTOP,
                category=CapabilityCategory.TELEMETRY,
                input_schema={"type": "object"},
                risk_level=CapabilityRisk.READ_ONLY,
                verification_strategy="win32_power_status_query",
                idempotent=True,
            ),
            DeviceCapability(
                capability_id="windows.system.info",
                name="Get Windows System Info",
                description="Retrieves OS version, architecture, CPU, memory, and disk usage.",
                device_type=DeviceType.WINDOWS_LAPTOP,
                category=CapabilityCategory.SYSTEM_INFO,
                input_schema={"type": "object"},
                risk_level=CapabilityRisk.READ_ONLY,
                verification_strategy="system_query",
                idempotent=True,
            ),
            DeviceCapability(
                capability_id="windows.filesystem.open",
                name="Open Windows Path in Explorer",
                description="Opens a local file, folder, or drive path in Windows File Explorer.",
                device_type=DeviceType.WINDOWS_LAPTOP,
                category=CapabilityCategory.FILESYSTEM,
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "Path or folder to reveal"}},
                    "required": ["path"],
                },
                risk_level=CapabilityRisk.ORDINARY_WRITE,
                verification_strategy="explorer_spawn_check",
                idempotent=True,
            ),
        ]
        for cap in win_caps:
            self.register_capability(DeviceType.WINDOWS_LAPTOP, cap)

        # --- Android Capabilities ---
        android_caps = [
            DeviceCapability(
                capability_id="android.app.launch",
                name="Launch Android Application",
                description="Launches an Android application by label or package name via Intent.",
                device_type=DeviceType.ANDROID_PHONE,
                category=CapabilityCategory.APPLICATION,
                input_schema={
                    "type": "object",
                    "properties": {
                        "app_name": {"type": "string", "description": "Android application name (e.g. WhatsApp)"},
                        "package_name": {"type": "string", "description": "Optional explicit package name"},
                    },
                    "required": ["app_name"],
                },
                risk_level=CapabilityRisk.ORDINARY_WRITE,
                verification_strategy="intent_dispatch_verification",
                idempotent=False,
            ),
            DeviceCapability(
                capability_id="android.browser.open_url",
                name="Open URL on Android",
                description="Opens a web URL in the default browser on the Android companion phone.",
                device_type=DeviceType.ANDROID_PHONE,
                category=CapabilityCategory.BROWSER,
                input_schema={
                    "type": "object",
                    "properties": {"url": {"type": "string", "description": "Target HTTP/HTTPS URL"}},
                    "required": ["url"],
                },
                risk_level=CapabilityRisk.ORDINARY_WRITE,
                verification_strategy="intent_dispatch_verification",
                idempotent=True,
            ),
            DeviceCapability(
                capability_id="android.system.battery",
                name="Read Android Battery",
                description="Retrieves live battery percentage and charging state from the companion phone.",
                device_type=DeviceType.ANDROID_PHONE,
                category=CapabilityCategory.TELEMETRY,
                input_schema={"type": "object"},
                risk_level=CapabilityRisk.READ_ONLY,
                verification_strategy="battery_telemetry_query",
                idempotent=True,
            ),
            DeviceCapability(
                capability_id="android.system.network",
                name="Read Android Network Status",
                description="Retrieves current WiFi SSID, cellular connection state, and IP address.",
                device_type=DeviceType.ANDROID_PHONE,
                category=CapabilityCategory.TELEMETRY,
                input_schema={"type": "object"},
                risk_level=CapabilityRisk.READ_ONLY,
                verification_strategy="network_telemetry_query",
                idempotent=True,
            ),
            DeviceCapability(
                capability_id="android.system.info",
                name="Get Android Device Info",
                description="Retrieves phone model (e.g. Realme GT 7T), Android OS version, and build info.",
                device_type=DeviceType.ANDROID_PHONE,
                category=CapabilityCategory.SYSTEM_INFO,
                input_schema={"type": "object"},
                risk_level=CapabilityRisk.READ_ONLY,
                verification_strategy="companion_info_query",
                idempotent=True,
            ),
            DeviceCapability(
                capability_id="android.system.ring",
                name="Ring Android Phone",
                description="Find My Phone: Rings phone at maximum volume to locate it.",
                device_type=DeviceType.ANDROID_PHONE,
                category=CapabilityCategory.OS_CONTROL,
                input_schema={"type": "object"},
                risk_level=CapabilityRisk.REVERSIBLE,
                verification_strategy="audio_alert_dispatch",
                idempotent=True,
            ),
        ]
        for cap in android_caps:
            self.register_capability(DeviceType.ANDROID_PHONE, cap)

    def _init_default_devices(self) -> None:
        """Sets up default hardware device records for Windows Workstation and Realme companion."""
        # 1. Primary Windows Laptop Workstation
        self._devices["laptop_windows"] = RegisteredDevice(
            device_id="laptop_windows",
            device_type=DeviceType.WINDOWS_LAPTOP,
            device_name="Windows Workstation",
            status="online",
            capabilities=dict(self._capabilities_by_type[DeviceType.WINDOWS_LAPTOP]),
        )

        # 2. Android Phone Companion
        self._devices["phone_android"] = RegisteredDevice(
            device_id="phone_android",
            device_type=DeviceType.ANDROID_PHONE,
            device_name="Realme GT 7T",
            status="standby",
            capabilities=dict(self._capabilities_by_type[DeviceType.ANDROID_PHONE]),
        )

    # --- Device & Capability Access ---

    def register_device(self, device: RegisteredDevice) -> None:
        with self._lock:
            self._devices[device.device_id] = device

    def unregister_device(self, device_id: str) -> None:
        with self._lock:
            self._devices.pop(device_id, None)

    def get_device(self, device_id: str) -> RegisteredDevice | None:
        with self._lock:
            return self._devices.get(device_id)

    def get_device_by_type(self, device_type: DeviceType) -> RegisteredDevice | None:
        with self._lock:
            for dev in self._devices.values():
                if dev.device_type == device_type:
                    return dev
            return None

    def list_devices(self) -> list[RegisteredDevice]:
        with self._lock:
            return list(self._devices.values())

    def register_capability(self, device_type: DeviceType, capability: DeviceCapability) -> None:
        with self._lock:
            if device_type not in self._capabilities_by_type:
                self._capabilities_by_type[device_type] = {}
            self._capabilities_by_type[device_type][capability.capability_id] = capability

            # Update existing devices of this type
            for dev in self._devices.values():
                if dev.device_type == device_type:
                    dev.capabilities[capability.capability_id] = capability

    def get_capabilities(self, device_type: DeviceType | None = None) -> list[DeviceCapability]:
        with self._lock:
            if device_type is not None:
                return list(self._capabilities_by_type.get(device_type, {}).values())
            all_caps: list[DeviceCapability] = []
            for caps_dict in self._capabilities_by_type.values():
                all_caps.extend(caps_dict.values())
            return all_caps

    def find_capability(
        self,
        capability_id: str,
        device_type: DeviceType | None = None,
    ) -> DeviceCapability | None:
        with self._lock:
            if device_type:
                return self._capabilities_by_type.get(device_type, {}).get(capability_id)
            for caps_dict in self._capabilities_by_type.values():
                if capability_id in caps_dict:
                    return caps_dict[capability_id]
            return None

    # --- Live Presence & Telemetry ---

    def is_device_online(
        self,
        device_type: DeviceType,
        db: Any | None = None,
        user_id: str | None = None,
    ) -> bool:
        """Determines if a device type is online right now.

        For Windows:
        - If running as local daemon/Electron, Windows is online.
        - If cloud relay, checks laptop host heartbeat.

        For Android:
        - Checks live WebSocket connection in MeshHub.
        - Or checks recent heartbeat in DB paired_devices within 180s.
        """
        if device_type == DeviceType.WINDOWS_LAPTOP:
            # Check local OS or relay
            try:
                from app.services import mesh_relay_service as mrs
                if mrs.is_local_windows_host():
                    return True
                if db and user_id:
                    return mrs.is_host_laptop_online(db, user_id, threshold_seconds=180.0)
            except Exception:
                pass
            dev = self.get_device_by_type(DeviceType.WINDOWS_LAPTOP)
            return dev.status == "online" if dev else True

        if device_type == DeviceType.ANDROID_PHONE:
            # Check MeshHub active connections
            try:
                from app.services import mesh_service as ms
                for d in ms.hub.devices.values():
                    if "phone" in d.device_type:
                        return True
            except Exception:
                pass

            # Check DB paired devices heartbeat
            if db and user_id:
                try:
                    from app.services import mesh_relay_service as mrs
                    paired = mrs.list_paired_devices(db, user_id)
                    cutoff = time.time() - 180.0
                    for p in paired:
                        if "phone" in (p.device_type or "").lower():
                            if p.last_seen_at and p.last_seen_at.timestamp() >= cutoff:
                                return True
                except Exception:
                    pass

            dev = self.get_device_by_type(DeviceType.ANDROID_PHONE)
            if dev:
                return dev.status == "online" or (time.time() - dev.last_seen < 180.0)
            return False

        return False

    def update_device_presence(
        self,
        device_id: str,
        status: str,
        latency_ms: float | None = None,
    ) -> None:
        with self._lock:
            dev = self._devices.get(device_id)
            if dev:
                dev.status = status
                dev.last_seen = time.time()
                if latency_ms is not None:
                    dev.latency_ms = latency_ms

    def update_device_telemetry(
        self,
        device_id: str,
        battery: int | None = None,
        is_charging: bool | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            dev = self._devices.get(device_id)
            if dev:
                if battery is not None:
                    dev.telemetry["battery_level"] = battery
                if is_charging is not None:
                    dev.telemetry["is_charging"] = is_charging
                if extra:
                    dev.telemetry.update(extra)
                dev.last_seen = time.time()

    # --- Dynamic Application Catalog Sync ---

    def update_installed_apps(
        self,
        device_type: DeviceType,
        apps: list[dict[str, str]] | list[str],
    ) -> None:
        """Stores the list of dynamically discovered applications for a device."""
        with self._lock:
            dev = self.get_device_by_type(device_type)
            if not dev:
                return

            names: list[str] = []
            metadata: list[dict[str, str]] = []

            for item in apps:
                if isinstance(item, str):
                    clean = item.strip().lower()
                    if clean:
                        names.append(clean)
                        metadata.append({"name": item.strip(), "package": item.strip()})
                elif isinstance(item, dict):
                    name = item.get("name", "").strip()
                    pkg = item.get("package") or item.get("path") or ""
                    if name:
                        names.append(name.lower())
                        metadata.append({"name": name, "package": pkg})

            dev.installed_apps = sorted(list(set(names)))
            dev.installed_apps_metadata = metadata
            logger.info("Updated %d installed apps for %s", len(names), device_type.value)

    def get_installed_apps(self, device_type: DeviceType) -> list[str]:
        with self._lock:
            dev = self.get_device_by_type(device_type)
            if not dev:
                return []
            if dev.installed_apps:
                return list(dev.installed_apps)

            # Lazy discover on Windows if empty
            if device_type == DeviceType.WINDOWS_LAPTOP:
                try:
                    from app.devices.windows.app_discovery import windows_app_discovery
                    apps = windows_app_discovery.list_all_apps()
                    self.update_installed_apps(
                        DeviceType.WINDOWS_LAPTOP,
                        [{"name": a["name"], "package": a["target"]} for a in apps],
                    )
                    return [a["name"].lower() for a in apps]
                except Exception as exc:
                    logger.warning("Failed lazy Windows app discovery: %s", exc)

            return list(dev.installed_apps)

    def is_app_installed(self, device_type: DeviceType, app_query: str) -> bool:
        """Checks if an app is installed on the given device by exact or partial match."""
        clean = app_query.strip().lower()
        if not clean:
            return False

        installed = self.get_installed_apps(device_type)
        if clean in installed:
            return True

        for app in installed:
            if clean in app or app in clean:
                return True
        return False


# Global singleton instance
default_registry = DeviceCapabilityRegistry()
