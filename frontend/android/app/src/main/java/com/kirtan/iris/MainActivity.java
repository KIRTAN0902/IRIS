package com.kirtan.iris;

import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    public static volatile boolean sPendingVoiceLaunch = false;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(PaymentPlugin.class);
        registerPlugin(AppLauncherPlugin.class);
        super.onCreate(savedInstanceState);
        handleVoiceIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
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
