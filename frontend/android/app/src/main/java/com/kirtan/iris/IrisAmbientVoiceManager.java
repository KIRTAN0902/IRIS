package com.kirtan.iris;

import android.app.Activity;
import android.content.Context;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.AudioTrack;
import android.media.MediaRecorder;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.util.Log;

import org.json.JSONArray;
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

public class IrisAmbientVoiceManager {

    private static final String TAG = "IRIS_AmbientVoice";
    private static final int SAMPLE_RATE = 24000;
    private static final String DEFAULT_WS_URL = "wss://irisai.runs-on.dev/api/voice/live";

    private final Context mContext;
    private final IrisOverlayView mOverlayView;
    private final Handler mMainHandler;

    private WebSocket mWebSocket;
    private AudioRecord mAudioRecord;
    private AudioTrack mAudioTrack;
    private Thread mRecordThread;

    private final AtomicBoolean mIsActive = new AtomicBoolean(false);
    private final AtomicBoolean mIsRecording = new AtomicBoolean(false);

    public IrisAmbientVoiceManager(Context context, IrisOverlayView overlayView) {
        this.mContext = context;
        this.mOverlayView = overlayView;
        this.mMainHandler = new Handler(Looper.getMainLooper());
    }

    public synchronized void startSession(String wsUrl) {
        if (mIsActive.getAndSet(true)) {
            Log.w(TAG, "Ambient voice session already active.");
            return;
        }

        String targetUrl = (wsUrl != null && !wsUrl.trim().isEmpty()) ? wsUrl : DEFAULT_WS_URL;
        Log.i(TAG, "Starting ambient voice session with endpoint: " + targetUrl);

        mOverlayView.setState(IrisOverlayView.STATE_ACTIVATING);
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
            .writeTimeout(10, TimeUnit.SECONDS)
            .build();

        Request request = new Request.Builder().url(url).build();
        mWebSocket = client.newWebSocket(request, new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                Log.i(TAG, "Ambient WebSocket connected.");
                mMainHandler.post(() -> {
                    mOverlayView.setState(IrisOverlayView.STATE_LISTENING);
                    mOverlayView.setStatusText("Listening...");
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
                            mOverlayView.setState(IrisOverlayView.STATE_LISTENING);
                            mOverlayView.setStatusText("Listening...");
                        });
                    } else if ("text".equals(type)) {
                        String txt = json.optString("text", "");
                        mMainHandler.post(() -> {
                            if (txt.length() < 50) {
                                mOverlayView.setStatusText(txt);
                            }
                        });
                    } else if ("launch_mobile_app".equals(type)) {
                        String app = json.optString("app", "");
                        mMainHandler.post(() -> {
                            mOverlayView.setState(IrisOverlayView.STATE_EXECUTING);
                            mOverlayView.setStatusText("Opening " + app + "...");
                            AppLauncherPlugin.launchAppDirect(mContext, app);
                        });
                    } else if ("request_screen_capture".equals(type)) {
                        mMainHandler.post(() -> {
                            mOverlayView.setState(IrisOverlayView.STATE_PROCESSING);
                            mOverlayView.setStatusText("Inspecting screen...");
                            // Screen capture request: send back image response
                            // If screen perception is needed, client returns image
                        });
                    } else if ("turn_complete".equals(type)) {
                        mMainHandler.post(() -> {
                            mOverlayView.setState(IrisOverlayView.STATE_LISTENING);
                            mOverlayView.setStatusText("Listening...");
                        });
                    }
                } catch (Exception e) {
                    Log.w(TAG, "Error parsing WebSocket text frame: " + e.getMessage());
                }
            }

            @Override
            public void onMessage(WebSocket webSocket, ByteString bytes) {
                byte[] rawAudio = bytes.toByteArray();
                if (mAudioTrack != null && rawAudio.length > 0) {
                    mAudioTrack.write(rawAudio, 0, rawAudio.length);
                    float amp = calculateRmsAmplitude(rawAudio);
                    mMainHandler.post(() -> {
                        mOverlayView.setState(IrisOverlayView.STATE_SPEAKING);
                        mOverlayView.setAudioAmplitude(amp);
                    });
                }
            }

            @Override
            public void onFailure(WebSocket webSocket, Throwable t, Response response) {
                Log.e(TAG, "WebSocket connection failure: " + t.getMessage());
                mMainHandler.post(() -> {
                    mOverlayView.setState(IrisOverlayView.STATE_ERROR);
                    mOverlayView.setStatusText("Connection error");
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

    private void startAudioRecording() {
        if (mIsRecording.getAndSet(true)) return;

        int bufferSize = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        );

        try {
            mAudioRecord = new AudioRecord(
                MediaRecorder.AudioSource.VOICE_RECOGNITION,
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                Math.max(bufferSize * 2, 4096)
            );

            mAudioRecord.startRecording();
            mRecordThread = new Thread(() -> {
                byte[] buffer = new byte[2048];
                while (mIsRecording.get()) {
                    int read = mAudioRecord.read(buffer, 0, buffer.length);
                    if (read > 0 && mWebSocket != null) {
                        mWebSocket.send(ByteString.of(buffer, 0, read));
                        float rms = calculateRmsAmplitude(buffer, read);
                        mMainHandler.post(() -> {
                            if (mOverlayView.getState() == IrisOverlayView.STATE_LISTENING) {
                                mOverlayView.setAudioAmplitude(rms);
                            }
                        });
                    }
                }
            }, "IrisAudioRecordThread");
            mRecordThread.start();
        } catch (SecurityException se) {
            Log.e(TAG, "Microphone permission denied: " + se.getMessage());
            mMainHandler.post(() -> {
                mOverlayView.setState(IrisOverlayView.STATE_ERROR);
                mOverlayView.setStatusText("Microphone permission denied");
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
        // Normalize 0..32767 to 0.0..1.0
        return (float) Math.min(1.0, rms / 8000.0);
    }

    public synchronized void stopSession() {
        if (!mIsActive.getAndSet(false)) return;
        Log.i(TAG, "Stopping ambient voice session.");

        mIsRecording.set(false);

        if (mRecordThread != null) {
            mRecordThread.interrupt();
            mRecordThread = null;
        }

        if (mAudioRecord != null) {
            try {
                mAudioRecord.stop();
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
                mWebSocket.close(1000, "Ambient session ended by user");
            } catch (Exception ignored) {}
            mWebSocket = null;
        }

        mOverlayView.dismiss();
    }
}
