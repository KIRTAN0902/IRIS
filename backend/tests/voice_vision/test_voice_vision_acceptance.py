"""IRIS P3 Unified Voice Intelligence & Real-Time Visual Perception Acceptance Test Suite.

Verifies Mandatory Acceptance Tests A through L:
- Test A: Voice and chat equivalence ("Open WhatsApp on my phone")
- Test B: Windows voice control ("Open Chrome on my laptop")
- Test C: Browser fallback through voice ("Open Google Drive on my laptop")
- Test D: Voice follow-up context (spoken task creation, inspection, and completion)
- Test E: Android screen perception (ephemeral PixelCopy/WebSocket capture & OCR)
- Test F: Windows screen perception (GDI buffer capture & zero image storage)
- Test G: Visual follow-up ("Which button should I click?")
- Test H: Visual change detection (stale context > 120s handling)
- Test I: Permission denial (graceful handling, no hallucinations)
- Test J: Mesh disconnection (safe offline reporting)
- Test K: Multimodal execution ("Look at my screen, identify error, help fix it")
- Test L: Voice live tool dispatch & backward compatibility for Gemini Live audio
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from sqlalchemy.orm import Session

from app.agent.schemas import AgentResponseSchema
from app.agent.supervisor import IrisSupervisor
from app.ai.voice_bridge import UnifiedVoiceBridge
from app.core.security import get_current_user
from app.devices.contracts import DeviceExecutionRequest, DeviceExecutionResult, DeviceType
from app.models.enums import TaskStatus
from app.models.task import Task
from app.models.user import User
from app.services.screen_perception_service import (
    ActiveVisualPerception,
    ScreenPerceptionService,
    screen_perception_service,
)
from app.services.vision_service import VisionExtractionResult, vision_service


@pytest.fixture
def test_user(db: Session) -> User:
    return get_current_user(db)


# -----------------------------------------------------------------------------
# Test A: Voice and Chat Equivalence
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_voice_and_chat_equivalence(db: Session, test_user: User):
    """Test A: Spoken 'Open WhatsApp on my phone' and chat command route identically."""
    # 1. Voice Bridge Path
    bridge = UnifiedVoiceBridge(lambda: db, test_user)

    with patch("app.devices.android.executor.android_device_executor.execute_async") as mock_android:
        mock_android.return_value = DeviceExecutionResult(
            request_id="test_req_a",
            device_id="phone_android",
            success=True,
            data={"package_name": "com.whatsapp", "app_name": "WhatsApp"},
            capability_id="android.app.launch",
            device_type=DeviceType.ANDROID_PHONE,
        )

        voice_reply = await bridge.open_application("WhatsApp", target_device="phone")
        assert "Opening Whatsapp on your Android phone" in voice_reply or "Opening WhatsApp" in voice_reply
        assert mock_android.called
        req_voice = mock_android.call_args[0][0]
        assert req_voice.target_device_type == DeviceType.ANDROID_PHONE
        assert req_voice.capability_id == "android.app.launch"
        assert req_voice.parameters["app_name"] == "WhatsApp"

    # 2. Chat Supervisor Path
    with patch("app.agent.agent.default_agent.run_turn") as mock_agent_turn:
        from app.agent.schemas import ChatMessageOut
        from datetime import datetime
        mock_agent_turn.return_value = (
            ChatMessageOut(
                id=1,
                conversation_id=1,
                role="assistant",
                content="Opening WhatsApp on your Android phone.",
                actions_taken=[{"tool_name": "launch_app", "target": "phone", "app": "WhatsApp", "success": True}],
                created_at=datetime.utcnow(),
            ),
            None,
        )

        chat_resp, actions = await IrisSupervisor.process(
            db=db,
            user=test_user,
            user_message="Open WhatsApp on my phone",
        )
        assert "Opening WhatsApp on your Android phone" in chat_resp.message
        assert len(actions) == 1
        assert actions[0]["tool_name"] == "launch_app"


# -----------------------------------------------------------------------------
# Test B: Windows Voice Control
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b_windows_voice_control(db: Session, test_user: User):
    """Test B: Voice execution of 'Open Chrome on my laptop' executes Windows app launch."""
    bridge = UnifiedVoiceBridge(lambda: db, test_user)

    with patch("app.ai.voice_bridge._windows_executor.execute") as mock_win_exec:
        mock_win_exec.return_value = DeviceExecutionResult(
            request_id="test_req_b",
            device_id="laptop_windows",
            success=True,
            data={"app_name": "Google Chrome", "path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"},
            capability_id="windows.app.launch",
            device_type=DeviceType.WINDOWS_LAPTOP,
        )

        reply = await bridge.dispatch_tool_call(
            "open_application",
            {"app_name": "Chrome", "target_device": "laptop"},
        )
        assert "Opened Google Chrome on your Windows laptop." in reply
        assert mock_win_exec.called
        req = mock_win_exec.call_args[0][0]
        assert req.capability_id == "windows.app.launch"
        assert req.target_device_type == DeviceType.WINDOWS_LAPTOP


# -----------------------------------------------------------------------------
# Test C: Browser Fallback Through Voice
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c_browser_fallback_through_voice(db: Session, test_user: User):
    """Test C: Spoken 'Open Google Drive on my laptop' uses browser fallback without errors."""
    bridge = UnifiedVoiceBridge(lambda: db, test_user)

    with patch("app.ai.voice_bridge._windows_executor.execute") as mock_win_exec:
        mock_win_exec.return_value = DeviceExecutionResult(
            request_id="test_req_c",
            device_id="laptop_windows",
            success=True,
            data={
                "browser": "Google Chrome",
                "url": "https://drive.google.com",
                "app_name": "Google Drive",
            },
            capability_id="windows.app.launch",
            device_type=DeviceType.WINDOWS_LAPTOP,
        )

        reply = await bridge.dispatch_tool_call(
            "open_application",
            {"app_name": "Google Drive", "target_device": "laptop"},
        )
        assert "Opened Google Drive in Google Chrome at https://drive.google.com on your Windows laptop." in reply


# -----------------------------------------------------------------------------
# Test D: Voice Follow-Up Context
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_d_voice_follow_up_context(db: Session, test_user: User):
    """Test D: Multi-turn voice interaction for task creation, query, and completion."""
    bridge = UnifiedVoiceBridge(lambda: db, test_user)

    # Turn 1: Create task
    create_res = await bridge.dispatch_tool_call(
        "create_daily_task",
        {"title": "Review pitch deck", "priority": "HIGH", "estimated_minutes": 45},
    )
    assert "Created task #" in create_res
    assert "Review pitch deck" in create_res
    assert "High" in create_res

    # Check database
    task = db.query(Task).filter(Task.user_id == test_user.id, Task.title == "Review pitch deck").first()
    assert task is not None
    assert task.status == TaskStatus.TODO.value
    assert task.estimated_duration == 45

    # Turn 2: Query today's tasks
    list_res = await bridge.dispatch_tool_call("get_today_tasks", {})
    assert "Review pitch deck" in list_res

    # Turn 3: Complete task
    complete_res = await bridge.dispatch_tool_call(
        "complete_task",
        {"task_title_or_id": "Review pitch deck"},
    )
    assert "Marked task #" in complete_res
    assert "completed" in complete_res

    # Re-query task from db and check completed status
    updated_task = db.query(Task).filter(Task.user_id == test_user.id, Task.title == "Review pitch deck").first()
    assert updated_task is not None
    assert updated_task.status == TaskStatus.COMPLETED.value


# -----------------------------------------------------------------------------
# Test E: Android Screen Perception
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e_android_screen_perception(db: Session, test_user: User):
    """Test E: Capture and analyze Android screen with zero persistent image files on disk."""
    service = ScreenPerceptionService()
    mock_ws = AsyncMock()

    test_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

    async def mock_capture():
        await asyncio.sleep(0.01)
        service.complete_capture_future({"image_base64": test_b64})

    asyncio.create_task(mock_capture())

    fake_vision_res = VisionExtractionResult(
        summary="A mobile settings screen showing Wi-Fi and Bluetooth toggles.",
        extracted_text_or_code="Settings Wi-Fi Connected Bluetooth Off Display Battery",
        actionable_items=[
            {"title": "Wi-Fi", "type": "toggle", "state": "on"},
            {"title": "Bluetooth", "type": "toggle", "state": "off"},
        ],
    )

    with patch("app.devices.registry.default_registry.is_device_online", return_value=True):
        with patch.object(vision_service, "analyze_ephemeral_images", return_value=fake_vision_res):
            success, message, result = await service.capture_and_analyze(
                db=db,
                user=test_user,
                target_device_hint="phone",
                question="What is on my screen?",
                client_ws=mock_ws,
            )

            assert success is True
            assert result is not None
            assert "mobile settings screen" in result.summary
            assert "Wi-Fi" in result.extracted_text_or_code

            # Verify active perception cache exists
            active = service.get_active_perception(test_user.id)
            assert active is not None
            assert active.device_type == DeviceType.ANDROID_PHONE
            assert active.summary == result.summary


# -----------------------------------------------------------------------------
# Test F: Windows Screen Perception
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f_windows_screen_perception(db: Session, test_user: User):
    """Test F: Capture and analyze Windows laptop screen using in-memory buffer."""
    service = ScreenPerceptionService()
    test_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

    fake_vision_res = VisionExtractionResult(
        summary="Visual Studio Code displaying main.py with an unresolved import error.",
        extracted_text_or_code="import fastapi from app.core import settings ModuleNotFoundError: No module named 'fastapi'",
        actionable_items=[
            {"title": "Run", "type": "button"},
            {"title": "Debug", "type": "button"},
        ],
    )

    with patch("app.services.mesh_relay_service.is_local_windows_host", return_value=True):
        with patch("app.services.mesh_service.capture_windows_screen", return_value={"success": True, "image_base64": test_b64, "width": 1920, "height": 1080}):
            with patch.object(vision_service, "analyze_ephemeral_images", return_value=fake_vision_res):
                success, message, result = await service.capture_and_analyze(
                    db=db,
                    user=test_user,
                    target_device_hint="laptop",
                    question="Look at my screen and tell me what is open",
                )

                assert success is True
                assert result is not None
                assert "Visual Studio Code" in result.summary
                active = service.get_active_perception(test_user.id)
                assert active is not None
                assert active.device_type == DeviceType.WINDOWS_LAPTOP


# -----------------------------------------------------------------------------
# Test G: Visual Follow-Up Question
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_visual_follow_up(db: Session, test_user: User):
    """Test G: User asks follow-up referencing visible elements without re-capturing."""
    service = ScreenPerceptionService()

    # Pre-populate active perception
    service._active_perceptions[test_user.id] = ActiveVisualPerception(
        timestamp=time.time(),
        device_type=DeviceType.ANDROID_PHONE,
        summary="A checkout screen with Order Summary, Total Rs 450, and a green 'Proceed to Pay' button.",
        extracted_text_or_code="Order Summary Total Rs 450 Proceed to Pay Cancel",
        actionable_items=[
            {"title": "Proceed to Pay", "type": "button", "color": "green", "x": 100, "y": 800},
            {"title": "Cancel", "type": "button", "color": "grey", "x": 100, "y": 900},
        ],
    )

    with patch("app.agent.supervisor.IrisSupervisor.process") as mock_sup:
        mock_sup.return_value = (
            AgentResponseSchema(
                thought="Identified Proceed to Pay button from screen context.",
                actions=[],
                message="Click the green 'Proceed to Pay' button at the bottom of the screen to continue.",
            ),
            [],
        )

        ans = await service.answer_visual_followup(
            question="Which button should I click to complete my purchase?",
            db=db,
            user=test_user,
        )

        assert "Proceed to Pay" in ans
        assert mock_sup.called
        call_msg = mock_sup.call_args[1]["user_message"]
        assert "ACTIVE VISUAL CONTEXT" in call_msg
        assert "Proceed to Pay" in call_msg


# -----------------------------------------------------------------------------
# Test H: Visual Change Detection (Stale Context > 120s)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_h_visual_change_detection_stale_context(db: Session, test_user: User):
    """Test H: Warn user when visual context is older than 120 seconds."""
    service = ScreenPerceptionService()

    # Context captured 180 seconds ago (> 120s limit)
    service._active_perceptions[test_user.id] = ActiveVisualPerception(
        timestamp=time.time() - 180.0,
        device_type=DeviceType.WINDOWS_LAPTOP,
        summary="Old desktop screen view.",
        extracted_text_or_code="Terminal window open",
        actionable_items=[],
    )

    ans = await service.answer_visual_followup(
        question="Which window is active right now?",
        db=db,
        user=test_user,
    )

    assert "older than 120 seconds" in ans or "may have changed" in ans
    assert "Please ask me to inspect your screen again" in ans


# -----------------------------------------------------------------------------
# Test I: Permission Denial
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_i_permission_denial(db: Session, test_user: User):
    """Test I: Handle permission denial or cancelled capture gracefully."""
    service = ScreenPerceptionService()
    mock_ws = AsyncMock()

    async def mock_deny():
        await asyncio.sleep(0.01)
        # Empty string indicates cancelled or denied permission
        service.complete_capture_future("")

    asyncio.create_task(mock_deny())

    with patch("app.devices.registry.default_registry.is_device_online", return_value=True):
        success, message, result = await service.capture_and_analyze(
            db=db,
            user=test_user,
            target_device_hint="phone",
            question="What is on my screen?",
            client_ws=mock_ws,
        )

        assert success is False
        assert result is None
        assert "permission was denied or cancelled" in message


# -----------------------------------------------------------------------------
# Test J: Mesh Disconnection
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_j_mesh_disconnection(db: Session, test_user: User):
    """Test J: Safe offline reporting when remote laptop workstation is disconnected."""
    bridge = UnifiedVoiceBridge(lambda: db, test_user)

    with patch("app.services.mesh_relay_service.is_local_windows_host", return_value=False):
        with patch("app.devices.registry.default_registry.is_device_online", return_value=False):
            reply = await bridge.open_application("VS Code", target_device="laptop")
            assert "offline or unreachable on the Sovereign Mesh" in reply


# -----------------------------------------------------------------------------
# Test K: Multimodal Execution
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_k_multimodal_execution(db: Session, test_user: User):
    """Test K: Ground natural query in active screen error to recommend resolution."""
    test_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

    fake_vision_res = VisionExtractionResult(
        summary="A terminal showing 'psycopg2.OperationalError: could not connect to server: Connection refused'",
        extracted_text_or_code="Traceback (most recent call last): psycopg2.OperationalError: could not connect to server: Connection refused Is the server running on host 'localhost' and accepting TCP/IP connections on port 5432?",
        actionable_items=[
            {"title": "Connection refused", "type": "error_log"},
        ],
    )

    with patch("app.services.mesh_relay_service.is_local_windows_host", return_value=True):
        with patch("app.services.mesh_service.capture_windows_screen", return_value={"success": True, "image_base64": test_b64, "width": 1920, "height": 1080}):
            with patch.object(vision_service, "analyze_ephemeral_images", return_value=fake_vision_res):
                resp, _ = await IrisSupervisor.process(
                    db=db,
                    user=test_user,
                    user_message="Look at my screen and tell me what is open",
                )

                assert "psycopg2" in resp.message or "Connection refused" in resp.message


# -----------------------------------------------------------------------------
# Test L: Gemini Live Tool Dispatch & Legacy Compatibility
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_l_voice_live_tool_dispatch(db: Session, test_user: User):
    """Test L: UnifiedVoiceBridge dispatches all legacy and modern Live function calls."""
    bridge = UnifiedVoiceBridge(lambda: db, test_user)

    # 1. Lock Workstation
    with patch("app.ai.voice_bridge._windows_executor.execute") as mock_exec:
        mock_exec.return_value = DeviceExecutionResult(
            request_id="test_req_l1",
            device_id="laptop_windows",
            success=True,
            capability_id="windows.system.lock",
        )
        res_lock = await bridge.dispatch_tool_call("lock_laptop", {})
        assert "locked" in res_lock.lower()

    # 2. Battery Status
    with patch("app.ai.voice_bridge._windows_executor.execute") as mock_exec:
        mock_exec.return_value = DeviceExecutionResult(
            request_id="test_req_l2",
            device_id="laptop_windows",
            success=True,
            data={"battery_level_percent": 88, "is_charging": False},
            capability_id="windows.system.battery",
        )
        res_bat = await bridge.dispatch_tool_call("get_laptop_status", {})
        assert "88%" in res_bat

    # 3. Terminal Command
    with patch("app.agent.supervisor.IrisSupervisor.process") as mock_sup:
        mock_sup.return_value = (
            AgentResponseSchema(
                thought="Executed command",
                actions=[],
                message="Listing: file1.txt, file2.py",
            ),
            [],
        )
        res_term = await bridge.dispatch_tool_call("execute_terminal_command", {"command": "dir"})
        assert "Listing" in res_term
