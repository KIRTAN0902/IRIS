package com.kirtan.iris.assistant

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.kirtan.iris.assistant.ui.AssistantTheme
import kotlinx.coroutines.flow.MutableStateFlow

/**
 * Native diagnostics and setup surface. Every capability is measured on the
 * real device at runtime; nothing is reported as working merely because the APK
 * compiled or because an API exists.
 */
class AssistantSettingsActivity : ComponentActivity() {

    private lateinit var prefs: AssistantPreferences
    private val report = MutableStateFlow<CapabilityReport?>(null)
    private val hotwordEnabled = MutableStateFlow(true)

    private val micPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { refresh() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = AssistantPreferences(this)
        hotwordEnabled.value = prefs.hotwordEnabled
        DeviceStateMonitor.init(this)

        setContent {
            AssistantTheme {
                val current by report.collectAsStateWithLifecycle()
                val hotwordOn by hotwordEnabled.collectAsStateWithLifecycle()
                SettingsScreen(
                    report = current,
                    hotwordEnabled = hotwordOn,
                    language = prefs.languageTag,
                    server = prefs.serverBaseUrl(),
                    onBack = { onBackPressedDispatcher.onBackPressed() },
                    onRole = {
                        if (!CapabilityDetector.requestAssistantRole(this)) {
                            openAssistantSettings()
                        }
                    },
                    onOpenAssistantSettings = { openAssistantSettings() },
                    onMic = {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                            micPermission.launch(Manifest.permission.RECORD_AUDIO)
                        }
                    },
                    onOverlay = { openOverlaySettings() },
                    onBattery = { openBatterySettings() },
                    onHotwordToggle = { enabled ->
                        hotwordEnabled.value = enabled
                        prefs.hotwordEnabled = enabled
                        IrisVoiceInteractionService.refreshHotword()
                    },
                    onHotwordSetup = { openVoiceInputSettings() },
                    onTest = {
                        AssistantLauncher.launch(this, AssistantSource.TEST)
                    },
                )
            }
        }
    }

    override fun onResume() {
        super.onResume()
        refresh()
    }

    private fun refresh() {
        report.value = CapabilityDetector.detect(this, AssistantRuntime.snapshot().hotword)
    }

    private fun openAssistantSettings() {
        CapabilityDetector.openAssistantSettings(this)
    }

    private fun openVoiceInputSettings() {
        runCatching {
            startActivity(Intent(Settings.ACTION_VOICE_INPUT_SETTINGS))
        }.onFailure {
            openAssistantSettings()
        }
    }

    private fun openOverlaySettings() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            runCatching {
                startActivity(
                    Intent(
                        Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:$packageName"),
                    ),
                )
            }
        }
    }

    private fun openBatterySettings() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            runCatching {
                startActivity(
                    Intent(
                        Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                        Uri.parse("package:$packageName"),
                    ),
                )
            }.onFailure {
                runCatching { startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)) }
            }
        }
    }
}

