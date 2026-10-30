package com.kirtan.iris;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.PixelFormat;
import android.os.Build;
import android.os.IBinder;
import android.provider.Settings;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.Gravity;
import android.view.WindowManager;

import androidx.core.app.NotificationCompat;

/**
 * Native Android Floating Sphere Service for IRIS.
 *
 * Hosts the compact floating IrisSphereView directly on WindowManager as TYPE_APPLICATION_OVERLAY.
 * Automatically activates voice streaming and microphone capture immediately upon appearance.
 */
public class IrisSphereService extends Service implements IrisSphereView.OnSphereInteractionListener {

    private static final String TAG = "IRIS_SphereService";
    private static final String CHANNEL_ID = "iris_sphere_channel";
    private static final int NOTIFICATION_ID = 2027;

    public static final String ACTION_START_SPHERE = "com.kirtan.iris.START_SPHERE";
    public static final String ACTION_STOP_SPHERE = "com.kirtan.iris.STOP_SPHERE";

    private WindowManager mWindowManager;
    private IrisSphereView mSphereView;
    private WindowManager.LayoutParams mLayoutParams;
    private IrisAmbientVoiceManager mVoiceManager;
    private boolean mIsViewAttached = false;

    public static void startSphere(Context context) {
        Intent intent = new Intent(context, IrisSphereService.class);
        intent.setAction(ACTION_START_SPHERE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(intent);
        } else {
            context.startService(intent);
        }
    }

    public static void stopSphere(Context context) {
        Intent intent = new Intent(context, IrisSphereService.class);
        intent.setAction(ACTION_STOP_SPHERE);
        context.startService(intent);
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        mWindowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent != null ? intent.getAction() : null;

        if (ACTION_STOP_SPHERE.equals(action)) {
            dismissAndStop();
            return START_NOT_STICKY;
        }

        startForegroundNotification();
        showFloatingSphere();

        return START_NOT_STICKY;
    }

    private void startForegroundNotification() {
        Intent contentIntent = new Intent(this, MainActivity.class);
        int piFlags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            piFlags |= PendingIntent.FLAG_IMMUTABLE;
        }
        PendingIntent pi = PendingIntent.getActivity(this, 0, contentIntent, piFlags);

        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("IRIS Voice Sphere")
            .setContentText("Listening and ready...")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .setContentIntent(pi);

        Notification notification = builder.build();

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }
    }

    private void showFloatingSphere() {
        if (mIsViewAttached) return;

        // Verify overlay permission
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
            Log.w(TAG, "SYSTEM_ALERT_WINDOW permission not granted. Falling back to AssistantActivity.");
            Intent assistIntent = new Intent(this, IrisSphereActivity.class);
            assistIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(assistIntent);
            stopSelf();
            return;
        }

        int overlayType = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            : WindowManager.LayoutParams.TYPE_PHONE;

        int windowFlags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
            | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
            | WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED;

        DisplayMetrics dm = getResources().getDisplayMetrics();
        int sphereSize = (int) (88 * dm.density);

        mLayoutParams = new WindowManager.LayoutParams(
            sphereSize,
            sphereSize,
            overlayType,
            windowFlags,
            PixelFormat.TRANSLUCENT
        );

        mLayoutParams.gravity = Gravity.TOP | Gravity.START;
        // Default position: top right edge of screen
        mLayoutParams.x = dm.widthPixels - sphereSize - 16;
        mLayoutParams.y = (int) (dm.heightPixels * 0.28f);

        mSphereView = new IrisSphereView(this);
        mSphereView.setWindowManagerParams(mWindowManager, mLayoutParams);
        mSphereView.setOnSphereInteractionListener(this);

        try {
            mWindowManager.addView(mSphereView, mLayoutParams);
            mIsViewAttached = true;
            Log.i(TAG, "IrisSphereView attached to WindowManager successfully.");

            // Initialize Voice Session and IMMEDIATELY START LISTENING
            mVoiceManager = new IrisAmbientVoiceManager(this, mSphereView);
            mVoiceManager.startSession(null);
            Log.i(TAG, "IrisAmbientVoiceManager started automatic listening session.");
        } catch (Exception e) {
            Log.e(TAG, "Failed to attach IrisSphereView: " + e.getMessage(), e);
            stopSelf();
        }
    }

    @Override
    public void onSphereTapped() {
        Log.i(TAG, "Sphere tapped by user.");
        if (mVoiceManager != null) {
            if (mSphereView.getState() == IrisVisualContainer.STATE_SPEAKING) {
                // User interrupted: stop speaking, start listening
                mSphereView.setState(IrisVisualContainer.STATE_LISTENING);
            } else if (mSphereView.getState() == IrisVisualContainer.STATE_IDLE) {
                // Wake up and listen
                mVoiceManager.startSession(null);
            }
        }
    }

    @Override
    public void onSphereDismissed() {
        dismissAndStop();
    }

    @Override
    public void onSphereMoved(int x, int y) {
        // Position updated
    }

    private void dismissAndStop() {
        if (mVoiceManager != null) {
            mVoiceManager.stopSession();
        }

        if (mIsViewAttached && mSphereView != null && mWindowManager != null) {
            try {
                mWindowManager.removeView(mSphereView);
            } catch (Exception ignored) {}
            mIsViewAttached = false;
        }

        stopForeground(true);
        stopSelf();
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "IRIS Voice Sphere",
                NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("Shows active status of the floating IRIS assistant.");
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                nm.createNotificationChannel(channel);
            }
        }
    }

    @Override
    public void onDestroy() {
        dismissAndStop();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
