package com.kirtan.iris;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.PixelCopy;
import android.view.Window;
import android.view.WindowManager;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;

/**
 * Universal Android Hardware Screen Capture Engine for IRIS Screen Perception.
 *
 * Implements resilient multi-tier capture:
 * 1. Native Digital Assistant OS Screenshot (VoiceInteractionSession.onHandleScreenshot) - 0ms latency.
 * 2. Android MediaProjection Hardware Buffer (VirtualDisplay + ImageReader) across all third-party apps.
 * 3. Surface PixelCopy fallback.
 *
 * Preserves the Zero-Image-Storage guarantee:
 * Bitmaps exist in RAM only and are compressed directly into ephemeral JPEG streams.
 */
public class IrisScreenCaptureManager {

    private static final String TAG = "IRIS_ScreenCapture";

    // In-memory cache for digital assistant session screenshots
    public static volatile Bitmap sLatestAssistScreenshot = null;
    public static volatile long sLatestAssistScreenshotTimestamp = 0;

    // MediaProjection state
    public static volatile MediaProjection sMediaProjection = null;
    public static volatile Intent sProjectionData = null;
    public static volatile int sProjectionResultCode = 0;

    public interface CaptureCallback {
        void onSuccess(Bitmap bitmap, String base64Jpeg);
        void onError(String errorMessage);
    }

    public static void setAssistScreenshot(Bitmap screenshot) {
        if (screenshot != null) {
            sLatestAssistScreenshot = screenshot;
            sLatestAssistScreenshotTimestamp = System.currentTimeMillis();
            Log.i(TAG, "Stored fresh OS assist screenshot: " + screenshot.getWidth() + "x" + screenshot.getHeight());
        }
    }

    public static void captureCurrentDisplay(Context context, CaptureCallback callback) {
        Handler mainHandler = new Handler(Looper.getMainLooper());

        // 1. Check if we have a fresh assist screenshot from the OS (within 30 seconds)
        long now = System.currentTimeMillis();
        if (sLatestAssistScreenshot != null && (now - sLatestAssistScreenshotTimestamp) < 30000) {
            Bitmap bmp = sLatestAssistScreenshot;
            Log.i(TAG, "Serving fresh OS assist screenshot (<30s old)");
            encodeAndDeliver(bmp, callback);
            return;
        }

        // 2. Try MediaProjection if active
        if (sMediaProjection != null) {
            captureViaMediaProjection(context, sMediaProjection, callback);
            return;
        }

        // 3. Fallback: try capturing active window via PixelCopy if context is Activity
        if (context instanceof Activity) {
            Activity act = (Activity) context;
            captureViaActivityPixelCopy(act, callback);
            return;
        }

        // 4. If nothing else is available, notify callback
        mainHandler.post(() -> {
            callback.onError("Screen capture permission required. Please grant MediaProjection or invoke IRIS as the Default Digital Assistant.");
        });
    }

    public static void captureViaActivityPixelCopy(Activity activity, CaptureCallback callback) {
        Window window = activity.getWindow();
        if (window == null) {
            callback.onError("Activity window unavailable for PixelCopy");
            return;
        }

        int width = window.getDecorView().getWidth();
        int height = window.getDecorView().getHeight();
        if (width <= 0 || height <= 0) {
            DisplayMetrics dm = activity.getResources().getDisplayMetrics();
            width = dm.widthPixels;
            height = dm.heightPixels;
        }

        final Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            try {
                PixelCopy.request(
                    window,
                    bitmap,
                    copyResult -> {
                        if (copyResult == PixelCopy.SUCCESS) {
                            encodeAndDeliver(bitmap, callback);
                        } else {
                            callback.onError("PixelCopy failed with result: " + copyResult);
                        }
                    },
                    new Handler(Looper.getMainLooper())
                );
                return;
            } catch (Exception e) {
                Log.w(TAG, "PixelCopy request failed: " + e.getMessage());
            }
        }

        callback.onError("PixelCopy unsupported or failed on this Android version");
    }

    public static void captureViaMediaProjection(Context context, MediaProjection projection, CaptureCallback callback) {
        WindowManager wm = (WindowManager) context.getSystemService(Context.WINDOW_SERVICE);
        DisplayMetrics metrics = new DisplayMetrics();
        if (wm != null && wm.getDefaultDisplay() != null) {
            wm.getDefaultDisplay().getRealMetrics(metrics);
        } else {
            metrics = context.getResources().getDisplayMetrics();
        }

        int width = metrics.widthPixels;
        int height = metrics.heightPixels;
        int density = metrics.densityDpi;

        ImageReader imageReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2);
        Handler handler = new Handler(Looper.getMainLooper());

        VirtualDisplay virtualDisplay = projection.createVirtualDisplay(
            "IrisScreenPerception",
            width,
            height,
            density,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader.getSurface(),
            null,
            handler
        );

        imageReader.setOnImageAvailableListener(reader -> {
            Image image = null;
            try {
                image = reader.acquireLatestImage();
                if (image != null) {
                    Image.Plane[] planes = image.getPlanes();
                    ByteBuffer buffer = planes[0].getBuffer();
                    int pixelStride = planes[0].getPixelStride();
                    int rowStride = planes[0].getRowStride();
                    int rowPadding = rowStride - pixelStride * width;

                    Bitmap bitmap = Bitmap.createBitmap(
                        width + rowPadding / pixelStride,
                        height,
                        Bitmap.Config.ARGB_8888
                    );
                    bitmap.copyPixelsFromBuffer(buffer);

                    // Crop out row padding if necessary
                    Bitmap cleanBitmap = Bitmap.createBitmap(bitmap, 0, 0, width, height);

                    virtualDisplay.release();
                    imageReader.close();

                    encodeAndDeliver(cleanBitmap, callback);
                }
            } catch (Exception e) {
                Log.e(TAG, "Error acquiring image from VirtualDisplay: " + e.getMessage(), e);
                callback.onError("Image capture processing error: " + e.getMessage());
            } finally {
                if (image != null) {
                    image.close();
                }
            }
        }, handler);
    }

    private static void encodeAndDeliver(Bitmap bitmap, CaptureCallback callback) {
        Handler mainHandler = new Handler(Looper.getMainLooper());
        new Thread(() -> {
            try {
                ByteArrayOutputStream baos = new ByteArrayOutputStream();
                bitmap.compress(Bitmap.CompressFormat.JPEG, 85, baos);
                byte[] jpegBytes = baos.toByteArray();
                String base64Jpeg = "data:image/jpeg;base64," + Base64.encodeToString(jpegBytes, Base64.NO_WRAP);

                mainHandler.post(() -> callback.onSuccess(bitmap, base64Jpeg));
            } catch (Exception e) {
                mainHandler.post(() -> callback.onError("Failed to encode JPEG: " + e.getMessage()));
            }
        }).start();
    }
}
