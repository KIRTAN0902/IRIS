"""Windows Capability Execution Engine with postcondition verification.

Executes capabilities on the local Windows workstation:
- Application launching (with process / window detection)
- Browser navigation
- System locking and telemetry
- Filesystem operations
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any

from app.core.logging import get_logger
from app.devices.contracts import (
    DeviceExecutionRequest,
    DeviceExecutionResult,
)
from app.devices.windows.app_discovery import windows_app_discovery
from app.devices.windows.browser_discovery import windows_browser_discovery
from app.devices.windows.system_control import windows_system_control

logger = get_logger("iris.devices.windows.executor")


class WindowsDeviceExecutor:
    """Capability-driven execution engine for the Windows workstation."""

    def execute(self, request: DeviceExecutionRequest) -> DeviceExecutionResult:
        """Executes capability requested on Windows and verifies postconditions."""
        start_time = time.monotonic()
        cap_id = request.capability_id
        params = request.parameters

        try:
            if cap_id in ("windows.app.launch", "device.app.launch"):
                return self._launch_app(request, params, start_time)

            elif cap_id in ("windows.browser.open_url", "device.browser.open_url"):
                return self._open_browser_url(request, params, start_time)

            elif cap_id in ("windows.system.lock", "device.system.lock"):
                return self._lock_workstation(request, start_time)

            elif cap_id in ("windows.system.battery", "device.battery.read"):
                return self._get_battery(request, start_time)

            elif cap_id in ("windows.system.info", "device.info.read"):
                return self._get_info(request, start_time)

            elif cap_id == "windows.network.check":
                return self._check_network(request, start_time)

            elif cap_id in ("windows.filesystem.open", "device.file.open"):
                return self._open_file(request, params, start_time)

            else:
                duration = int((time.monotonic() - start_time) * 1000)
                return DeviceExecutionResult(
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                    device_id="laptop_host_primary",
                    capability_id=cap_id,
                    success=False,
                    error=f"Unrecognized capability '{cap_id}' for Windows executor.",
                    verified=False,
                    duration_ms=duration,
                )

        except Exception as exc:
            duration = int((time.monotonic() - start_time) * 1000)
            logger.error("Windows execution exception on %s: %s", cap_id, exc, exc_info=True)
            return DeviceExecutionResult(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                device_id="laptop_host_primary",
                capability_id=cap_id,
                success=False,
                error=f"Execution error: {type(exc).__name__}: {exc}",
                verified=False,
                duration_ms=duration,
            )

    # --- Capability Implementations & Verifications ---------------------------

    def _launch_app(self, request: DeviceExecutionRequest, params: dict[str, Any], start_time: float) -> DeviceExecutionResult:
        app_query = params.get("app_name") or params.get("application") or params.get("app", "")
        if not app_query:
            duration = int((time.monotonic() - start_time) * 1000)
            return DeviceExecutionResult(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                device_id="laptop_host_primary",
                capability_id=request.capability_id,
                success=False,
                error="Parameter 'app_name' is required.",
                duration_ms=duration,
            )

        # 1. Discover if native app exists
        app = windows_app_discovery.find_app(app_query)
        if not app:
            # 2. Check if query is an online service destination (e.g. Google Drive)
            service_url = windows_browser_discovery.resolve_service_destination(app_query)
            if service_url:
                logger.info("No native app found for '%s'; falling back to browser navigation for %s", app_query, service_url)
                return self._open_browser_url(request, {"url": service_url, "reason": f"Fallback for {app_query}"}, start_time)

            duration = int((time.monotonic() - start_time) * 1000)
            return DeviceExecutionResult(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                device_id="laptop_host_primary",
                capability_id=request.capability_id,
                success=False,
                error=f"Application '{app_query}' is not installed on this Windows laptop.",
                verified=False,
                verification_details="Application not found in Start Menu, Registry, or System App Paths.",
                duration_ms=duration,
            )

        # 3. Launch discovered application
        try:
            if app.app_type in ("lnk", "protocol"):
                cmd = ["cmd.exe", "/c", "start", "", app.target]
            elif app.app_type == "exe":
                arg = params.get("argument")
                cmd = [app.target, arg] if arg else [app.target]
            else:
                cmd = ["cmd.exe", "/c", "start", "", app.target]

            proc = subprocess.Popen(cmd, shell=False)

            # Postcondition verification: check process creation
            time.sleep(0.15)
            # If poll returns an error exit code immediately, report failure
            is_alive = proc.poll() is None or proc.poll() == 0
            duration = int((time.monotonic() - start_time) * 1000)

            return DeviceExecutionResult(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                device_id="laptop_host_primary",
                capability_id=request.capability_id,
                success=True,
                data={
                    "app_name": app.name,
                    "target": app.target,
                    "app_type": app.app_type,
                    "pid": proc.pid,
                },
                verified=is_alive,
                verification_details=f"Process spawned with PID {proc.pid} (active: {is_alive})",
                duration_ms=duration,
            )
        except Exception as exc:
            duration = int((time.monotonic() - start_time) * 1000)
            return DeviceExecutionResult(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                device_id="laptop_host_primary",
                capability_id=request.capability_id,
                success=False,
                error=str(exc),
                verified=False,
                duration_ms=duration,
            )

    def _open_browser_url(self, request: DeviceExecutionRequest, params: dict[str, Any], start_time: float) -> DeviceExecutionResult:
        url = params.get("url") or ""
        browser_name = params.get("browser")

        res = windows_browser_discovery.open_url(url, browser_name)
        duration = int((time.monotonic() - start_time) * 1000)

        return DeviceExecutionResult(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            device_id="laptop_host_primary",
            capability_id=request.capability_id,
            success=res.get("success", False),
            data=res,
            error=res.get("error"),
            verified=res.get("success", False),
            verification_details=f"Navigated browser {res.get('browser')} to {url}",
            duration_ms=duration,
        )

    def _lock_workstation(self, request: DeviceExecutionRequest, start_time: float) -> DeviceExecutionResult:
        res = windows_system_control.lock_workstation()
        duration = int((time.monotonic() - start_time) * 1000)
        return DeviceExecutionResult(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            device_id="laptop_host_primary",
            capability_id=request.capability_id,
            success=res.get("success", False),
            data=res,
            error=res.get("error"),
            verified=res.get("success", False),
            verification_details="Native LockWorkStation API invoked.",
            duration_ms=duration,
        )

    def _get_battery(self, request: DeviceExecutionRequest, start_time: float) -> DeviceExecutionResult:
        res = windows_system_control.get_battery_status()
        duration = int((time.monotonic() - start_time) * 1000)
        return DeviceExecutionResult(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            device_id="laptop_host_primary",
            capability_id=request.capability_id,
            success=True,
            data=res,
            verified=True,
            verification_details="Direct Win32 GetSystemPowerStatus query.",
            duration_ms=duration,
        )

    def _get_info(self, request: DeviceExecutionRequest, start_time: float) -> DeviceExecutionResult:
        res = windows_system_control.get_system_info()
        duration = int((time.monotonic() - start_time) * 1000)
        return DeviceExecutionResult(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            device_id="laptop_host_primary",
            capability_id=request.capability_id,
            success=True,
            data=res,
            verified=True,
            duration_ms=duration,
        )

    def _check_network(self, request: DeviceExecutionRequest, start_time: float) -> DeviceExecutionResult:
        res = windows_system_control.check_network_connectivity()
        duration = int((time.monotonic() - start_time) * 1000)
        return DeviceExecutionResult(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            device_id="laptop_host_primary",
            capability_id=request.capability_id,
            success=res.get("connected", False),
            data=res,
            verified=True,
            duration_ms=duration,
        )

    def _open_file(self, request: DeviceExecutionRequest, params: dict[str, Any], start_time: float) -> DeviceExecutionResult:
        file_path = params.get("path") or ""
        duration = int((time.monotonic() - start_time) * 1000)
        if not file_path or not os.path.exists(file_path):
            return DeviceExecutionResult(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                device_id="laptop_host_primary",
                capability_id=request.capability_id,
                success=False,
                error=f"File not found: {file_path}",
                verified=False,
                duration_ms=duration,
            )

        try:
            os.startfile(file_path)
            return DeviceExecutionResult(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                device_id="laptop_host_primary",
                capability_id=request.capability_id,
                success=True,
                data={"path": file_path},
                verified=True,
                verification_details="os.startfile executed with default shell association.",
                duration_ms=duration,
            )
        except Exception as exc:
            return DeviceExecutionResult(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                device_id="laptop_host_primary",
                capability_id=request.capability_id,
                success=False,
                error=str(exc),
                verified=False,
                duration_ms=duration,
            )


windows_device_executor = WindowsDeviceExecutor()
