package com.kirtan.iris

import android.app.Application
import com.kirtan.iris.assistant.DeviceStateMonitor

/**
 * The application no longer guesses whether a launch came from a screen-off
 * gesture. Assistant activations are explicit intents or Android's
 * VoiceInteractionService; the launcher icon always opens the full dashboard.
 */
class IrisApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        DeviceStateMonitor.init(this)
    }
}
