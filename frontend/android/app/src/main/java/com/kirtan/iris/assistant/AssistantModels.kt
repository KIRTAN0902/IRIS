package com.kirtan.iris.assistant

/** The real state of the native voice session. The UI renders this, nothing else. */
enum class AssistantState {
    STANDBY,
    ACTIVATING,
    LISTENING,
    PROCESSING,
    EXECUTING,
    SPEAKING,
    APPROVAL_REQUIRED,
    ERROR,
    DISMISSING,
}

enum class AssistantSource {
    HOTWORD,
    ASSIST_GESTURE,
    QUICK_TILE,
    SHORTCUT,
    WIDGET,
    NOTIFICATION,
    IN_APP,
    TEST,
}

/** Result of trying to create Android's hardware-backed hotword detector. */
data class HotwordStatus(
    val state: Int = AlwaysOnHotwordStates.UNKNOWN,
    val keyphrase: String = AssistantDefaults.KEYPHRASE,
    val localeTag: String = AssistantDefaults.LANGUAGE_TAG,
    val detail: String = "Not evaluated yet.",
) {
    val isEnrolled: Boolean get() = state == AlwaysOnHotwordStates.ENROLLED
    val isHardwareBacked: Boolean get() = isEnrolled
    val label: String
        get() = when (state) {
            AlwaysOnHotwordStates.ENROLLED -> "Available (hardware DSP)"
            AlwaysOnHotwordStates.UNENROLLED -> "Keyphrase not enrolled"
            AlwaysOnHotwordStates.UNSUPPORTED -> "Keyphrase unsupported by device DSP"
            AlwaysOnHotwordStates.HARDWARE_UNAVAILABLE -> "No compatible hotword hardware"
            AlwaysOnHotwordStates.NOT_ASSISTANT -> "IRIS is not the default assistant"
            else -> "Not evaluated"
        }
}

/** Mirrors AlwaysOnHotwordDetector state constants without importing platform types into the UI. */
object AlwaysOnHotwordStates {
    const val UNKNOWN = Int.MIN_VALUE
    const val HARDWARE_UNAVAILABLE = -2
    const val UNSUPPORTED = -1
    const val UNENROLLED = 1
    const val ENROLLED = 2
    const val NOT_ASSISTANT = 100
}

data class AssistantUiState(
    val state: AssistantState = AssistantState.STANDBY,
    val source: AssistantSource = AssistantSource.IN_APP,
    val statusText: String = "IRIS is ready",
    val transcript: String = "",
    val error: String? = null,
    val micLevel: Float = 0f,
    val outputLevel: Float = 0f,
    val languageTag: String = AssistantDefaults.LANGUAGE_TAG,
    val hotword: HotwordStatus = HotwordStatus(),
    val connected: Boolean = false,
    val foregroundPackage: String = "",
    val approvalText: String = "",
) {
    val isActive: Boolean
        get() = state != AssistantState.STANDBY && state != AssistantState.DISMISSING
}

object AssistantDefaults {
    const val PREFS = "iris_assistant"
    const val KEYPHRASE = "Hey IRIS"
    const val LANGUAGE_TAG = "en-IN"
    const val VOICE_NAME = ""
    const val DEFAULT_SERVER = "https://irisai.runs-on.dev"
    const val HOTWORD_ENABLED = "hotword_enabled"
    const val SERVER_URL = "assistant_server_url"
    const val LANGUAGE = "assistant_language"
    const val VOICE = "assistant_voice"
    const val AUTO_DISMISS_SECONDS = "assistant_auto_dismiss_seconds"
}

object AssistantMessages {
    const val LISTENING = "Listening"
    const val THINKING = "Thinking"
    const val EXECUTING = "Working"
    const val SPEAKING = "Speaking"
    const val ACTIVATING = "Connecting"
    const val APPROVAL = "Approval needed"
    const val CONNECTION_ERROR = "Connection lost"
    const val MIC_DENIED = "Microphone permission is required"
    const val DISMISSING = "Closing"
}
