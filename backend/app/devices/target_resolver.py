"""IRIS Dynamic Device Target Resolver.

Resolves the intended target device (Windows laptop workstation vs Android phone)
and specific capability action from natural user phrasing, OS state, and device presence.

Follows the P2 principle:
"IRIS should discover device capabilities rather than depend on hardcoded device-command mappings."
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app.devices.contracts import DeviceType
from app.devices.registry import DeviceCapabilityRegistry, default_registry
from app.devices.windows.browser_discovery import WindowsBrowserDiscovery

logger = logging.getLogger(__name__)


class TargetResolutionResult(BaseModel):
    """Result of analyzing user intent and target hardware device."""

    target_device: DeviceType = Field(..., description="Resolved target hardware device")
    target_device_id: str = Field(..., description="Target device ID in Sovereign Mesh")
    action: str = Field(..., description="Resolved action ('launch_app', 'open_url', 'lock_workstation', 'battery_status', 'ring_phone', etc.)")
    cleaned_query: str = Field(..., description="Target app, destination, or command without device prefixes/suffixes")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reasoning: str = Field(..., description="Explanation of why this target device and capability was selected")
    fallback_url: str | None = Field(default=None, description="Resolved web URL fallback if target is an online service")
    needs_clarification: bool = Field(default=False)


class DeviceTargetResolver:
    """Intelligently routes device execution requests based on explicit cues, app availability, and context."""

    # Regex patterns for explicit target cues
    LAPTOP_PATTERNS = [
        re.compile(r"\b(?:on|in|to|at)\s+(?:my\s+)?(?:laptop|pc|computer|desktop|workstation|windows|machine)\b", re.IGNORECASE),
        re.compile(r"\b(?:laptop|pc|computer|desktop|workstation)\s+(?:app|browser|screen|battery)\b", re.IGNORECASE),
    ]

    PHONE_PATTERNS = [
        re.compile(r"\b(?:on|in|to|at)\s+(?:my\s+)?(?:phone|mobile|android|realme|handheld|cellphone|cell)\b", re.IGNORECASE),
        re.compile(r"\b(?:phone|mobile|android|realme)\s+(?:app|screen|battery)\b", re.IGNORECASE),
    ]

    # Device exclusive commands
    LOCK_PATTERNS = re.compile(r"\b(?:lock|secure)\s+(?:my\s+)?(?:laptop|workstation|pc|computer|desktop|screen|session)\b", re.IGNORECASE)
    RING_PATTERNS = re.compile(r"\b(?:ring|find|locate|buzz)\s+(?:my\s+)?(?:phone|mobile|cell|realme)\b", re.IGNORECASE)
    BATTERY_PATTERNS = re.compile(r"\b(?:battery|charge|power\s+level|battery\s+percentage|battery\s+level)\b", re.IGNORECASE)

    # Mobile-heavy applications (primarily mobile apps)
    MOBILE_NATIVE_APPS = {
        "whatsapp",
        "phonepe",
        "gpay",
        "google pay",
        "paytm",
        "cred",
        "swiggy",
        "zomato",
        "zepto",
        "blinkit",
        "uber",
        "ola",
        "rapido",
        "instagram",
        "camera",
        "settings",
    }

    # Workstation-heavy applications (primarily desktop development / productivity tools)
    WORKSTATION_NATIVE_APPS = {
        "vscode",
        "vs code",
        "visual studio code",
        "code",
        "terminal",
        "powershell",
        "cmd",
        "command prompt",
        "explorer",
        "file explorer",
        "antigravity",
        "antigravity ide",
        "antigravity cli",
        "agy",
        "notepad",
        "pycharm",
        "git",
        "taskmgr",
        "task manager",
    }

    def __init__(self, registry: DeviceCapabilityRegistry | None = None) -> None:
        self.registry = registry or default_registry

    def resolve(
        self,
        user_prompt: str,
        client_device: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> TargetResolutionResult:
        """Resolves target device, action, entity query, and confidence from user phrasing."""
        clean_text = user_prompt.strip()
        lower_text = clean_text.lower()

        # 1. Check for Workstation Lock
        if self.LOCK_PATTERNS.search(lower_text) or lower_text in ["lock pc", "lock laptop", "lock workstation", "lock computer"]:
            return TargetResolutionResult(
                target_device=DeviceType.WINDOWS_LAPTOP,
                target_device_id="laptop_windows",
                action="lock_workstation",
                cleaned_query="lock workstation",
                confidence=1.0,
                reasoning="Explicit workstation lock command directed to Windows desktop.",
            )

        # 2. Check for Phone Ring (Find My Phone)
        if self.RING_PATTERNS.search(lower_text) or lower_text in ["ring phone", "ring my phone", "find my phone", "buzz my phone"]:
            return TargetResolutionResult(
                target_device=DeviceType.ANDROID_PHONE,
                target_device_id="phone_android",
                action="ring_phone",
                cleaned_query="ring phone",
                confidence=1.0,
                reasoning="Find My Phone command directed to Android phone companion.",
            )

        # 3. Check for Battery Queries
        if self.BATTERY_PATTERNS.search(lower_text):
            has_phone = any(p.search(lower_text) for p in self.PHONE_PATTERNS) or "phone" in lower_text or "mobile" in lower_text
            has_laptop = any(p.search(lower_text) for p in self.LAPTOP_PATTERNS) or "laptop" in lower_text or "pc" in lower_text or "workstation" in lower_text

            if has_phone and not has_laptop:
                return TargetResolutionResult(
                    target_device=DeviceType.ANDROID_PHONE,
                    target_device_id="phone_android",
                    action="battery_status",
                    cleaned_query="battery",
                    confidence=0.98,
                    reasoning="Explicit request for Android phone battery level.",
                )
            if has_laptop and not has_phone:
                return TargetResolutionResult(
                    target_device=DeviceType.WINDOWS_LAPTOP,
                    target_device_id="laptop_windows",
                    action="battery_status",
                    cleaned_query="battery",
                    confidence=0.98,
                    reasoning="Explicit request for Windows laptop battery telemetry.",
                )
            # Both or unspecified battery request
            default_target = DeviceType.WINDOWS_LAPTOP if client_device != "phone" else DeviceType.ANDROID_PHONE
            target_id = "laptop_windows" if default_target == DeviceType.WINDOWS_LAPTOP else "phone_android"
            return TargetResolutionResult(
                target_device=default_target,
                target_device_id=target_id,
                action="battery_status",
                cleaned_query="battery",
                confidence=0.85,
                reasoning=f"Battery telemetry request default to active workstation {default_target.value}.",
            )

        # 4. Check for Explicit Device Cues in General Text
        explicit_laptop = any(p.search(lower_text) for p in self.LAPTOP_PATTERNS)
        explicit_phone = any(p.search(lower_text) for p in self.PHONE_PATTERNS)

        # Extract app or destination entity
        cleaned_entity = self._extract_clean_entity(clean_text)
        lower_entity = cleaned_entity.lower()

        # Check if destination resolves to a web service URL
        service_url = WindowsBrowserDiscovery.resolve_service_destination(lower_entity)

        # Scenario A: Explicit Laptop Target
        if explicit_laptop and not explicit_phone:
            return TargetResolutionResult(
                target_device=DeviceType.WINDOWS_LAPTOP,
                target_device_id="laptop_windows",
                action="launch_app",
                cleaned_query=cleaned_entity,
                confidence=0.98,
                reasoning=f"Explicit target 'laptop' specified by user for '{cleaned_entity}'.",
                fallback_url=service_url,
            )

        # Scenario B: Explicit Phone Target
        if explicit_phone and not explicit_laptop:
            return TargetResolutionResult(
                target_device=DeviceType.ANDROID_PHONE,
                target_device_id="phone_android",
                action="launch_app",
                cleaned_query=cleaned_entity,
                confidence=0.98,
                reasoning=f"Explicit target 'phone' specified by user for '{cleaned_entity}'.",
                fallback_url=service_url,
            )

        # Scenario C: Implicit Target — Dynamic Capability & Affinity Matching
        # 1. Check if application has strong mobile affinity (e.g. WhatsApp, PhonePe, GPay, Camera)
        if lower_entity in self.MOBILE_NATIVE_APPS:
            return TargetResolutionResult(
                target_device=DeviceType.ANDROID_PHONE,
                target_device_id="phone_android",
                action="launch_app",
                cleaned_query=cleaned_entity,
                confidence=0.90,
                reasoning=f"Application '{cleaned_entity}' has primary mobile affinity on Android companion.",
                fallback_url=service_url,
            )

        # 2. Check if application has strong workstation affinity (e.g. VS Code, Terminal, Antigravity)
        if lower_entity in self.WORKSTATION_NATIVE_APPS:
            return TargetResolutionResult(
                target_device=DeviceType.WINDOWS_LAPTOP,
                target_device_id="laptop_windows",
                action="launch_app",
                cleaned_query=cleaned_entity,
                confidence=0.92,
                reasoning=f"Application '{cleaned_entity}' is a native workstation tool on Windows.",
                fallback_url=service_url,
            )

        # 3. Check if installed on Windows via dynamic discovery
        if self.registry.is_app_installed(DeviceType.WINDOWS_LAPTOP, lower_entity):
            return TargetResolutionResult(
                target_device=DeviceType.WINDOWS_LAPTOP,
                target_device_id="laptop_windows",
                action="launch_app",
                cleaned_query=cleaned_entity,
                confidence=0.88,
                reasoning=f"Discovered '{cleaned_entity}' installed on Windows desktop.",
                fallback_url=service_url,
            )

        # 4. Check if known online service (e.g. Google Drive, Google Docs, Notion, Figma)
        if service_url:
            return TargetResolutionResult(
                target_device=DeviceType.WINDOWS_LAPTOP,
                target_device_id="laptop_windows",
                action="launch_app",
                cleaned_query=cleaned_entity,
                confidence=0.85,
                reasoning=f"'{cleaned_entity}' is an online service resolvable on Windows via browser fallback.",
                fallback_url=service_url,
            )

        # 5. Default to Windows Workstation or Active Device
        default_target = DeviceType.WINDOWS_LAPTOP if client_device != "phone" else DeviceType.ANDROID_PHONE
        target_id = "laptop_windows" if default_target == DeviceType.WINDOWS_LAPTOP else "phone_android"
        return TargetResolutionResult(
            target_device=default_target,
            target_device_id=target_id,
            action="launch_app",
            cleaned_query=cleaned_entity,
            confidence=0.75,
            reasoning=f"Defaulting execution of '{cleaned_entity}' to primary workstation {default_target.value}.",
            fallback_url=service_url,
        )

    def _extract_clean_entity(self, text: str) -> str:
        """Strips prefixes ('open', 'launch', 'start') and target device suffixes."""
        clean = text.strip()

        # Remove leading trigger verbs
        clean = re.sub(r"^(?:please\s+)?(?:open|launch|start|run|access|show|navigate\s+to|goto)\s+", "", clean, flags=re.IGNORECASE).strip()

        # Remove device suffixes like "on my phone", "on my laptop", "on laptop", "on phone"
        clean = re.sub(r"\s+(?:on|in|at)\s+(?:my\s+)?(?:laptop|pc|computer|desktop|windows|phone|mobile|android|realme)\s*$", "", clean, flags=re.IGNORECASE).strip()

        # Remove quotes
        clean = clean.strip("\"'`;")
        return clean


# Global resolver instance
default_target_resolver = DeviceTargetResolver()
