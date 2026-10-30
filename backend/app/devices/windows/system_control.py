"""Native Windows System Control and Telemetry.

Direct Win32 API integration for workstation lock, power/battery inspection,
and system status without fragile shell commands.
"""

from __future__ import annotations

import ctypes
import os
import platform
import socket
from typing import Any

from app.core.logging import get_logger

logger = get_logger("iris.devices.windows.system_control")


class _SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_byte),
        ("BatteryFlag", ctypes.c_byte),
        ("BatteryLifePercent", ctypes.c_byte),
        ("SystemStatusFlag", ctypes.c_byte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


class WindowsSystemControl:
    """Provides native Win32 access to system controls and telemetry."""

    def lock_workstation(self) -> dict[str, Any]:
        """Locks the Windows workstation immediately using native User32 LockWorkStation."""
        if os.name != "nt":
            return {"success": False, "error": "Lock workstation only supported on Windows."}

        try:
            res = ctypes.windll.user32.LockWorkStation()
            success = bool(res != 0)
            return {
                "success": success,
                "locked": success,
                "message": "Windows workstation locked successfully." if success else "Failed to lock workstation.",
            }
        except Exception as exc:
            logger.error("LockWorkStation API failed: %s", exc)
            return {"success": False, "error": str(exc), "message": f"Lock API error: {exc}"}

    def get_battery_status(self) -> dict[str, Any]:
        """Reads live battery and AC charging state directly from Kernel32 GetSystemPowerStatus."""
        if os.name != "nt":
            return {"battery_percent": None, "is_charging": None, "is_present": False}

        status = _SYSTEM_POWER_STATUS()
        try:
            success = ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status))
            if not success:
                return {"battery_percent": None, "is_charging": None, "is_present": False}

            # ACLineStatus: 0 = Offline (on battery), 1 = Online (plugged in), 255 = Unknown
            # BatteryLifePercent: 0..100, or 255 = Unknown
            percent = int(status.BatteryLifePercent) if status.BatteryLifePercent != 255 else None
            is_charging = bool(status.ACLineStatus == 1)
            battery_present = bool(status.BatteryFlag != 128)  # 128 = No system battery (desktop)

            return {
                "battery_percent": percent,
                "is_charging": is_charging,
                "is_present": battery_present,
                "ac_status": "PLUGGED_IN" if status.ACLineStatus == 1 else "ON_BATTERY",
                "message": f"Battery: {percent}% ({'Charging' if is_charging else 'Discharging'})" if percent is not None else "AC Power Connected (No battery)",
            }
        except Exception as exc:
            logger.debug("GetSystemPowerStatus error: %s", exc)
            return {"battery_percent": None, "is_charging": None, "error": str(exc)}

    def get_system_info(self) -> dict[str, Any]:
        """Returns host workstation OS telemetry."""
        return {
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "hostname": platform.node(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
        }

    def check_network_connectivity(self) -> dict[str, Any]:
        """Quick check to verify outbound internet reachability."""
        try:
            # Check Google public DNS on port 53 (ultra-fast 500ms timeout)
            with socket.create_connection(("8.8.8.8", 53), timeout=1.0):
                return {"connected": True, "message": "Internet connection active."}
        except OSError:
            return {"connected": False, "message": "Internet connection unreachable."}


windows_system_control = WindowsSystemControl()
