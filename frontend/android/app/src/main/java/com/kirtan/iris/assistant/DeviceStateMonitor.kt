package com.kirtan.iris.assistant

import android.app.KeyguardManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.os.PowerManager

/**
 * Tracks only the device states that matter to assistant activation:
 * display off, display waking, lock screen visible, unlocked, session active.
 *
 * Deliberately does not poll accelerometer, gyroscope or proximity sensors.
 * There is no wake lock and no background CPU loop.
 */
object DeviceStateMonitor {

    enum class DisplayState { UNKNOWN, OFF, ON_LOCKED, UNLOCKED }

    @Volatile
    var displayState: DisplayState = DisplayState.UNKNOWN
        private set

    @Volatile
    private var registered = false

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            context ?: return
            refresh(context)
        }
    }

    fun init(context: Context) {
        if (registered) return
        val app = context.applicationContext
        val filter = IntentFilter().apply {
            addAction(Intent.ACTION_SCREEN_OFF)
            addAction(Intent.ACTION_SCREEN_ON)
            addAction(Intent.ACTION_USER_PRESENT)
            addAction(Intent.ACTION_USER_BACKGROUND)
        }
        app.registerReceiver(receiver, filter)
        registered = true
        refresh(app)
    }

    fun refresh(context: Context) {
        val power = context.getSystemService(Context.POWER_SERVICE) as? PowerManager
        val keyguard = context.getSystemService(Context.KEYGUARD_SERVICE) as? KeyguardManager
        displayState = when {
            power == null || !power.isInteractive -> DisplayState.OFF
            keyguard != null && keyguard.isKeyguardLocked -> DisplayState.ON_LOCKED
            else -> DisplayState.UNLOCKED
        }
    }

    fun isScreenOff(): Boolean = displayState == DisplayState.OFF

    fun isLocked(): Boolean = displayState == DisplayState.ON_LOCKED

    fun describe(): String = when (displayState) {
        DisplayState.OFF -> "Display off"
        DisplayState.ON_LOCKED -> "Lock screen visible"
        DisplayState.UNLOCKED -> "Device unlocked"
        DisplayState.UNKNOWN -> "Unknown"
    }

    fun sdkLabel(): String = "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})"
}
