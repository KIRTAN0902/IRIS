package com.kirtan.iris;

import android.app.Application;
import android.app.KeyguardManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.graphics.Rect;
import android.os.SystemClock;
import android.util.Log;

/**
 * Custom Application class for IRIS.
 *
 * Tracks hardware screen and unlock state transitions to reliably distinguish
 * between:
 * 1. Screen-off gestures / lockscreen activations -> Launches native floating sphere.
 * 2. User tapping the application icon on the home screen -> Opens full React application.
 */
public class IrisApplication extends Application {

    private static final String TAG = "IRIS_Application";
    public static final String PREFS_NAME = "iris_settings";
    public static final String KEY_PREFER_SPHERE = "prefer_floating_sphere";

    private static volatile long sLastScreenOffTimestamp = 0;
    private static volatile long sLastScreenOnTimestamp = 0;
    private static volatile long sLastUnlockTimestamp = 0;

    @Override
    public void onCreate() {
        super.onCreate();
        registerScreenStateReceiver();
    }

    private void registerScreenStateReceiver() {
        IntentFilter filter = new IntentFilter();
        filter.addAction(Intent.ACTION_SCREEN_OFF);
        filter.addAction(Intent.ACTION_SCREEN_ON);
        filter.addAction(Intent.ACTION_USER_PRESENT);

        registerReceiver(new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                if (intent == null || intent.getAction() == null) return;
                long now = SystemClock.elapsedRealtime();
                switch (intent.getAction()) {
                    case Intent.ACTION_SCREEN_OFF:
                        sLastScreenOffTimestamp = now;
                        break;
                    case Intent.ACTION_SCREEN_ON:
                        sLastScreenOnTimestamp = now;
                        break;
                    case Intent.ACTION_USER_PRESENT:
                        sLastUnlockTimestamp = now;
                        Log.i(TAG, "Device unlocked by user. Timestamp: " + now);
                        break;
                }
            }
        }, filter);
    }

    /**
     * Determines whether an incoming launch Intent originated from a screen-off gesture,
     * lockscreen activation, or system assistant trigger, versus a deliberate home-screen tap.
     */
    public static boolean isScreenOffGestureLaunch(Intent intent, Context context) {
        if (intent == null) return false;

        String action = intent.getAction();

        // 1. Explicit sphere actions (shortcuts, quick tile, widget)
        if ("com.kirtan.iris.ACTION_SPHERE".equals(action) ||
            "com.kirtan.iris.ACTION_AMBIENT_VOICE".equals(action) ||
            Intent.ACTION_ASSIST.equals(action) ||
            "android.intent.action.VOICE_COMMAND".equals(action) ||
            intent.getBooleanExtra("open_sphere", false)) {
            Log.i(TAG, "Explicit sphere action detected: " + action);
            return true;
        }

        // 2. If the user explicitly launched with force_dashboard extra, always open dashboard
        if (intent.getBooleanExtra("force_dashboard", false)) {
            return false;
        }

        // 3. Check user preference (default: true for ambient experience)
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        boolean sphereEnabled = prefs.getBoolean(KEY_PREFER_SPHERE, true);
        if (!sphereEnabled) {
            return false;
        }

        // 4. Physical launcher icon tap detection:
        // Android and Realme Launcher ALWAYS set sourceBounds to the tapped icon's screen rect.
        Rect bounds = intent.getSourceBounds();
        if (bounds != null && !bounds.isEmpty()) {
            Log.i(TAG, "Launch has icon sourceBounds (" + bounds + ") -> Normal home-screen tap. Opening dashboard.");
            return false;
        }

        // 5. Check if the device was recently unlocked or screen recently turned on (screen-off gesture window)
        long now = SystemClock.elapsedRealtime();
        boolean justUnlocked = (sLastUnlockTimestamp > 0 && (now - sLastUnlockTimestamp) < 4500);
        boolean justScreenOn = (sLastScreenOnTimestamp > 0 && (now - sLastScreenOnTimestamp) < 5500);

        KeyguardManager km = (KeyguardManager) context.getSystemService(Context.KEYGUARD_SERVICE);
        boolean isKeyguardActive = (km != null && (km.isKeyguardLocked() || km.isDeviceLocked()));

        Log.i(TAG, "Screen-off check: justUnlocked=" + justUnlocked +
                   ", justScreenOn=" + justScreenOn +
                   ", isKeyguardActive=" + isKeyguardActive +
                   ", boundsNull=" + (bounds == null) +
                   ", timeSinceUnlock=" + (sLastUnlockTimestamp > 0 ? (now - sLastUnlockTimestamp) : -1) + "ms");

        if (justUnlocked || justScreenOn || isKeyguardActive) {
            return true;
        }

        // 6. Cold-start gesture fallback:
        // If launched via MAIN/LAUNCHER intent without sourceBounds, it's a system gesture launch
        if (Intent.ACTION_MAIN.equals(action) && bounds == null) {
            Log.i(TAG, "ACTION_MAIN without sourceBounds -> Detected system gesture trigger.");
            return true;
        }

        return false;
    }
}
