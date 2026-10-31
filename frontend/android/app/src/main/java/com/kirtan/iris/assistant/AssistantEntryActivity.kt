package com.kirtan.iris.assistant

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.kirtan.iris.assistant.ui.AssistantOverlay
import com.kirtan.iris.assistant.ui.AssistantTheme
import com.kirtan.iris.assistant.voice.VoiceSessionController

/**
 * Fallback host for the exact same assistant session when IRIS is not the
 * selected system assistant. It is translucent, excluded from recents and turns
 * the display on only if the activation came from a hardware hotword while the
 * screen was off.
 */
class AssistantEntryActivity : ComponentActivity() {

    private lateinit var controller: VoiceSessionController

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        DeviceStateMonitor.init(this)
        DeviceStateMonitor.refresh(this)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                    WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON,
            )
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS)
        window.setDimAmount(0f)

        val source = AssistantLauncher.sourceFrom(intent)
        controller = VoiceSessionController(this, source) {
            if (!isFinishing) {
                finish()
                overridePendingTransition(0, android.R.anim.fade_out)
            }
        }
        setContent {
            AssistantTheme {
                AssistantOverlay(
                    stateFlow = AssistantRuntime.state,
                    onDismiss = { controller.stop(AssistantState.DISMISSING) },
                    onInterrupt = { controller.interrupt() },
                    onOpenSettings = { AssistantLauncher.openSettings(this) },
                    onRetry = { controller.restart() },
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        AssistantLauncher.sourceFrom(intent)
        controller.restart()
    }

    override fun onStart() {
        super.onStart()
        controller.start()
    }

    override fun onStop() {
        controller.stop()
        super.onStop()
        if (!isChangingConfigurations) finish()
    }

    override fun onDestroy() {
        controller.stop()
        super.onDestroy()
    }
}