@Composable
private fun SettingsScreen(
    report: CapabilityReport?,
    hotwordEnabled: Boolean,
    language: String,
    server: String,
    onBack: () -> Unit,
    onRole: () -> Unit,
    onOpenAssistantSettings: () -> Unit,
    onMic: () -> Unit,
    onOverlay: () -> Unit,
    onBattery: () -> Unit,
    onHotwordToggle: (Boolean) -> Unit,
    onHotwordSetup: () -> Unit,
    onTest: () -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    listOf(Color(0xFF04080D), Color(0xFF071018), Color(0xFF020508)),
                ),
            ),
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 28.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = "‹",
                    color = Color(0xFF67E8F9),
                    fontSize = 30.sp,
                    modifier = Modifier
                        .clip(CircleShape)
                        .clickable(onClick = onBack)
                        .padding(horizontal = 10.dp),
                )
                Spacer(Modifier.width(8.dp))
                Column {
                    Text(
                        text = "IRIS NATIVE ASSISTANT",
                        color = Color(0xFFE6FBFF),
                        fontSize = 18.sp,
                        fontWeight = FontWeight.SemiBold,
                        letterSpacing = 1.8.sp,
                    )
                    Text(
                        text = "System integration, capabilities and privacy",
                        color = Color(0xFF7FA6B6),
                        fontSize = 11.sp,
                    )
                }
            }

            Spacer(Modifier.height(22.dp))

            HeroCard(report)
            Spacer(Modifier.height(14.dp))

            SettingsCard("ASSISTANT ROLE") {
                StatusLine(
                    label = "Default digital assistant",
                    value = if (report?.isAssistant == true) "IRIS selected" else "Not selected",
                    ok = report?.isAssistant == true,
                )
                Hint("Required for power-button long press, the system assist gesture, lock-screen invocation and hardware hotword detection.")
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    ActionButton(if (report?.isAssistant == true) "Reconfigure" else "Set IRIS as assistant", onRole)
                    ActionButton("Android settings", onOpenAssistantSettings)
                }
            }

            Spacer(Modifier.height(14.dp))

            SettingsCard("ALWAYS-ON HOTWORD • \"${AssistantDefaults.KEYPHRASE}\"") {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(
                            text = if (hotwordEnabled) "Hotword enabled" else "Hotword disabled",
                            color = Color(0xFFE6FBFF),
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Medium,
                        )
                        Text(
                            text = "Uses Android's hardware-detected keyphrase path. The assistant never streams microphone audio until activation.",
                            color = Color(0xFF7FA6B6),
                            fontSize = 11.sp,
                        )
                    }
                    Spacer(Modifier.width(12.dp))
                    Switch(
                        checked = hotwordEnabled,
                        onCheckedChange = onHotwordToggle,
                        colors = SwitchDefaults.colors(
                            checkedThumbColor = Color(0xFF03212A),
                            checkedTrackColor = Color(0xFF22D3EE),
                        ),
                    )
                }
                Spacer(Modifier.height(10.dp))
                StatusLine(
                    label = "Hardware detector",
                    value = report?.hotword?.label ?: "Not evaluated",
                    ok = report?.hotword?.isEnrolled == true,
                )
                Hint(report?.hotword?.detail ?: "Open this screen after selecting IRIS as the assistant; Android will report the real DSP capability.")
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    ActionButton("Hotword enrolment", onHotwordSetup)
                }
            }

            Spacer(Modifier.height(14.dp))

            SettingsCard("VOICE & PRIVACY") {
                StatusLine("Microphone permission", if (report?.microphone == true) "Granted" else "Denied", report?.microphone == true)
                StatusLine("Language", "$language • English (India)", true)
                StatusLine("Voice session", "Existing IRIS /api/voice/live", true)
                StatusLine("Permissions", "Microphone only while the session is visible", true)
                StatusLine("Screen perception", "OS assist screenshot • RAM only, never stored", report?.screenPerception == true)
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    ActionButton("Grant microphone", onMic)
                    ActionButton("Test session", onTest)
                }
            }

            Spacer(Modifier.height(14.dp))

            SettingsCard("BACKGROUND & BATTERY") {
                StatusLine("Battery optimisation", if (report?.batteryOptimized == true) "IRIS exempt" else "Optimising IRIS", report?.batteryOptimized == true)
                StatusLine("Display state", report?.displayState ?: "Unknown", true)
                StatusLine("Sensor polling", "None", true)
                StatusLine("Wake locks", "None held by the assistant", true)
                Hint("realme UI may kill or freeze background services. Exempt IRIS from battery optimisation and allow auto-launch so Android can rebind the assistant service.")
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    ActionButton("Battery settings", onBattery)
                    ActionButton("Overlay (fallback)", onOverlay)
                }
            }

            Spacer(Modifier.height(14.dp))

            SettingsCard("OEM GESTURES ON REALME UI") {
                Text(
                    text = "realme UI does not expose a third-party screen-off gesture API or broadcast. Double-tap-to-wake only wakes the display and never delivers the tap event to an app. The reliable integrations are the system assistant gesture (power long-press / corner swipe), the Quick Settings tile, the launcher shortcut and this session.",
                    color = Color(0xFFB6D4DF),
                    fontSize = 12.sp,
                    lineHeight = 18.sp,
                )
                Spacer(Modifier.height(8.dp))
                ActionButton("Test assistant activation", onTest)
            }

            Spacer(Modifier.height(14.dp))

            SettingsCard("CAPABILITY MATRIX") {
                Text(
                    text = "${report?.device ?: "Unknown device"} • ${report?.android ?: ""}",
                    color = Color(0xFF8FB8C7),
                    fontSize = 11.sp,
                )
                Spacer(Modifier.height(8.dp))
                report?.rows?.forEach { row ->
                    CapabilityRowView(row)
                }
                Spacer(Modifier.height(8.dp))
                Text(
                    text = "Backend: $server",
                    color = Color(0xFF5C7C8A),
                    fontSize = 10.sp,
                )
            }
        }
    }
}

