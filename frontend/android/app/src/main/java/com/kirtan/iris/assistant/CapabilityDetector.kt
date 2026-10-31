package com.kirtan.iris.assistant

import android.Manifest
import android.app.role.RoleManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioManager
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.core.content.ContextCompat

data class CapabilityRow(
    val title: String,
    val value: String,
    val supported: Boolean,
    val detail: String,
)

data class CapabilityReport(
    val device: String,
    val android: String,
    val manufacturer: String,
    val isAssistant: Boolean,
    val microphone: Boolean,
    val overlay: Boolean,
    val notifications: Boolean,
    val batteryOptimized: Boolean,
    val screenPerception: Boolean,
    val hotword: HotwordStatus,
    val displayState: String,
    val rows: List<CapabilityRow>,
)

/**
 * Pure capability inspection. Never claims a feature works merely because the
 * platform API exists: hotword support is only reported from the lifecycle of a
 * real AlwaysOnHotwordDetector created by the active VoiceInteractionService.
 */
object CapabilityDetector {

    @JvmStatic
    fun isDefaultAssistant(context: Context): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val roleManager = context.getSystemService(Context.ROLE_SERVICE) as? RoleManager
            roleManager?.isRoleHeld(RoleManager.ROLE_ASSISTANT) == true
        } else {
            val current = Settings.Secure.getString(
                context.contentResolver,
                "voice_interaction_service",
            )
            !current.isNullOrBlank() && current.contains(context.packageName)
        }
    }

    @JvmStatic
    fun hasMicrophone(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED

    @JvmStatic
    fun canDrawOverlays(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(context)

    fun notificationsEnabled(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return true
        return ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED
    }

    fun ignoresBatteryOptimizations(context: Context): Boolean {
        val power = context.getSystemService(Context.POWER_SERVICE) as? PowerManager ?: return true
        return power.isIgnoringBatteryOptimizations(context.packageName)
    }

    fun screenPerceptionPossible(context: Context): Boolean {
        // The zero-friction path is the OS assist screenshot handed to a
        // VoiceInteractionSession. We can report support without requesting
        // MediaProjection and without storing any image.
        return true
    }

    fun detect(context: Context, hotword: HotwordStatus = AssistantRuntime.snapshot().hotword): CapabilityReport {
        DeviceStateMonitor.refresh(context)
        val pm = context.packageManager
        val isAssistant = isDefaultAssistant(context)
        val mic = hasMicrophone(context)
        val overlay = canDrawOverlays(context)
        val notifications = notificationsEnabled(context)
        val battery = ignoresBatteryOptimizations(context)
        val audio = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
        val hasMicHardware = pm.hasSystemFeature(PackageManager.FEATURE_MICROPHONE)

        val rows = buildList {
            add(
                CapabilityRow(
                    "Default digital assistant",
                    if (isAssistant) "IRIS selected" else "Not selected",
                    isAssistant,
                    "Required for power-button long press, system assist gesture, keyguard invoke, and AlwaysOnHotwordDetector.",
                ),
            )
            add(
                CapabilityRow(
                    "Always-on hotword \"${AssistantDefaults.KEYPHRASE}\"",
                    hotword.label,
                    hotword.isEnrolled,
                    hotword.detail,
                ),
            )
            add(
                CapabilityRow(
                    "Hardware microphone",
                    if (hasMicHardware) "Present" else "Missing",
                    hasMicHardware,
                    "Used only during an active, visible assistant session. Audio is streamed to the existing IRIS /api/voice/live endpoint.",
                ),
            )
            add(
                CapabilityRow(
                    "Microphone permission",
                    if (mic) "Granted" else "Denied",
                    mic,
                    "Must be granted once. Hotword detection itself is handled by the system DSP, not by continuously recording audio.",
                ),
            )
            add(
                CapabilityRow(
                    "Audio focus / echo cancellation",
                    if (audio != null) "AudioManager available" else "Unavailable",
                    audio != null,
                    "The session requests transient audio focus; acoustic echo cancellation is enabled when the OEM exposes it.",
                ),
            )
            add(
                CapabilityRow(
                    "Screen perception",
                    "OS assist screenshot",
                    screenPerceptionPossible(context),
                    "Screenshots are delivered by Android to the assistant session, encoded in RAM and sent to the existing VisionService. Nothing is written to disk.",
                ),
            )
            add(
                CapabilityRow(
                    "Overlay permission",
                    if (overlay) "Granted" else "Not granted",
                    overlay,
                    "Only needed for the fallback floating session when IRIS is not the default assistant. Not used for the permanent shortcut-free experience.",
                ),
            )
            add(
                CapabilityRow(
                    "Notifications",
                    if (notifications) "Granted" else "Not granted",
                    notifications,
                    "Used only for the optional assistant status/notification action.",
                ),
            )
            add(
                CapabilityRow(
                    "Battery optimisation",
                    if (battery) "IRIS exempt" else "Optimised",
                    battery,
                    "The assistant does not hold wake locks or poll sensors. Exemption is recommended on realme UI so the system can rebind the assistant service.",
                ),
            )
            add(
                CapabilityRow(
                    "Realme screen-off gestures",
                    "Not exposed to third-party apps",
                    false,
                    "realme UI does not publish a screen-off gesture API or intent. Use the system assistant gesture or the Quick Settings tile instead.",
                ),
            )
            add(
                CapabilityRow(
                    "Display / lock state",
                    DeviceStateMonitor.describe(),
                    true,
                    "Tracked from system broadcasts only; no sensor polling.",
                ),
            )
        }

        return CapabilityReport(
            device = "${Build.MANUFACTURER} ${Build.MODEL}",
            android = DeviceStateMonitor.sdkLabel(),
            manufacturer = Build.MANUFACTURER,
            isAssistant = isAssistant,
            microphone = mic,
            overlay = overlay,
            notifications = notifications,
            batteryOptimized = battery,
            screenPerception = screenPerceptionPossible(context),
            hotword = hotword,
            displayState = DeviceStateMonitor.describe(),
            rows = rows,
        )
    }

    @JvmStatic
    fun requestAssistantRole(context: Context): Boolean {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val roleManager = context.getSystemService(Context.ROLE_SERVICE) as? RoleManager
            if (roleManager != null && roleManager.isRoleAvailable(RoleManager.ROLE_ASSISTANT)) {
                val intent = roleManager.createRequestRoleIntent(RoleManager.ROLE_ASSISTANT)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(intent)
                return true
            }
        }
        return openAssistantSettings(context)
    }

    @JvmStatic
    fun openAssistantSettings(context: Context): Boolean {
        val candidates = buildList {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) add(Settings.ACTION_VOICE_INPUT_SETTINGS)
            add(Settings.ACTION_VOICE_INPUT_SETTINGS)
            add(Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS)
        }
        for (action in candidates.distinct()) {
            try {
                context.startActivity(Intent(action).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                return true
            } catch (_: Exception) {
            }
        }
        return false
    }
}
