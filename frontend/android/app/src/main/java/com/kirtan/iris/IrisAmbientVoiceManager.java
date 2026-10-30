package com.kirtan.iris;

import android.content.Context;
import android.graphics.Bitmap;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.AudioTrack;
import android.media.MediaRecorder;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.util.Log;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import okio.ByteString;

/**
 * Universal Ambient Voice Streaming & Hardware Action Manager for IRIS.
 *
 * Coordinates:
 * 1. Automatic 24kHz 16-bit mono PCM capture via AudioRecord.
 * 2. Full-duplex WebSocket connection to /api/voice/live.
 * 3. AudioTrack streaming playback.
 * 4. Screen Perception hardware capture dispatch (delivers screen_capture_response).
 * 5. Native local tool dispatching (AppLauncherPlugin.launchAppDirect).
 * 6. Zero Background Surveillance: microphone hardware is opened strictly during active turns.
 */
public class IrisAmbientVoiceManager {

    private static final String TAG = "IRIS_AmbientVoice";
    private static final int SAMPLE_RATE = 24000;
    private static final String DEFAULT_WS_URL = "wss://irisai.runs-on.dev/api/voice/live";

    private final Context mContext;
    private final IrisVisualContainer mVisualContainer;
    private final Handler mMainHandler;

    private WebSocket mWebSocket;
    private AudioRecord mAudioRecord;
    private AudioTrack mAudioTrack;
    private Thread mRecordThread;

    private final AtomicBoolean mIsActive = new AtomicBoolean(false);
    private final AtomicBoolean mIsRecording = new AtomicBoolean(false);

    private Runnable mFollowUpTimeoutRunnable;

    public IrisAmbientVoiceManager(Context context, IrisVisualContainer visualContainer) {
        this.mContext = context;
        this.mVisualContainer = visualContainer;
        this.mMainHandler = new Handler(Looper.getMainLooper());
    }

    public synchronized void startSession(String wsUrl) {
        if (mIsActive.getAndSet(true)) {
            Log.w(TAG, "Ambient voice session already active.");
            return;
        }

        String targetUrl = wsUrl;
        if (targetUrl == null || targetUrl.trim().isEmpty()) {
            android.content.SharedPreferences prefs = mContext.getSharedPreferences("iris_payment_prefs", Context.MODE_PRIVATE);
            String customServer = prefs.getString("server_url", null);
            if (customServer != null && !customServer.trim().isEmpty()) {
                String clean = customServer.trim();
                if (clean.endsWith("/")) clean = clean.substring(0, clean.length() - 1);
                if (clean.startsWith("http://")) clean = "ws://" + clean.substring(7);
                else if (clean.startsWith("https://")) clean = "wss://" + clean.substring(8);
                else if (!clean.startsWith("ws://") && !clean.startsWith("wss://")) clean = "wss://" + clean;
                targetUrl = clean + "/api/voice/live";
            } else {
                targetUrl = DEFAULT_WS_URL;
            }
        }
        Log.i(TAG, "Starting ambient voice session with endpoint: " + targetUrl);

        if (mVisualContainer != null) {
            mVisualContainer.setState(IrisVisualContainer.STATE_ACTIVATING);
        }
        initAudioTrack();
        connectWebSocket(targetUrl);
    }

    private void initAudioTrack() {
        try {
            int bufferSize = AudioTrack.getMinBufferSize(
                SAMPLE_RATE,
                AudioFormat.CHANNEL_OUT_MONO,
                AudioFormat.ENCODING_PCM_16BIT
            );
            mAudioTrack = new AudioTrack(
                AudioManager.STREAM_MUSIC,
                SAMPLE_RATE,
                AudioFormat.CHANNEL_OUT_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                Math.max(bufferSize * 2, 8192),
                AudioTrack.MODE_STREAM
            );
            mAudioTrack.play();
        } catch (Exception e) {
            Log.e(TAG, "Failed to initialize AudioTrack: " + e.getMessage(), e);
        }
    }

