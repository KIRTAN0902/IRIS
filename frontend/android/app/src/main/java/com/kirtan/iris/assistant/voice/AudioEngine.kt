package com.kirtan.iris.assistant.voice

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.min
import kotlin.math.sqrt

/**
 * Native full-duplex audio for the assistant session.
 *
 * Capture is 24 kHz / 16-bit / mono PCM (the Gemini Live wire format).
 * Playback runs on its own queue so WebSocket callbacks never block.
 * The microphone is only opened while a session is active.
 */
class AudioEngine(
    context: Context,
    private val onMicPcm: (ByteArray, Int) -> Unit,
    private val onMicLevel: (Float) -> Unit,
    private val onOutputLevel: (Float) -> Unit,
    private val onFocusLost: () -> Unit,
    private val onError: (String) -> Unit,
) {
    companion object {
        private const val TAG = "IRIS_AudioEngine"
        const val SAMPLE_RATE = 24_000
    }

    private val appContext = context.applicationContext
    private val main = Handler(Looper.getMainLooper())
    private val audioManager = appContext.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    private val recording = AtomicBoolean(false)
    private val playing = AtomicBoolean(true)
    private var record: AudioRecord? = null
    private var recordThread: Thread? = null
    private var track: AudioTrack? = null
    private var playThread: Thread? = null
    private val playQueue = LinkedBlockingQueue<ByteArray>(64)
    private var echoCanceler: AcousticEchoCanceler? = null
    private var noiseSuppressor: NoiseSuppressor? = null
    private var focusRequest: AudioFocusRequest? = null
    private var legacyFocusListener: AudioManager.OnAudioFocusChangeListener? = null

    private val focusListener = AudioManager.OnAudioFocusChangeListener { change ->
        when (change) {
            AudioManager.AUDIOFOCUS_LOSS,
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT,
            -> {
                Log.i(TAG, "Audio focus lost ($change)")
                main.post { onFocusLost() }
            }
        }
    }

    fun start(): Boolean {
        if (!requestAudioFocus()) {
            onError("Another app is using the microphone")
            return false
        }
        val started = startCapture()
        startPlayback()
        return started
    }

    private fun requestAudioFocus(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val attributes = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANT)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build()
            val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
                .setAudioAttributes(attributes)
                .setAcceptsDelayedFocusGain(false)
                .setOnAudioFocusChangeListener(focusListener)
                .build()
            focusRequest = request
            audioManager.requestAudioFocus(request) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED
        } else {
            val listener = AudioManager.OnAudioFocusChangeListener { change ->
                focusListener.onAudioFocusChange(change)
            }
            legacyFocusListener = listener
            @Suppress("DEPRECATION")
            audioManager.requestAudioFocus(
                listener,
                AudioManager.STREAM_MUSIC,
                AudioManager.AUDIOFOCUS_GAIN_TRANSIENT,
            ) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED
        }
    }

    private fun startCapture(): Boolean {
        if (recording.getAndSet(true)) return true
        val minBuffer = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        if (minBuffer <= 0) {
            recording.set(false)
            onError("Microphone is unavailable")
            return false
        }

        val sources = intArrayOf(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            MediaRecorder.AudioSource.DEFAULT,
        )
        var created: AudioRecord? = null
        for (source in sources) {
            val candidate = try {
                AudioRecord(
                    source,
                    SAMPLE_RATE,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT,
                    maxOf(minBuffer * 2, 4800),
                )
            } catch (t: Throwable) {
                Log.w(TAG, "AudioRecord source $source failed: ${t.message}")
                null
            }
            if (candidate?.state == AudioRecord.STATE_INITIALIZED) {
                created = candidate
                break
            }
            candidate?.release()
        }

        val audioRecord = created
        if (audioRecord == null) {
            recording.set(false)
            onError("Microphone could not be initialised")
            return false
        }
        record = audioRecord

        if (AcousticEchoCanceler.isAvailable()) {
            echoCanceler = AcousticEchoCanceler.create(audioRecord.audioSessionId)?.apply { enabled = true }
        }
        if (NoiseSuppressor.isAvailable()) {
            noiseSuppressor = NoiseSuppressor.create(audioRecord.audioSessionId)?.apply { enabled = true }
        }

        try {
            audioRecord.startRecording()
        } catch (t: Throwable) {
            Log.e(TAG, "startRecording failed: ${t.message}")
            recording.set(false)
            releaseCapture()
            onError("Microphone permission was denied")
            return false
        }

        recordThread = Thread({
            val buffer = ByteArray(2400)
            while (recording.get()) {
                val read = try {
                    audioRecord.read(buffer, 0, buffer.size)
                } catch (_: Throwable) {
                    -1
                }
                if (read > 0) {
                    onMicPcm(buffer.copyOf(read), read)
                    onMicLevel(rms(buffer, read))
                }
            }
        }, "IRIS-AudioCapture").apply {
            priority = Thread.NORM_PRIORITY + 1
            start()
        }
        return true
    }

    private fun startPlayback() {
        if (!playing.getAndSet(true)) return
        playThread = Thread({
            while (playing.get()) {
                val chunk = try {
                    playQueue.poll(250, TimeUnit.MILLISECONDS)
                } catch (_: InterruptedException) {
                    null
                } ?: continue
                val audioTrack = track ?: continue
                try {
                    audioTrack.write(chunk, 0, chunk.size)
                    onOutputLevel(rms(chunk, chunk.size))
                } catch (t: Throwable) {
                    Log.w(TAG, "AudioTrack write failed: ${t.message}")
                }
            }
        }, "IRIS-AudioPlayback").apply { start() }
    }

    fun play(pcm: ByteArray) {
        if (pcm.isEmpty() || !playing.get()) return
        if (track == null) initTrack()
        if (playQueue.remainingCapacity() == 0) playQueue.poll()
        playQueue.offer(pcm)
    }

    private fun initTrack() {
        try {
            val minBuffer = AudioTrack.getMinBufferSize(
                SAMPLE_RATE,
                AudioFormat.CHANNEL_OUT_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
            )
            val audioTrack = AudioTrack(
                AudioManager.STREAM_MUSIC,
                SAMPLE_RATE,
                AudioFormat.CHANNEL_OUT_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                maxOf(minBuffer * 2, 8192),
                AudioTrack.MODE_STREAM,
            )
            audioTrack.play()
            track = audioTrack
        } catch (t: Throwable) {
            Log.e(TAG, "AudioTrack init failed: ${t.message}")
            onError("Audio output is unavailable")
        }
    }

    fun flushOutput() {
        playQueue.clear()
        try {
            track?.pause()
            track?.flush()
            track?.play()
        } catch (_: Throwable) {
        }
        onOutputLevel(0f)
    }

    fun stop() {
        recording.set(false)
        playing.set(false)
        recordThread?.interrupt()
        recordThread = null
        playThread?.interrupt()
        playThread = null
        releaseCapture()
        try {
            track?.stop()
            track?.release()
        } catch (_: Throwable) {
        }
        track = null
        playQueue.clear()
        abandonAudioFocus()
        onMicLevel(0f)
        onOutputLevel(0f)
    }

    private fun releaseCapture() {
        echoCanceler?.release()
        echoCanceler = null
        noiseSuppressor?.release()
        noiseSuppressor = null
        try {
            if (record?.recordingState == AudioRecord.RECORDSTATE_RECORDING) record?.stop()
            record?.release()
        } catch (_: Throwable) {
        }
        record = null
    }

    private fun abandonAudioFocus() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            focusRequest?.let { audioManager.abandonAudioFocusRequest(it) }
            focusRequest = null
        } else {
            legacyFocusListener?.let {
                @Suppress("DEPRECATION")
                audioManager.abandonAudioFocus(it)
            }
            legacyFocusListener = null
        }
    }

    private fun rms(data: ByteArray, length: Int): Float {
        val samples = length / 2
        if (samples <= 0) return 0f
        var sum = 0.0
        var i = 0
        while (i < length - 1) {
            val sample = ((data[i].toInt() and 0xFF) or (data[i + 1].toInt() shl 8)).toShort()
            sum += sample.toDouble() * sample
            i += 2
        }
        val rms = sqrt(sum / samples)
        return min(1.0, rms / 9_000.0).toFloat()
    }
}
