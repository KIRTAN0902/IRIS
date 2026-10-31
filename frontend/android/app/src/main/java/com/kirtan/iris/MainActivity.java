package com.kirtan.iris;

import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import com.getcapacitor.BridgeActivity;

/**
 * The full IRIS dashboard. It is intentionally not part of assistant
 * activation: the launcher icon always opens this activity, and the assistant
 * session is hosted by Android's VoiceInteractionService.
 */
public class MainActivity extends BridgeActivity {

    private static final String TAG = "IRIS_MainActivity";

    public static volatile boolean sPendingVoiceLaunch = false;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(PaymentPlugin.class);
        registerPlugin(AppLauncherPlugin.class);
        registerPlugin(IrisAmbientPlugin.class);
        super.onCreate(savedInstanceState);

        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.M) {
            if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{android.Manifest.permission.RECORD_AUDIO}, 101);
            }
        }

        handleVoiceIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleVoiceIntent(intent);
    }

    private void handleVoiceIntent(Intent intent) {
        if (intent != null && "voice".equals(intent.getStringExtra("action"))) {
            Log.i(TAG, "In-app voice shortcut requested");
            sPendingVoiceLaunch = true;
            scheduleVoiceDispatches();
        }
    }

    private void scheduleVoiceDispatches() {
        Handler handler = new Handler(Looper.getMainLooper());
        int[] delays = {300, 800, 1800, 3000, 5000};
        for (int delay : delays) {
            handler.postDelayed(() -> {
                if (getBridge() != null && getBridge().getWebView() != null) {
                    getBridge().getWebView().evaluateJavascript(
                        "window.__IRIS_AUTO_VOICE__ = true; window.dispatchEvent(new CustomEvent('iris-auto-voice'));",
                        null
                    );
                }
            }, delay);
        }
    }
}
