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
import android.util.Log;
import android.view.Gravity;
import android.view.WindowManager;

import androidx.core.app.NotificationCompat;

public class IrisAmbientService extends Service {

    private static final String TAG = "IRIS_AmbientService";
    private static final String CHANNEL_ID = "iris_ambient_channel";
    private static final int NOTIFICATION_ID = 2026;

    public static final String ACTION_START_AMBIENT = "com.kirtan.iris.START_AMBIENT";
    public static final String ACTION_STOP_AMBIENT = "com.kirtan.iris.STOP_AMBIENT";

    private WindowManager mWindowManager;
    private IrisOverlayView mOverlayView;
    private IrisAmbientVoiceManager mVoiceManager;
    private boolean mIsOverlayAttached = false;

    public static void startAmbient(Context context) {
        Intent intent = new Intent(context, IrisAmbientService.class);
        intent.setAction(ACTION_START_AMBIENT);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(intent);
        } else {
            context.startService(intent);
        }
    }

    public static void stopAmbient(Context context) {
        Intent intent = new Intent(context, IrisAmbientService.class);
        intent.setAction(ACTION_STOP_AMBIENT);
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

        if (ACTION_STOP_AMBIENT.equals(action)) {
            stopAmbientSession();
            stopSelf();
            return START_NOT_STICKY;
        }

        startForegroundNotification();
        showAmbientOverlay();

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
            .setContentTitle("IRIS Ambient Assistant")
            .setContentText("Listening and ready...")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .setContentIntent(pi);

        Notification notification = builder.build();

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            int serviceType = ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE;
            startForeground(NOTIFICATION_ID, notification, serviceType);
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }
    }

    private void showAmbientOverlay() {
        if (mIsOverlayAttached) return;

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
            Log.w(TAG, "Cannot draw overlays: permission not granted.");
            // If overlay permission not granted, fallback to opening AssistantActivity
            Intent intent = new Intent(this, AssistantActivity.class);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
            stopSelf();
            return;
        }

        mOverlayView = new IrisOverlayView(this);
        mVoiceManager = new IrisAmbientVoiceManager(this, mOverlayView);

        mOverlayView.setOnDismissListener(() -> {
            stopAmbientSession();
            stopSelf();
        });

        int layoutType;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            layoutType = WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY;
        } else {
            layoutType = WindowManager.LayoutParams.TYPE_PHONE;
        }

        WindowManager.LayoutParams params = new WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            layoutType,
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN |
            WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS |
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE |
            WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS,
            PixelFormat.TRANSLUCENT
        );
        params.gravity = Gravity.TOP | Gravity.START;

        try {
            mWindowManager.addView(mOverlayView, params);
            mIsOverlayAttached = true;
            mVoiceManager.startSession(null);
        } catch (Exception e) {
            Log.e(TAG, "Failed to attach overlay view: " + e.getMessage(), e);
            stopSelf();
        }
    }

    private void stopAmbientSession() {
        if (mVoiceManager != null) {
            mVoiceManager.stopSession();
            mVoiceManager = null;
        }

        if (mIsOverlayAttached && mOverlayView != null) {
            try {
                mWindowManager.removeView(mOverlayView);
            } catch (Exception ignored) {}
            mIsOverlayAttached = false;
            mOverlayView = null;
        }

        stopForeground(true);
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "IRIS Ambient Assistant",
                NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("Background ambient assistant status indicator");
            channel.setShowBadge(false);
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                nm.createNotificationChannel(channel);
            }
        }
    }

    @Override
    public void onDestroy() {
        stopAmbientSession();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
