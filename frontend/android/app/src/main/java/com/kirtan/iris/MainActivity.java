package com.kirtan.iris;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    private static final String TAG = "IRIS_MainActivity";
    private static final String PREFS_NAME = "iris_settings";
    private static final String KEY_PREFER_SPHERE = "prefer_floating_sphere";

    public static volatile boolean sPendingVoiceLaunch = false;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(PaymentPlugin.class);
        registerPlugin(AppLauncherPlugin.class);
        registerPlugin(IrisAmbientPlugin.class);
        super.onCreate(savedInstanceState);

        // Check if intent explicitly requested ambient sphere mode
        if (shouldDelegateToSphere(getIntent())) {
            Log.i(TAG, "Delegating activation directly to IrisSphereService without opening full app.");
            IrisSphereService.startSphere(this);
            moveTaskToBack(true);
            finish();
            return;
        }

        // Request microphone permission on first app launch if not yet granted
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
        if (shouldDelegateToSphere(intent)) {
            Log.i(TAG, "New intent delegated to IrisSphereService.");
            IrisSphereService.startSphere(this);
            moveTaskToBack(true);
            return;
        }
        handleVoiceIntent(intent);
    }

    private boolean shouldDelegateToSphere(Intent intent) {
        if (intent == null) return false;

        String action = intent.getAction();

        // 1. Normal app launcher clicks from home screen MUST ALWAYS open the dashboard!
        if (Intent.ACTION_MAIN.equals(action) && intent.hasCategory(Intent.CATEGORY_LAUNCHER)) {
            return false;
        }

        // 2. Explicit sphere actions
        if ("com.kirtan.iris.ACTION_SPHERE".equals(action)) {
            return true;
        }

        if (intent.getBooleanExtra("open_sphere", false)) {
            return true;
        }

        // 3. Ambient voice or assist intent delegation if user prefers sphere mode
        if ("com.kirtan.iris.ACTION_AMBIENT_VOICE".equals(action) ||
            Intent.ACTION_ASSIST.equals(action) ||
            "android.intent.action.VOICE_COMMAND".equals(action)) {
            SharedPreferences prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
            return prefs.getBoolean(KEY_PREFER_SPHERE, false);
        }

        return false;
    }

    private void handleVoiceIntent(Intent intent) {
        if (intent != null && "voice".equals(intent.getStringExtra("action"))) {
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
