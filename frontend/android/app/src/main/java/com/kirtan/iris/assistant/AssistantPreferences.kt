package com.kirtan.iris.assistant

import android.content.Context

/**
 * Single source of truth for native assistant configuration.
 *
 * The legacy Capacitor server URL is honoured so an existing installation keeps
 * talking to the same IRIS backend after the assistant migration.
 */
class AssistantPreferences(context: Context) {

    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences(AssistantDefaults.PREFS, Context.MODE_PRIVATE)
    private val legacy = appContext.getSharedPreferences("iris_payment_prefs", Context.MODE_PRIVATE)

    var hotwordEnabled: Boolean
        get() = prefs.getBoolean(AssistantDefaults.HOTWORD_ENABLED, true)
        set(value) = prefs.edit().putBoolean(AssistantDefaults.HOTWORD_ENABLED, value).apply()

    var languageTag: String
        get() = prefs.getString(AssistantDefaults.LANGUAGE, AssistantDefaults.LANGUAGE_TAG)
            ?.takeIf { it.isNotBlank() } ?: AssistantDefaults.LANGUAGE_TAG
        set(value) = prefs.edit().putString(AssistantDefaults.LANGUAGE, value).apply()

    var voiceName: String
        get() = prefs.getString(AssistantDefaults.VOICE, AssistantDefaults.VOICE_NAME).orEmpty()
        set(value) = prefs.edit().putString(AssistantDefaults.VOICE, value).apply()

    var autoDismissSeconds: Int
        get() = prefs.getInt(AssistantDefaults.AUTO_DISMISS_SECONDS, 12).coerceIn(4, 60)
        set(value) = prefs.edit().putInt(AssistantDefaults.AUTO_DISMISS_SECONDS, value.coerceIn(4, 60)).apply()

    fun serverBaseUrl(): String {
        val configured = prefs.getString(AssistantDefaults.SERVER_URL, null)
            ?.takeIf { it.isNotBlank() }
            ?: legacy.getString("server_url", null)?.takeIf { it.isNotBlank() }
            ?: AssistantDefaults.DEFAULT_SERVER
        return configured.trim().trimEnd('/')
    }

    fun voiceWebSocketUrl(): String {
        var base = serverBaseUrl()
        base = when {
            base.startsWith("https://") -> "wss://" + base.removePrefix("https://")
            base.startsWith("http://") -> "ws://" + base.removePrefix("http://")
            base.startsWith("wss://") || base.startsWith("ws://") -> base
            else -> "wss://$base"
        }
        return if (base.endsWith("/api")) "$base/voice/live" else "$base/api/voice/live"
    }

    fun setServerBaseUrl(value: String) {
        prefs.edit().putString(AssistantDefaults.SERVER_URL, value.trim().trimEnd('/')).apply()
    }
}
