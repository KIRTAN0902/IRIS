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
        // Check if intent or user preference delegates directly to floating sphere
        if (shouldDelegateToSphere(getIntent())) {
            Log.i(TAG, "Delegating activation directly to IrisSphereService without opening full app.");
            IrisSphereService.startSphere(this);
            moveTaskToBack(true);
            finish();
            super.onCreate(savedInstanceState);
            return;
        }

        registerPlugin(PaymentPlugin.class);
        registerPlugin(AppLauncherPlugin.class);
        registerPlugin(IrisAmbientPlugin.class);
        super.onCreate(savedInstanceState);
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
        if ("com.kirtan.iris.ACTION_SPHERE".equals(action) ||
            "com.kirtan.iris.ACTION_AMBIENT_VOICE".equals(action)) {
            return true;
        }

        if (intent.getBooleanExtra("open_sphere", false)) {
            return true;
        }

        // If user set "prefer floating sphere" and didn't explicitly request the dashboard
        if (!intent.getBooleanExtra("force_dashboard", false)) {
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