    private void connectWebSocket(String url) {
        OkHttpClient client = new OkHttpClient.Builder()
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .connectTimeout(8, TimeUnit.SECONDS)
            .build();

        Request request = new Request.Builder()
            .url(url)
            .addHeader("X-IRIS-Target-Device", "phone_android")
            .addHeader("X-IRIS-Ambient-Mode", "sphere")
            .build();

        client.newWebSocket(request, new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                mWebSocket = webSocket;
                Log.i(TAG, "Connected to IRIS Voice WebSocket.");
                mMainHandler.post(() -> {
                    if (mVisualContainer != null) {
                        mVisualContainer.setState(IrisVisualContainer.STATE_LISTENING);
                        mVisualContainer.setStatusText("Listening...");
                    }
                    startAudioRecording();
                });
            }

            @Override
            public void onMessage(WebSocket webSocket, String text) {
                try {
                    JSONObject json = new JSONObject(text);
                    String type = json.optString("type", "");

                    if ("ready".equals(type)) {
                        mMainHandler.post(() -> {
                            if (mVisualContainer != null) {
                                mVisualContainer.setState(IrisVisualContainer.STATE_LISTENING);
                                mVisualContainer.setStatusText("Listening...");
                            }
                        });
                    } else if ("text".equals(type)) {
                        String txt = json.optString("text", "");
                        mMainHandler.post(() -> {
                            if (mVisualContainer != null && txt.length() < 60) {
                                mVisualContainer.setStatusText(txt);
                            }
                        });
                    } else if ("launch_mobile_app".equals(type)) {
                        String app = json.optString("app", "");
                        mMainHandler.post(() -> {
                            if (mVisualContainer != null) {
                                mVisualContainer.setState(IrisVisualContainer.STATE_EXECUTING);
                                mVisualContainer.setStatusText("Opening " + app + "...");
                            }
                            AppLauncherPlugin.launchAppDirect(mContext, app);
                        });
                    } else if ("request_screen_capture".equals(type)) {
                        String reqId = json.optString("request_id", "");
                        Log.i(TAG, "Received request_screen_capture from server (id: " + reqId + ")");
                        mMainHandler.post(() -> {
                            if (mVisualContainer != null) {
                                mVisualContainer.setState(IrisVisualContainer.STATE_PROCESSING);
                                mVisualContainer.setStatusText("Inspecting screen...");
                            }
                            // Execute Hardware Screen Capture
                            IrisScreenCaptureManager.captureCurrentDisplay(mContext, new IrisScreenCaptureManager.CaptureCallback() {
                                @Override
                                public void onSuccess(Bitmap bitmap, String base64Jpeg) {
                                    Log.i(TAG, "Screen captured successfully, delivering response.");
                                    try {
                                        JSONObject resp = new JSONObject();
                                        resp.put("type", "screen_capture_response");
                                        resp.put("request_id", reqId);
                                        resp.put("image_base64", base64Jpeg);
                                        if (mWebSocket != null) {
                                            mWebSocket.send(resp.toString());
                                        }
                                    } catch (Exception e) {
                                        Log.e(TAG, "Error framing screen_capture_response: " + e.getMessage());
                                    }
                                }

                                @Override
                                public void onError(String errorMessage) {
                                    Log.w(TAG, "Screen capture failed: " + errorMessage);
                                    try {
                                        JSONObject resp = new JSONObject();
                                        resp.put("type", "screen_capture_response");
                                        resp.put("request_id", reqId);
                                        resp.put("error", errorMessage);
                                        if (mWebSocket != null) {
                                            mWebSocket.send(resp.toString());
                                        }
                                    } catch (Exception ignored) {}
                                }
                            });
                        });
                    } else if ("turn_complete".equals(type)) {
                        mMainHandler.post(() -> {
                            if (mVisualContainer != null) {
                                mVisualContainer.setState(IrisVisualContainer.STATE_LISTENING);
                                mVisualContainer.setStatusText("Listening...");
                            }
                            scheduleFollowUpWindow();
                        });
                    }
                } catch (Exception e) {
                    Log.w(TAG, "Error parsing WebSocket text frame: " + e.getMessage());
                }
            }

            @Override
            public void onMessage(WebSocket webSocket, ByteString bytes) {
                cancelFollowUpTimeout();
                byte[] rawAudio = bytes.toByteArray();
                if (mAudioTrack != null && rawAudio.length > 0) {
                    mAudioTrack.write(rawAudio, 0, rawAudio.length);
                    float amp = calculateRmsAmplitude(rawAudio);
                    mMainHandler.post(() -> {
                        if (mVisualContainer != null) {
                            mVisualContainer.setState(IrisVisualContainer.STATE_SPEAKING);
                            mVisualContainer.setAudioAmplitude(amp);
                        }
                    });
                }
            }

            @Override
            public void onFailure(WebSocket webSocket, Throwable t, Response response) {
                Log.e(TAG, "WebSocket connection failure: " + t.getMessage());
                mMainHandler.post(() -> {
                    if (mVisualContainer != null) {
                        mVisualContainer.setState(IrisVisualContainer.STATE_ERROR);
                        mVisualContainer.setStatusText("Connection error");
                    }
                    mMainHandler.postDelayed(() -> stopSession(), 2000);
                });
            }

            @Override
            public void onClosed(WebSocket webSocket, int code, String reason) {
                Log.i(TAG, "WebSocket closed: " + reason);
                mMainHandler.post(() -> stopSession());
            }
        });
    }

    private void scheduleFollowUpWindow() {
        cancelFollowUpTimeout();
        // Keep listening for 8 seconds for conversational follow-ups (e.g. "Now open Chrome")
        mFollowUpTimeoutRunnable = () -> {
            Log.i(TAG, "Follow-up window elapsed with no user speech.");
            if (mVisualContainer != null) {
                mVisualContainer.setState(IrisVisualContainer.STATE_IDLE);
            }
        };
        mMainHandler.postDelayed(mFollowUpTimeoutRunnable, 8000);
    }

    private void cancelFollowUpTimeout() {
        if (mFollowUpTimeoutRunnable != null) {
            mMainHandler.removeCallbacks(mFollowUpTimeoutRunnable);
            mFollowUpTimeoutRunnable = null;
        }
    }

    private void startAudioRecording() {
        if (mIsRecording.getAndSet(true)) return;

        try {
            int minBuffer = AudioRecord.getMinBufferSize(
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT
            );
            int bufferSize = Math.max(minBuffer * 2, 4096);

            mAudioRecord = new AudioRecord(
                MediaRecorder.AudioSource.VOICE_RECOGNITION,
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufferSize
            );

            if (mAudioRecord.getState() != AudioRecord.STATE_INITIALIZED) {
                Log.e(TAG, "AudioRecord initialization failed.");
                mIsRecording.set(false);
                return;
            }

            mAudioRecord.startRecording();
            mRecordThread = new Thread(() -> {
                byte[] buffer = new byte[2048];
                while (mIsRecording.get()) {
                    int read = mAudioRecord.read(buffer, 0, buffer.length);
                    if (read > 0 && mWebSocket != null) {
                        mWebSocket.send(ByteString.of(buffer, 0, read));
                        float rms = calculateRmsAmplitude(buffer, read);
                        mMainHandler.post(() -> {
                            if (mVisualContainer != null && mVisualContainer.getState() == IrisVisualContainer.STATE_LISTENING) {
                                mVisualContainer.setAudioAmplitude(rms);
                            }
                        });
                    }
                }
            }, "IrisAudioRecordThread");
            mRecordThread.start();
        } catch (SecurityException se) {
            Log.e(TAG, "Microphone permission denied: " + se.getMessage());
            mMainHandler.post(() -> {
                if (mVisualContainer != null) {
                    mVisualContainer.setState(IrisVisualContainer.STATE_ERROR);
                    mVisualContainer.setStatusText("Microphone permission denied");
                }
            });
        } catch (Exception e) {
            Log.e(TAG, "AudioRecord initialization error: " + e.getMessage(), e);
        }
    }

    private float calculateRmsAmplitude(byte[] data) {
        return calculateRmsAmplitude(data, data.length);
    }

    private float calculateRmsAmplitude(byte[] data, int length) {
        long sum = 0;
        int samples = length / 2;
        if (samples == 0) return 0.0f;

        for (int i = 0; i < length - 1; i += 2) {
            short sample = (short) ((data[i] & 0xFF) | (data[i + 1] << 8));
            sum += (long) sample * sample;
        }

        double rms = Math.sqrt((double) sum / samples);
        // Normalize 16-bit audio (0 - 32768) to 0.0 - 1.0 with soft knee curve
        float normalized = (float) (rms / 8000.0);
        return Math.min(1.0f, Math.max(0.0f, normalized));
    }

    public synchronized void stopSession() {
        if (!mIsActive.getAndSet(false)) return;

        Log.i(TAG, "Stopping ambient voice session, releasing audio hardware.");
        cancelFollowUpTimeout();
        mIsRecording.set(false);

        if (mRecordThread != null) {
            mRecordThread.interrupt();
            mRecordThread = null;
        }

        if (mAudioRecord != null) {
            try {
                if (mAudioRecord.getRecordingState() == AudioRecord.RECORDSTATE_RECORDING) {
                    mAudioRecord.stop();
                }
                mAudioRecord.release();
            } catch (Exception ignored) {}
            mAudioRecord = null;
        }

        if (mAudioTrack != null) {
            try {
                mAudioTrack.stop();
                mAudioTrack.release();
            } catch (Exception ignored) {}
            mAudioTrack = null;
        }

        if (mWebSocket != null) {
            try {
                mWebSocket.close(1000, "Turn completed");
            } catch (Exception ignored) {}
            mWebSocket = null;
        }

        mMainHandler.post(() -> {
            if (mVisualContainer != null) {
                mVisualContainer.setState(IrisVisualContainer.STATE_IDLE);
                mVisualContainer.setAudioAmplitude(0.0f);
            }
        });
    }

    public boolean isActive() {
        return mIsActive.get();
    }
}
