package com.kirtan.iris.assistant

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** Stable Java/Capacitor-facing facade used by the existing React dashboard. */
object AssistantBridge {

    @JvmStatic
    fun capabilitiesJson(context: Context): String {
        val report = CapabilityDetector.detect(context)
        val root = JSONObject()
        root.put("device", report.device)
        root.put("android", report.android)
        root.put("isAssistant", report.isAssistant)
        root.put("microphone", report.microphone)
        root.put("overlay", report.overlay)
        root.put("notifications", report.notifications)
        root.put("batteryOptimized", report.batteryOptimized)
        root.put("screenPerception", report.screenPerception)
        root.put("displayState", report.displayState)
        root.put("language", AssistantPreferences(context).languageTag)
        root.put("hotwordState", report.hotword.state)
        root.put("hotwordLabel", report.hotword.label)
        root.put("hotwordDetail", report.hotword.detail)
        val rows = JSONArray()
        report.rows.forEach { row ->
            rows.put(
                JSONObject()
                    .put("title", row.title)
                    .put("value", row.value)
                    .put("supported", row.supported)
                    .put("detail", row.detail),
            )
        }
        root.put("rows", rows)
        return root.toString()
    }

    @JvmStatic
    fun launchAssistant(context: Context) {
        AssistantLauncher.launch(context, AssistantSource.IN_APP)
    }

    @JvmStatic
    fun openSettings(context: Context) {
        AssistantLauncher.openSettings(context)
    }

    @JvmStatic
    fun refreshHotword() {
        IrisVoiceInteractionService.refreshHotword()
    }
}
