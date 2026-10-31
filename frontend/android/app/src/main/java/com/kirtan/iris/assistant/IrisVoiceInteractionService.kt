package com.kirtan.iris.assistant

import android.os.Bundle
import android.service.voice.VoiceInteractionService
import android.service.voice.VoiceInteractionSession
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Android digital-assistant entry point.
 *
 * Android binds this service when IRIS is selected as the default assistant. It
 * owns the hardware hotword detector and can ask the system to present the real
 * VoiceInteractionSession over the current app or lock screen.
 */
class IrisVoiceInteractionService : VoiceInteractionService() {

    companion object {
        private const val TAG = "IRIS_VoiceService"
        const val EXTRA_SOURCE = "assistant_source"

        @Volatile
        private var instance: IrisVoiceInteractionService? = null

        @JvmStatic
        fun requestShowSession(source: AssistantSource): Boolean {
            val service = instance ?: return false
            return service.showAssistant(source)
        }

        @JvmStatic
        fun refreshHotword() {
            instance?.hotwordController?.refresh()
        }

        @JvmStatic
        fun isBound(): Boolean = instance != null
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private lateinit var prefs: AssistantPreferences
    private var hotwordController: HotwordController? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        prefs = AssistantPreferences(this)
        DeviceStateMonitor.init(this)
        hotwordController = HotwordController(this, prefs) {
            showAssistant(AssistantSource.HOTWORD)
        }
        scope.launch {
            AssistantRuntime.state.collect { state ->
                hotwordController?.setSessionActive(state.isActive)
            }
        }
        Log.i(TAG, "VoiceInteractionService created")
    }

    override fun onReady() {
        super.onReady()
        Log.i(TAG, "IRIS is ready as the system digital assistant")
        hotwordController?.refresh()
    }

    override fun onShutdown() {
        Log.i(TAG, "VoiceInteractionService shutdown")
        hotwordController?.release()
        hotwordController = null
        instance = null
        scope.cancel()
        AssistantRuntime.standby()
        super.onShutdown()
    }

    override fun onLaunchVoiceAssistFromKeyguard() {
        super.onLaunchVoiceAssistFromKeyguard()
        if (!showAssistant(AssistantSource.ASSIST_GESTURE)) {
            AssistantLauncher.launch(this, AssistantSource.ASSIST_GESTURE)
        }
    }

    internal fun showAssistant(source: AssistantSource): Boolean {
        AssistantRuntime.begin(source)
        return try {
            val args = Bundle().apply {
                putString(EXTRA_SOURCE, source.name)
                putBoolean("show_transcript", true)
            }
            showSession(
                args,
                VoiceInteractionSession.SHOW_WITH_ASSIST or VoiceInteractionSession.SHOW_WITH_SCREENSHOT,
            )
            Log.i(TAG, "showSession requested from $source")
            true
        } catch (t: Throwable) {
            Log.w(TAG, "showSession failed: ${t.message}")
            AssistantRuntime.standby()
            false
        }
    }
}
