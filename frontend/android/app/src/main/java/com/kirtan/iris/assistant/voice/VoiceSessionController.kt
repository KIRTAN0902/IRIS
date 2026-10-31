package com.kirtan.iris.assistant.voice

import android.content.Context
import android.graphics.Bitmap
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.kirtan.iris.AppLauncherPlugin
import com.kirtan.iris.IrisScreenCaptureManager
import com.kirtan.iris.assistant.AssistantMessages
import com.kirtan.iris.assistant.AssistantPreferences
import com.kirtan.iris.assistant.AssistantRuntime
import com.kirtan.iris.assistant.AssistantSource
import com.kirtan.iris.assistant.AssistantState
import com.kirtan.iris.assistant.CapabilityDetector
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
import java.net.URLEncoder
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * The single native voice-session lifecycle.
 *
 * It is intentionally only a transport + audio client: reasoning (P1), tool
 * execution (P2), memory, Mesh and VisionService all remain on the existing IRIS
 * backend. No command interpreter is duplicated on the phone.
 */
class VoiceSessionController(
    context: Context,
    private val source: AssistantSource,
    private val onDismiss: () -> Unit,
) {
    companion object {
        private const val TAG = "IRIS_VoiceSession"
        private const val CONNECT_TIMEOUT_MS = 10_000L
        private const val ERROR_AUTO_DISMISS_MS = 4_000L
    }

    private val appContext = context.applicationContext
    private val prefs = AssistantPreferences(appContext)
    private val main = Handler(Looper.getMainLooper())
    private val active = AtomicBoolean(false)
    private val dismissing = AtomicBoolean(false)

    private var webSocket: WebSocket? = null
    private var client: OkHttpClient? = null
    private var audio: AudioEngine? = null
    private var followUpRunnable: Runnable? = null
    private var connectTimeout: Runnable? = null
    private var retries = 0
    private var transcript = StringBuilder()
    private var speaking = false

    private val micLevelListener: (Float) -> Unit = { level ->
        AssistantRuntime.levels(mic = level)
        if (level > 0.18f) cancelFollowUp()
    }

    fun start() {
        if (active.getAndSet(true)) return
        retries = 0
        transcript = StringBuilder()
        speaking = false
        AssistantRuntime.begin(source)

        if (!CapabilityDetector.hasMicrophone(appContext)) {
            fail("Microphone permission is required. Open IRIS Assistant Settings and grant it.")
            return
        }

        audio = AudioEngine(
            appContext,
            onMicPcm = { bytes, length -> forwardMicrophone(bytes, length) },
            onMicLevel = micLevelListener,
            onOutputLevel = { level -> AssistantRuntime.levels(output = level) },
            onFocusLost = {
                if (active.get()) {
                    fail("Audio focus was taken by another app (for example a phone call).")
                    scheduleDismiss(1_500L)
                }
            },
            onError = { message -> fail(message) },
        ).also { it.start() }

        connect()
    }

    private fun connect() {
        AssistantRuntime.setState(AssistantState.ACTIVATING)
        AssistantRuntime.status(AssistantMessages.ACTIVATING)

        val base = buildString {
            append(prefs.voiceWebSocketUrl())
            append("?language=").append(URLEncoder.encode(prefs.languageTag, "UTF-8"))
            if (prefs.voiceName.isNotBlank()) {
                append("&voice=").append(URLEncoder.encode(prefs.voiceName, "UTF-8"))
            }
        }

        val http = OkHttpClient.Builder()
            .connectTimeout(8, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .writeTimeout(10, TimeUnit.SECONDS)
            .pingInterval(20, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
        client = http

        val request = Request.Builder()
            .url(base)
            .header("X-IRIS-Target-Device", "phone_android")
            .header("X-IRIS-Mode", "native_assistant")
            .header("X-IRIS-Language", prefs.languageTag)
            .header("X-IRIS-Voice", prefs.voiceName)
            .header("X-IRIS-Activation", source.name)
            .build()

        Log.i(TAG, "Connecting voice session: $base")
        connectTimeout = Runnable {
            if (active.get() && !AssistantRuntime.snapshot().connected) {
                fail("IRIS backend did not respond in time.")
            }
        }.also { main.postDelayed(it, CONNECT_TIMEOUT_MS) }

        webSocket = http.newWebSocket(request, socketListener)
    }

    private val socketListener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            main.post {
                cancelConnectTimeout()
                if (!active.get()) return@post
                AssistantRuntime.connected()
                AssistantRuntime.status(AssistantMessages.LISTENING)
                Log.i(TAG, "Voice WebSocket open")
            }
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            main.post { handleTextFrame(webSocket, text) }
        }

        override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
            val pcm = bytes.toByteArray()
            if (pcm.isEmpty()) return
            main.post {
                if (!active.get()) return@post
                cancelFollowUp()
                speaking = true
                AssistantRuntime.update {
                    it.copy(state = AssistantState.SPEAKING, statusText = AssistantMessages.SPEAKING)
                }
                audio?.play(pcm)
            }
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            main.post {
                if (!active.get()) return@post
                Log.w(TAG, "Voice WebSocket failure: ${t.message}")
                if (retries < 1) {
                    retries += 1
                    AssistantRuntime.status("Reconnecting")
                    main.postDelayed({ if (active.get()) connect() }, 1_200L)
                } else {
                    fail(AssistantMessages.CONNECTION_ERROR)
                    scheduleDismiss(ERROR_AUTO_DISMISS_MS)
                }
            }
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            main.post {
                if (!active.get() || dismissing.get()) return@post
                Log.i(TAG, "Voice WebSocket closed: $code $reason")
                fail("The assistant connection closed.")
                scheduleDismiss(ERROR_AUTO_DISMISS_MS)
            }
        }
    }

    private fun handleTextFrame(socket: WebSocket, raw: String) {
        if (!active.get()) return
        val json = runCatching { JSONObject(raw) }.getOrNull() ?: return
        when (json.optString("type")) {
            "ready" -> {
                cancelConnectTimeout()
                AssistantRuntime.connected()
                AssistantRuntime.status(AssistantMessages.LISTENING)
            }

            "text" -> {
                val part = json.optString("text")
                if (part.isNotBlank()) {
                    cancelFollowUp()
                    transcript.append(part)
                    AssistantRuntime.transcript(transcript.toString())
                    if (!speaking) AssistantRuntime.setState(AssistantState.PROCESSING)
                }
            }

            "turn_complete" -> {
                speaking = false
                AssistantRuntime.listening()
                scheduleFollowUp()
            }

            "interrupted" -> {
                cancelFollowUp()
                speaking = false
                audio?.flushOutput()
                AssistantRuntime.listening()
            }

            "launch_mobile_app" -> {
                val app = json.optString("app")
                if (app.isNotBlank()) {
                    AssistantRuntime.setState(AssistantState.EXECUTING)
                    AssistantRuntime.status("Opening $app")
                    AppLauncherPlugin.launchAppDirect(appContext, app)
                }
            }

            "request_screen_capture" -> {
                val requestId = json.optString("request_id")
                AssistantRuntime.setState(AssistantState.PROCESSING)
                AssistantRuntime.status("Inspecting screen")
                IrisScreenCaptureManager.captureCurrentDisplay(
                    appContext,
                    object : IrisScreenCaptureManager.CaptureCallback {
                        override fun onSuccess(bitmap: Bitmap?, base64Jpeg: String?) {
                            val payload = JSONObject()
                                .put("type", "screen_capture_response")
                                .put("request_id", requestId)
                                .put("image_base64", base64Jpeg)
                            socket.send(payload.toString())
                            AssistantRuntime.status("Screen shared")
                        }

                        override fun onError(errorMessage: String?) {
                            val payload = JSONObject()
                                .put("type", "screen_capture_response")
                                .put("request_id", requestId)
                                .put("error", errorMessage ?: "Screen capture unavailable")
                            socket.send(payload.toString())
                            AssistantRuntime.status("Screen capture unavailable")
                        }
                    },
                )
            }

            "approval_required" -> {
                val text = json.optString("text").ifBlank { "IRIS needs your approval to continue." }
                AssistantRuntime.approval(text)
            }

            "error" -> {
                val message = json.optString("message").ifBlank { "IRIS reported an error." }
                fail(message)
                scheduleDismiss(ERROR_AUTO_DISMISS_MS)
            }

            "pong" -> Unit
            else -> Log.d(TAG, "Ignoring frame type ${json.optString("type")}")
        }
    }

    private fun forwardMicrophone(bytes: ByteArray, length: Int) {
        if (!active.get()) return
        webSocket?.send(bytes.toByteString(0, length))
    }

    fun interrupt() {
        audio?.flushOutput()
        speaking = false
        cancelFollowUp()
        runCatching {
            webSocket?.send(JSONObject().put("type", "interrupt").toString())
        }
        AssistantRuntime.listening()
    }

    fun restart() {
        stop()
        main.postDelayed({ if (!dismissing.get()) start() }, 150L)
    }

    fun stop(finalState: AssistantState = AssistantState.STANDBY) {
        val wasActive = active.getAndSet(false)
        cancelFollowUp()
        cancelConnectTimeout()
        audio?.stop()
        audio = null
        runCatching { webSocket?.close(1000, "Session finished") }
        webSocket = null
        client?.dispatcher?.executorService?.shutdown()
        client = null
        speaking = false
        transcript = StringBuilder()

        if (!wasActive) {
            if (finalState == AssistantState.DISMISSING && dismissing.compareAndSet(false, true)) {
                AssistantRuntime.setState(AssistantState.DISMISSING)
                main.postDelayed({
                    AssistantRuntime.standby()
                    dismissing.set(false)
                    onDismiss()
                }, 200L)
            }
            return
        }

        if (finalState == AssistantState.DISMISSING && dismissing.compareAndSet(false, true)) {
            AssistantRuntime.setState(AssistantState.DISMISSING)
            AssistantRuntime.status(AssistantMessages.DISMISSING)
            main.postDelayed({
                AssistantRuntime.standby()
                dismissing.set(false)
                onDismiss()
            }, 220L)
        } else {
            AssistantRuntime.standby()
        }
    }

    private fun fail(message: String) {
        cancelFollowUp()
        cancelConnectTimeout()
        AssistantRuntime.fail(message)
    }

    private fun scheduleDismiss(delayMs: Long) {
        main.postDelayed({
            if (active.get()) stop(AssistantState.DISMISSING)
        }, delayMs)
    }

    private fun scheduleFollowUp() {
        cancelFollowUp()
        val seconds = prefs.autoDismissSeconds
        followUpRunnable = Runnable {
            if (active.get()) {
                Log.i(TAG, "Follow-up window elapsed")
                stop(AssistantState.DISMISSING)
            }
        }.also { main.postDelayed(it, seconds * 1_000L) }
    }

    private fun cancelFollowUp() {
        followUpRunnable?.let { main.removeCallbacks(it) }
        followUpRunnable = null
    }

    private fun cancelConnectTimeout() {
        connectTimeout?.let { main.removeCallbacks(it) }
        connectTimeout = null
    }
}
