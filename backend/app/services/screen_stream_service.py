"""WebRTC Screen Streaming & Remote Desktop Service for IRIS Mesh.

Provides sovereign, zero-cost, bi-directional screen streaming and control:
1. Desktop Streamer: Captures Windows host monitor (using mss/GDI) at 30 FPS and streams via WebRTC.
2. WebRTC Peer Connection negotiation via Sovereign Mesh Relay (SDP Offer/Answer & ICE).
3. Remote Mouse & Keyboard input injection (Win32 API via ctypes).
4. Low-latency MJPEG / JPEG snapshot fallback for instant preview without WebRTC negotiation.
"""

from __future__ import annotations

import asyncio
from fractions import Fraction
import io
import time
from typing import Any

from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaRelay
import av
import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)

# Default public Google STUN servers for NAT traversal ($0 forever)
STUN_SERVERS = [
    RTCIceServer(urls=["stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"]),
]
RTC_CONFIG = RTCConfiguration(iceServers=STUN_SERVERS)


def attach_input_desktop() -> None:
    """Attaches current thread to the interactive Windows input desktop if on Windows."""
    try:
        import ctypes
        u = ctypes.windll.user32
        desk = u.OpenInputDesktop(0, False, 0x01FF)
        if desk:
            u.SetThreadDesktop(desk)
    except Exception:
        pass