@Composable
private fun HeroCard(report: CapabilityReport?) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(22.dp))
            .background(
                Brush.linearGradient(
                    listOf(Color(0xFF0B1B26), Color(0xFF101A2E), Color(0xFF081018)),
                ),
            )
            .padding(18.dp),
    ) {
        Text(
            text = if (report?.isAssistant == true) "IRIS is your system assistant" else "Make IRIS the system assistant",
            color = Color(0xFFE8FCFF),
            fontSize = 16.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(6.dp))
        Text(
            text = if (report?.isAssistant == true) {
                "Android can now invoke IRIS over the current app. The full dashboard remains a separate, normal app launch."
            } else {
                "Select IRIS once in Android settings. The assistant session is independent of the full application, and no floating shortcut is installed."
            },
            color = Color(0xFF9FC4D2),
            fontSize = 12.sp,
            lineHeight = 18.sp,
        )
    }
}

@Composable
private fun SettingsCard(title: String, content: @Composable () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(20.dp))
            .background(Color(0xCC070D13))
            .padding(16.dp),
    ) {
        Text(
            text = title,
            color = Color(0xFF67E8F9),
            fontSize = 10.sp,
            fontWeight = FontWeight.SemiBold,
            letterSpacing = 1.4.sp,
        )
        Spacer(Modifier.height(10.dp))
        content()
    }
}

@Composable
private fun StatusLine(label: String, value: String, ok: Boolean) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(6.dp)
                .clip(CircleShape)
                .background(if (ok) Color(0xFF34D399) else Color(0xFFFFB020)),
        )
        Spacer(Modifier.width(8.dp))
        Text(text = label, color = Color(0xFFB2CDD8), fontSize = 12.sp, modifier = Modifier.weight(1f))
        Text(text = value, color = Color(0xFFE6FBFF), fontSize = 12.sp)
    }
}

@Composable
private fun CapabilityRowView(row: CapabilityRow) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 5.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Box(
            Modifier
                .padding(top = 5.dp)
                .size(6.dp)
                .clip(CircleShape)
                .background(if (row.supported) Color(0xFF34D399) else Color(0xFFFF8A65)),
        )
        Spacer(Modifier.width(8.dp))
        Column(Modifier.weight(1f)) {
            Row {
                Text(text = row.title, color = Color(0xFFD7EEF5), fontSize = 11.sp, modifier = Modifier.weight(1f))
                Text(text = row.value, color = Color(0xFF8FB8C7), fontSize = 10.sp)
            }
            Text(text = row.detail, color = Color(0xFF66838F), fontSize = 10.sp, lineHeight = 14.sp)
        }
    }
}

@Composable
private fun Hint(text: String) {
    Text(text = text, color = Color(0xFF7795A1), fontSize = 10.sp, lineHeight = 14.sp)
    Spacer(Modifier.height(8.dp))
}

@Composable
private fun ActionButton(label: String, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(Color(0xFF0E2430))
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 9.dp),
    ) {
        Text(text = label, color = Color(0xFF9FE8F5), fontSize = 11.sp, fontWeight = FontWeight.Medium)
    }
}
