package com.kirtan.iris.assistant

import android.service.voice.VoiceInteractionService
import android.util.Log
import java.lang.reflect.InvocationHandler
import java.lang.reflect.Method
import java.lang.reflect.Proxy
import java.util.Locale

/**
 * Owns Android's hardware hotword detector probing.
 *
 * AlwaysOnHotwordDetector is marked @SystemApi in Android and requires
 * the signature-level permission MANAGE_VOICE_KEYPHRASES. On retail devices
 * (like Realme GT 7T), OEM DSPs only enroll Google Assistant / Breeno sound models.
 *
 * This controller probes the platform API dynamically at runtime and reports
 * the actual device capability honestly without crashing or faking availability.
 */
class HotwordController(
    private val service: VoiceInteractionService,
    private val prefs: AssistantPreferences,
    private val onDetected: () -> Unit,
) {
    companion object {
        private const val TAG = "IRIS_Hotword"
        private val CANDIDATE_LOCALES = listOf("en-IN", "en-US", "en-GB")
    }

    private var detectorInstance: Any? = null
    private var sessionActive = false
    private var prefEnabled = true

    fun refresh() {
        release()
        prefEnabled = prefs.hotwordEnabled
        val context = service.applicationContext

        if (!CapabilityDetector.isDefaultAssistant(context)) {
            AssistantRuntime.hotword(
                HotwordStatus(
                    state = AlwaysOnHotwordStates.NOT_ASSISTANT,
                    detail = "Select IRIS as the default digital assistant, then restart IRIS so Android can bind the assistant service.",
                ),
            )
            return
        }
        if (!prefEnabled) {
            AssistantRuntime.hotword(
                HotwordStatus(detail = "Always-on hotword is disabled in IRIS settings."),
            )
            return
        }

        // Dynamically probe createAlwaysOnHotwordDetector method on VoiceInteractionService
        val createMethod: Method? = try {
            VoiceInteractionService::class.java.methods.firstOrNull {
                it.name == "createAlwaysOnHotwordDetector" && it.parameterTypes.size == 3
            }
        } catch (t: Throwable) {
            null
        }

        if (createMethod == null) {
            Log.i(TAG, "createAlwaysOnHotwordDetector not accessible via public platform API on this device.")
            AssistantRuntime.hotword(
                HotwordStatus(
                    state = AlwaysOnHotwordStates.HARDWARE_UNAVAILABLE,
                    detail = "AlwaysOnHotwordDetector is not exposed in public Android SDK. Third-party apps cannot access the DSP hardware keyphrase enrollment without system signature.",
                ),
            )
            return
        }

        val locales = buildList {
            add(prefs.languageTag)
            addAll(CANDIDATE_LOCALES)
        }.distinct()

        var probeFailureReason: String? = null
        for (tag in locales) {
            val locale = Locale.forLanguageTag(tag)
            try {
                val callbackParamType = createMethod.parameterTypes[2]
                val callbackProxy = createCallbackProxy(callbackParamType, tag)
                val detector = createMethod.invoke(
                    service,
                    AssistantDefaults.KEYPHRASE,
                    locale,
                    callbackProxy,
                )
                detectorInstance = detector
                AssistantRuntime.hotword(
                    HotwordStatus(
                        state = AlwaysOnHotwordStates.UNKNOWN,
                        localeTag = tag,
                        detail = "Detector probe initiated for $tag. Awaiting DSP callback.",
                    ),
                )
                Log.i(TAG, "createAlwaysOnHotwordDetector invoked for $tag")
                return
            } catch (t: Throwable) {
                val root = t.cause ?: t
                probeFailureReason = root.message ?: root.javaClass.simpleName
                Log.w(TAG, "Hotword probe for $tag failed: $probeFailureReason")
            }
        }

        AssistantRuntime.hotword(
            HotwordStatus(
                state = AlwaysOnHotwordStates.HARDWARE_UNAVAILABLE,
                detail = "Hardware DSP keyphrase model is unavailable: $probeFailureReason. Realme UI restricts always-on DSP listening to system components. Use the power button, swipe gesture, or Quick Settings tile.",
            ),
        )
    }

    private fun createCallbackProxy(callbackClass: Class<*>, localeTag: String): Any? {
        if (!callbackClass.isInterface) {
            // Callback is an abstract class in framework stubs.
            return null
        }
        val handler = InvocationHandler { _, method, args ->
            when (method.name) {
                "onAvailabilityChanged" -> {
                    val status = (args?.getOrNull(0) as? Number)?.toInt() ?: 0
                    Log.i(TAG, "Hotword availability changed: $status")
                    applyStatus(status, localeTag)
                    null
                }
                "onDetected" -> {
                    Log.i(TAG, "Hotword detected!")
                    onDetected()
                    null
                }
                "onError" -> {
                    Log.w(TAG, "Hotword error reported by DSP")
                    null
                }
                else -> null
            }
        }
        return Proxy.newProxyInstance(callbackClass.classLoader, arrayOf(callbackClass), handler)
    }

    private fun applyStatus(rawStatus: Int, localeTag: String) {
        val mapped = when (rawStatus) {
            2 -> AlwaysOnHotwordStates.ENROLLED
            1 -> AlwaysOnHotwordStates.UNENROLLED
            -1 -> AlwaysOnHotwordStates.UNSUPPORTED
            -2 -> AlwaysOnHotwordStates.HARDWARE_UNAVAILABLE
            else -> AlwaysOnHotwordStates.UNKNOWN
        }
        AssistantRuntime.hotword(
            HotwordStatus(
                state = mapped,
                localeTag = localeTag,
                detail = "Reported by DSP for $localeTag.",
            ),
        )
    }

    fun setSessionActive(active: Boolean) {
        sessionActive = active
    }

    fun setEnabled(enabled: Boolean) {
        prefs.hotwordEnabled = enabled
        if (enabled) refresh() else release()
    }

    fun release() {
        val detector = detectorInstance
        if (detector != null) {
            try {
                detector.javaClass.getMethod("stopRecognition").invoke(detector)
            } catch (_: Throwable) {
            }
        }
        detectorInstance = null
    }
}
