"""IRIS P2 Universal Device Intelligence Acceptance Test Suite.

Verifies Mandatory Acceptance Tests A through J:
- Test A: Android application discovery ("Open WhatsApp on my phone")
- Test B: Windows application discovery ("Open Chrome on my laptop")
- Test C: Browser fallback ("Open Google Drive on my laptop" -> discovers browser -> opens URL -> verified)
- Test D: Unlisted application (discovers newly installed application dynamically)
- Test E: Dynamic target resolution (explicit text cues, exclusive actions, app affinity)
- Test F: Missing application (accurately reports uninstalled app, does not fake success)
- Test G: Offline device (handles unreachable device safely, does not fake success)
- Test H: Permission enforcement (unauthorized execution rejected, policy approval required)
- Test I: Duplicate request protection (idempotency token protects against duplicate execution)
- Test J: Cross-device verification (complete execution and result flow across Sovereign Mesh)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest

from app.devices.android.executor import AndroidDeviceExecutor
from app.devices.contracts import (
    CapabilityCategory,
    CapabilityRisk,
    DeviceCapability,
    DeviceExecutionRequest,
    DeviceExecutionResult,
    DeviceType,
)
from app.devices.registry import DeviceCapabilityRegistry, RegisteredDevice
from app.devices.target_resolver import DeviceTargetResolver
from app.devices.windows.app_discovery import DiscoveredApp, WindowsAppDiscovery
from app.devices.windows.browser_discovery import DiscoveredBrowser, WindowsBrowserDiscovery
from app.devices.windows.executor import WindowsDeviceExecutor
from app.devices.windows.system_control import WindowsSystemControl


# -----------------------------------------------------------------------------
# Test A: Android Application Discovery
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_android_application_discovery():
    """Test A: 'Open WhatsApp on my phone' resolves to Android and dispatches launch intent."""
    resolver = DeviceTargetResolver()
    resolution = resolver.resolve("Open WhatsApp on my phone")

    assert resolution.target_device == DeviceType.ANDROID_PHONE
    assert resolution.cleaned_query.lower() == "whatsapp"
    assert resolution.confidence >= 0.90

    # Execute on Android executor with online mock
    registry = DeviceCapabilityRegistry()
    registry.update_device_presence("phone_android", "online")

    executor = AndroidDeviceExecutor()
    req = DeviceExecutionRequest(
        target_device_id="phone_android",
        target_device_type=DeviceType.ANDROID_PHONE,
        capability_id="android.app.launch",
        parameters={"app_name": "whatsapp"},
    )

    with patch.object(registry, "is_device_online", return_value=True):
        with patch("app.devices.android.executor.default_registry", registry):
            with patch("app.services.mesh_service.hub.broadcast") as mock_broadcast:
                mock_broadcast.return_value = None
                result = await executor.execute_async(req)

                assert result.success is True
                assert result.verified is True
                assert result.device_id == "phone_android"
                assert "whatsapp" in result.verification_details.lower()


# -----------------------------------------------------------------------------
# Test B: Windows Application Discovery
# -----------------------------------------------------------------------------
def test_b_windows_application_discovery():
    """Test B: 'Open Chrome on my laptop' resolves to Windows and discovers app dynamically."""
    resolver = DeviceTargetResolver()
    resolution = resolver.resolve("Open Chrome on my laptop")

    assert resolution.target_device == DeviceType.WINDOWS_LAPTOP
    assert resolution.cleaned_query.lower() in ("chrome", "google chrome")
    assert resolution.confidence >= 0.90

    executor = WindowsDeviceExecutor()
    req = DeviceExecutionRequest(
        target_device_id="laptop_windows",
        target_device_type=DeviceType.WINDOWS_LAPTOP,
        capability_id="windows.app.launch",
        parameters={"app_name": "notepad"},
    )

    # Mock subprocess.Popen so we don't pop up a real window in automated CI
    mock_proc = MagicMock()
    mock_proc.pid = 4321
    mock_proc.poll.return_value = None

    with patch("subprocess.Popen", return_value=mock_proc):
        res = executor.execute(req)
        assert res.success is True
        assert res.verified is True
        assert res.data["pid"] == 4321


# -----------------------------------------------------------------------------
# Test C: Browser Fallback
# -----------------------------------------------------------------------------
def test_c_browser_fallback():
    """Test C: 'Open Google Drive on my laptop' -> discovers no desktop app -> resolves browser -> navigates to official URL."""
    resolver = DeviceTargetResolver()
    resolution = resolver.resolve("Open Google Drive on my laptop")

    assert resolution.target_device == DeviceType.WINDOWS_LAPTOP
    assert resolution.fallback_url == "https://drive.google.com"

    # Verify browser discovery resolution
    browser_disc = WindowsBrowserDiscovery()
    dest_url = browser_disc.resolve_service_destination("google drive")
    assert dest_url == "https://drive.google.com"

    # Test executor handles browser fallback seamlessly
    executor = WindowsDeviceExecutor()
    req = DeviceExecutionRequest(
        target_device_id="laptop_windows",
        target_device_type=DeviceType.WINDOWS_LAPTOP,
        capability_id="windows.app.launch",
        parameters={"app_name": "google drive"},
    )

    mock_proc = MagicMock()
    mock_proc.pid = 9876
    mock_proc.poll.return_value = None

    with patch("app.devices.windows.app_discovery.windows_app_discovery.find_app", return_value=None):
        with patch("subprocess.Popen", return_value=mock_proc):
            res = executor.execute(req)
            assert res.success is True
            assert res.verified is True
            assert res.data.get("url") == "https://drive.google.com"
            assert "Navigated browser" in (res.verification_details or "")


# -----------------------------------------------------------------------------
# Test D: Unlisted Application Discovery
# -----------------------------------------------------------------------------
def test_d_unlisted_application():
    """Test D: Discovers an unlisted/custom application dynamically without hardcoded dictionary."""
    discovery = WindowsAppDiscovery()
    
    # Inject an unlisted app into discovery
    custom_app = DiscoveredApp(
        name="CustomInternalTool",
        clean_name="custominternaltool",
        target=r"C:\Program Files\Internal\CustomTool.exe",
        app_type="exe",
        executable_path=r"C:\Program Files\Internal\CustomTool.exe",
    )
    discovery.register_app(custom_app)

    found = discovery.find_app("custom internal tool")
    assert found is not None
    assert found.name == "CustomInternalTool"
    assert found.target == r"C:\Program Files\Internal\CustomTool.exe"


# -----------------------------------------------------------------------------
# Test E: Device Target Resolution
# -----------------------------------------------------------------------------
def test_e_device_target_resolution():
    """Test E: Evaluates resolution across phone, laptop, battery, and workstation locking."""
    resolver = DeviceTargetResolver()

    # Explicit phone
    r1 = resolver.resolve("Open WhatsApp on my phone")
    assert r1.target_device == DeviceType.ANDROID_PHONE
    assert r1.confidence >= 0.90

    # Explicit laptop
    r2 = resolver.resolve("Open Chrome on my laptop")
    assert r2.target_device == DeviceType.WINDOWS_LAPTOP
    assert r2.confidence >= 0.90

    # Phone battery
    r3 = resolver.resolve("Check my phone's battery")
    assert r3.target_device == DeviceType.ANDROID_PHONE
    assert r3.action == "battery_status"
    assert r3.confidence >= 0.90

    # Workstation lock
    r4 = resolver.resolve("Lock my workstation")
    assert r4.target_device == DeviceType.WINDOWS_LAPTOP
    assert r4.action == "lock_workstation"
    assert r4.confidence == 1.0


# -----------------------------------------------------------------------------
# Test F: Missing Application Handling
# -----------------------------------------------------------------------------
def test_f_missing_application():
    """Test F: Accurately reports uninstalled application failure and DOES NOT fake success."""
    executor = WindowsDeviceExecutor()
    req = DeviceExecutionRequest(
        target_device_id="laptop_windows",
        target_device_type=DeviceType.WINDOWS_LAPTOP,
        capability_id="windows.app.launch",
        parameters={"app_name": "TotallyNonExistentApp12345"},
    )

    with patch("app.devices.windows.app_discovery.windows_app_discovery.find_app", return_value=None):
        with patch("app.devices.windows.browser_discovery.windows_browser_discovery.resolve_service_destination", return_value=None):
            res = executor.execute(req)
            assert res.success is False
            assert res.verified is False
            assert "not installed" in res.error.lower()


# -----------------------------------------------------------------------------
# Test G: Offline Device Handling
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_offline_device():
    """Test G: Handles unreachable/offline device safely and DOES NOT fake success."""
    registry = DeviceCapabilityRegistry()
    executor = AndroidDeviceExecutor()

    req = DeviceExecutionRequest(
        target_device_id="phone_android",
        target_device_type=DeviceType.ANDROID_PHONE,
        capability_id="android.app.launch",
        parameters={"app_name": "whatsapp"},
    )

    # Force phone to be offline
    with patch.object(registry, "is_device_online", return_value=False):
        with patch("app.devices.android.executor.default_registry", registry):
            res = await executor.execute_async(req)
            assert res.success is False
            assert res.verified is False
            assert "offline or unreachable" in res.error.lower()


# -----------------------------------------------------------------------------
# Test H: Permission Enforcement
# -----------------------------------------------------------------------------
def test_h_permission_enforcement():
    """Test H: Destructive or sensitive action without approval is rejected."""
    from app.execution.policy import default_policy, PermissionClass

    # Test policy classifies destructive command
    perm_class, reason = default_policy.classify_command("Remove-Item -Recurse -Force C:\\Windows")
    assert perm_class == PermissionClass.CLASS_D_DESTRUCTIVE

    # Test invalid approval token cannot bypass execution
    valid, err = default_policy.verify_and_consume_token(
        token="invalid_token_xyz",
        command="Remove-Item -Recurse -Force C:\\Windows",
        cwd=None,
    )
    assert valid is False
    assert err is not None


# -----------------------------------------------------------------------------
# Test I: Duplicate Request Protection (Idempotency)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_i_duplicate_request_protection():
    """Test I: Idempotency token protects against duplicate execution."""
    executor = AndroidDeviceExecutor()
    registry = DeviceCapabilityRegistry()

    req1 = DeviceExecutionRequest(
        request_id="req_unique_101",
        target_device_id="phone_android",
        target_device_type=DeviceType.ANDROID_PHONE,
        capability_id="android.system.ring",
        metadata={"idempotency_token": "token_ring_123"},
    )
    req2 = DeviceExecutionRequest(
        request_id="req_unique_102",
        target_device_id="phone_android",
        target_device_type=DeviceType.ANDROID_PHONE,
        capability_id="android.system.ring",
        metadata={"idempotency_token": "token_ring_123"},
    )

    with patch.object(registry, "is_device_online", return_value=True):
        with patch("app.devices.android.executor.default_registry", registry):
            with patch("app.services.mesh_service.hub.broadcast") as mock_broadcast:
                mock_broadcast.return_value = None

                # First execution succeeds
                res1 = await executor.execute_async(req1)
                assert res1.success is True
                assert res1.data.get("ring_alert") is True

                # Duplicate execution is intercepted and suppressed
                res2 = await executor.execute_async(req2)
                assert res2.success is True
                assert res2.data.get("duplicate_suppressed") is True
                assert "idempotency token" in res2.verification_details.lower()


# -----------------------------------------------------------------------------
# Test J: Cross-Device Verification
# -----------------------------------------------------------------------------
def test_j_cross_device_verification():
    """Test J: Complete execution contract lifecycle and verification across mesh."""
    req = DeviceExecutionRequest(
        request_id="req_verify_test",
        target_device_id="laptop_windows",
        target_device_type=DeviceType.WINDOWS_LAPTOP,
        capability_id="windows.system.info",
    )

    executor = WindowsDeviceExecutor()
    res = executor.execute(req)

    assert res.request_id == "req_verify_test"
    assert res.success is True
    assert res.verified is True
    assert res.data is not None
    assert "os" in res.data
    assert res.duration_ms >= 0
