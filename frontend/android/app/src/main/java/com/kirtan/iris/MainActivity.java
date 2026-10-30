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

        // Check if launch was triggered via gesture, lockscreen, or assistant invocation
        if (IrisApplication.isScreenOffGestureLaunch(getIntent(), this)) {
            Log.i(TAG, "Screen-off gesture / assist trigger detected. Starting IrisSphereService without opening full application.");
            IrisSphereService.startSphere(this);
            moveTaskToBack(true);
            finish();
            overridePendingTransition(0, 0);
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
        if (IrisApplication.isScreenOffGestureLaunch(intent, this)) {
            Log.i(TAG, "New intent delegated to IrisSphereService.");
            IrisSphereService.startSphere(this);
            moveTaskToBack(true);
            return;
        }
        handleVoiceIntent(intent);
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