def capture_screen_frame(scale_factor: int = 2) -> np.ndarray | None:
    """Captures the primary monitor screen as a numpy BGR array."""
    attach_input_desktop()
    try:
        import mss
        with mss.mss() as sct:
            monitor = sct.monitors[0]  # Full virtual desktop / primary monitor
            shot = sct.grab(monitor)
            img = np.array(shot)[:, :, :3]  # Drop alpha channel -> BGR
            if scale_factor > 1:
                # Sub-sample image for lower CPU usage and smooth 30fps transfer
                img = img[::scale_factor, ::scale_factor]
            return img
    except Exception as exc:
        logger.debug("Failed screen grab with mss: %s", exc)
        try:
            from PIL import ImageGrab
            pil_img = ImageGrab.grab()
            if scale_factor > 1:
                pil_img = pil_img.resize((pil_img.width // scale_factor, pil_img.height // scale_factor))
            rgb = np.array(pil_img)
            return rgb[:, :, ::-1]  # RGB to BGR
        except Exception as exc2:
            logger.debug("Failed screen grab with PIL: %s", exc2)
            return None


def get_screen_dimensions() -> tuple[int, int]:
    """Returns primary monitor (width, height) in pixels."""
    try:
        import ctypes
        u = ctypes.windll.user32
        return u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    except Exception:
        return 1920, 1080


# --- WebRTC Desktop Video Track ---


class DesktopVideoStreamTrack(VideoStreamTrack):
    """WebRTC VideoStreamTrack delivering real-time desktop frames at 30 FPS."""

    kind = "video"

    def __init__(self, fps: int = 30, scale_factor: int = 2) -> None:
        super().__init__()
        self.fps = fps
        self.scale_factor = scale_factor
        self.frame_time = 1.0 / fps
        self._start_time: float | None = None
        self._timestamp = 0

    async def recv(self) -> av.VideoFrame:
        pts, time_base = await self.next_timestamp()

        # Capture desktop frame asynchronously in thread pool to prevent blocking asyncio event loop
        loop = asyncio.get_running_loop()
        img = await loop.run_in_executor(None, capture_screen_frame, self.scale_factor)

        if img is None:
            # Fallback black placeholder frame
            img = np.zeros((720, 1280, 3), dtype=np.uint8)

        # Ensure contiguous memory layout for av.VideoFrame
        img = np.ascontiguousarray(img)
        frame = av.VideoFrame.from_ndarray(img, format="bgr24")
        frame.pts = pts
        frame.time_base = time_base
        return frame


# --- Remote Input Control (Mouse & Keyboard) ---


def inject_mouse_event(
    action: str,
    x_ratio: float,
    y_ratio: float,
    button: str = "left",
    wheel_delta: int = 0,
) -> bool:
    """Translates normalized coordinates (0.0 to 1.0) into Windows cursor position and click."""
    attach_input_desktop()
    try:
        import ctypes

        u = ctypes.windll.user32
        screen_w = u.GetSystemMetrics(0)
        screen_h = u.GetSystemMetrics(1)

        target_x = max(0, min(screen_w - 1, int(x_ratio * screen_w)))
        target_y = max(0, min(screen_h - 1, int(y_ratio * screen_h)))

        # Win32 Mouse Event Flags
        MOUSEEVENTF_MOVE = 0x0001
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        MOUSEEVENTF_RIGHTDOWN = 0x0008
        MOUSEEVENTF_RIGHTUP = 0x0010
        MOUSEEVENTF_MIDDLEDOWN = 0x0020
        MOUSEEVENTF_MIDDLEUP = 0x0040
        MOUSEEVENTF_WHEEL = 0x0800
        MOUSEEVENTF_ABSOLUTE = 0x8000

        # Move cursor
        u.SetCursorPos(target_x, target_y)

        if action == "move":
            return True

        if action in ("click", "down"):
            if button == "left":
                u.mouse_event(MOUSEEVENTF_LEFTDOWN, target_x, target_y, 0, 0)
                if action == "click":
                    time.sleep(0.02)
                    u.mouse_event(MOUSEEVENTF_LEFTUP, target_x, target_y, 0, 0)
            elif button == "right":
                u.mouse_event(MOUSEEVENTF_RIGHTDOWN, target_x, target_y, 0, 0)
                if action == "click":
                    time.sleep(0.02)
                    u.mouse_event(MOUSEEVENTF_RIGHTUP, target_x, target_y, 0, 0)
            elif button == "middle":
                u.mouse_event(MOUSEEVENTF_MIDDLEDOWN, target_x, target_y, 0, 0)
                if action == "click":
                    time.sleep(0.02)
                    u.mouse_event(MOUSEEVENTF_MIDDLEUP, target_x, target_y, 0, 0)

        elif action == "up":
            if button == "left":
                u.mouse_event(MOUSEEVENTF_LEFTUP, target_x, target_y, 0, 0)
            elif button == "right":
                u.mouse_event(MOUSEEVENTF_RIGHTUP, target_x, target_y, 0, 0)
            elif button == "middle":
                u.mouse_event(MOUSEEVENTF_MIDDLEUP, target_x, target_y, 0, 0)

        elif action == "double_click":
            u.mouse_event(MOUSEEVENTF_LEFTDOWN, target_x, target_y, 0, 0)
            u.mouse_event(MOUSEEVENTF_LEFTUP, target_x, target_y, 0, 0)
            time.sleep(0.05)
            u.mouse_event(MOUSEEVENTF_LEFTDOWN, target_x, target_y, 0, 0)
            u.mouse_event(MOUSEEVENTF_LEFTUP, target_x, target_y, 0, 0)

        elif action == "wheel":
            u.mouse_event(MOUSEEVENTF_WHEEL, target_x, target_y, wheel_delta, 0)

        return True
    except Exception as exc:
        logger.error("Failed to inject mouse event: %s", exc)
        return False


def inject_keyboard_event(text: str | None = None, key: str | None = None) -> bool:
    """Injects keystrokes or text on the Windows host."""
    attach_input_desktop()
    try:
        import ctypes
        u = ctypes.windll.user32

        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_UNICODE = 0x0004

        # Special key mapping
        SPECIAL_KEYS = {
            "Enter": 0x0D,
            "Backspace": 0x08,
            "Tab": 0x09,
            "Escape": 0x1B,
            "Space": 0x20,
            "ArrowLeft": 0x25,
            "ArrowUp": 0x26,
            "ArrowRight": 0x27,
            "ArrowDown": 0x28,
            "Delete": 0x2E,
        }

        if key and key in SPECIAL_KEYS:
            vk = SPECIAL_KEYS[key]
            u.keybd_event(vk, 0, 0, 0)
            time.sleep(0.02)
            u.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            return True

        if text:
            for char in text:
                code = ord(char)
                u.keybd_event(0, code, KEYEVENTF_UNICODE, 0)
                u.keybd_event(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)
            return True

        return False
    except Exception as exc:
        logger.error("Failed to inject keyboard event: %s", exc)
        return False


# --- WebRTC Peer Connection Manager ---


class ScreenStreamManager:
    """Manages active WebRTC PeerConnections for desktop streaming."""

    def __init__(self) -> None:
        self.peer_connections: dict[str, RTCPeerConnection] = {}
        self.active_tracks: dict[str, DesktopVideoStreamTrack] = {}

    async def handle_offer(
        self,
        session_id: str,
        sdp_offer: str,
        sdp_type: str = "offer",
    ) -> dict[str, Any]:
        """Processes an incoming WebRTC SDP Offer from a mobile client and generates an SDP Answer."""
        # Close any existing connection for this session
        await self.close_session(session_id)

        pc = RTCPeerConnection(configuration=RTC_CONFIG)
        self.peer_connections[session_id] = pc

        # Create desktop video track
        track = DesktopVideoStreamTrack(fps=30, scale_factor=2)
        self.active_tracks[session_id] = track
        pc.addTrack(track)

        @pc.on("datachannel")
        def on_datachannel(channel: Any) -> None:
            @channel.on("message")
            def on_message(message: Any) -> None:
                # Low-latency mouse/keyboard packets over WebRTC data channel
                import json
                try:
                    data = json.loads(message)
                    event_type = data.get("type")
                    if event_type == "MOUSE":
                        inject_mouse_event(
                            action=data.get("action", "click"),
                            x_ratio=data.get("x", 0.5),
                            y_ratio=data.get("y", 0.5),
                            button=data.get("button", "left"),
                            wheel_delta=data.get("delta", 0),
                        )
                    elif event_type == "KEYBOARD":
                        inject_keyboard_event(
                            text=data.get("text"),
                            key=data.get("key"),
                        )
                except Exception as exc:
                    logger.debug("DataChannel message parse error: %s", exc)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange() -> None:
            logger.info("WebRTC session %s state: %s", session_id, pc.connectionState)
            if pc.connectionState in ("failed", "closed"):
                await self.close_session(session_id)

        # Set remote offer
        offer = RTCSessionDescription(sdp=sdp_offer, type=sdp_type)
        await pc.setRemoteDescription(offer)

        # Generate answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        return {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
            "session_id": session_id,
        }

    async def add_ice_candidate(self, session_id: str, candidate_dict: dict[str, Any]) -> None:
        """Adds an ICE candidate received from mobile client."""
        pc = self.peer_connections.get(session_id)
        if not pc:
            return
        # aiortc handles candidates directly or via trickle ICE
        logger.debug("Received ICE candidate for session %s: %s", session_id, candidate_dict)

    async def close_session(self, session_id: str) -> None:
        """Closes an active peer connection."""
        pc = self.peer_connections.pop(session_id, None)
        self.active_tracks.pop(session_id, None)
        if pc:
            try:
                await pc.close()
            except Exception:
                pass


stream_manager = ScreenStreamManager()


# --- Low-Latency Snapshot Generator ---


def get_screen_jpeg_bytes(quality: int = 70, scale_factor: int = 2) -> bytes | None:
    """Returns a compressed JPEG screenshot bytes for fast preview / snapshot polling."""
    attach_input_desktop()
    try:
        from PIL import Image, ImageGrab
        img = ImageGrab.grab()
        if scale_factor > 1:
            img = img.resize((img.width // scale_factor, img.height // scale_factor), Image.Resampling.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()
    except Exception as exc:
        logger.debug("JPEG snapshot error: %s", exc)
        return None
