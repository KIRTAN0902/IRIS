package com.kirtan.iris;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Rect;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkInfo;
import android.net.Uri;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import android.provider.Settings;
import android.util.Base64;
import android.util.Log;
import android.view.PixelCopy;
import android.view.View;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.io.ByteArrayOutputStream;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@CapacitorPlugin(name = "AppLauncher")
public class AppLauncherPlugin extends Plugin {

    private static final String TAG = "IRIS_AppLauncher";

    // Fast-lookup dictionary for common Indian and global app names
    private static final Map<String, String> COMMON_PACKAGES = new HashMap<>();

    static {
        COMMON_PACKAGES.put("spotify", "com.spotify.music");
        COMMON_PACKAGES.put("whatsapp", "com.whatsapp");
        COMMON_PACKAGES.put("youtube", "com.google.android.youtube");
        COMMON_PACKAGES.put("instagram", "com.instagram.android");
        COMMON_PACKAGES.put("chrome", "com.android.chrome");
        COMMON_PACKAGES.put("maps", "com.google.android.apps.maps");
        COMMON_PACKAGES.put("google maps", "com.google.android.apps.maps");
        COMMON_PACKAGES.put("gmail", "com.google.android.gm");
        COMMON_PACKAGES.put("calculator", "com.google.android.calculator");
        COMMON_PACKAGES.put("settings", "com.android.settings");
        COMMON_PACKAGES.put("gpay", "com.google.android.apps.nbu.paisa.user");
        COMMON_PACKAGES.put("google pay", "com.google.android.apps.nbu.paisa.user");
        COMMON_PACKAGES.put("phonepe", "com.phonepe.app");
        COMMON_PACKAGES.put("paytm", "net.one97.paytm");
        COMMON_PACKAGES.put("cred", "com.dreamplug.androidapp");
        COMMON_PACKAGES.put("swiggy", "in.swiggy.android");
        COMMON_PACKAGES.put("zomato", "com.application.zomato");
        COMMON_PACKAGES.put("zepto", "com.zeptoconsumerapp");
        COMMON_PACKAGES.put("blinkit", "com.grofers.customerapp");
        COMMON_PACKAGES.put("uber", "com.ubercab");
        COMMON_PACKAGES.put("ola", "com.olacabs.customer");
        COMMON_PACKAGES.put("rapido", "com.rapido.passenger");
        COMMON_PACKAGES.put("telegram", "org.telegram.messenger");
        COMMON_PACKAGES.put("twitter", "com.twitter.android");
        COMMON_PACKAGES.put("x", "com.twitter.android");
        COMMON_PACKAGES.put("linkedin", "com.linkedin.android");
        COMMON_PACKAGES.put("netflix", "com.netflix.mediaclient");
        COMMON_PACKAGES.put("amazon", "in.amazon.mShop.android.shopping");
    }

    @PluginMethod
    public void launchApp(PluginCall call) {
        String appQuery = call.getString("appName");
        if (appQuery == null || appQuery.trim().isEmpty()) {
            call.reject("appName parameter is required");
            return;
        }

        String query = appQuery.trim().toLowerCase();
        Context context = getContext();
        PackageManager pm = context.getPackageManager();

        // 1. Handle special hardware actions (camera, settings)
        if (query.equals("camera") || query.equals("open camera")) {
            try {
                Intent cameraIntent = new Intent(MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA);
                cameraIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(cameraIntent);
                JSObject ret = new JSObject();
                ret.put("success", true);
                ret.put("app", "Camera");
                call.resolve(ret);
                return;
            } catch (Exception e) {
                Log.w(TAG, "Standard camera intent failed, falling back to package search");
            }
        }

        if (query.equals("settings") || query.equals("open settings")) {
            try {
                Intent settingsIntent = new Intent(Settings.ACTION_SETTINGS);
                settingsIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(settingsIntent);
                JSObject ret = new JSObject();
                ret.put("success", true);
                ret.put("app", "Settings");
                call.resolve(ret);
                return;
            } catch (Exception e) {
                Log.w(TAG, "Settings intent failed");
            }
        }

        if (query.equals("app_settings") || query.equals("app settings") || query.equals("permissions") || query.equals("app permissions")) {
            try {
                Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
                intent.setData(Uri.parse("package:" + context.getPackageName()));
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(intent);
                JSObject ret = new JSObject();
                ret.put("success", true);
                ret.put("app", "App Details Settings");
                call.resolve(ret);
                return;
            } catch (Exception e) {
                Log.w(TAG, "Application details settings intent failed", e);
            }
        }

        // 2. Check known aliases
        String targetPackage = COMMON_PACKAGES.get(query);

        // 3. If not in alias list, search installed apps dynamically by label
        if (targetPackage == null || !isPackageInstalled(pm, targetPackage)) {
            targetPackage = findPackageByLabel(pm, query);
        }

        if (targetPackage == null) {
            JSObject ret = new JSObject();
            ret.put("success", false);
            ret.put("error", "App '" + appQuery + "' was not found on this phone.");
            call.resolve(ret);
            return;
        }

        try {
            Intent launchIntent = pm.getLaunchIntentForPackage(targetPackage);
            if (launchIntent != null) {
                launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(launchIntent);
                JSObject ret = new JSObject();
                ret.put("success", true);
                ret.put("app", appQuery);
                ret.put("package", targetPackage);
                call.resolve(ret);
            } else {
                JSObject ret = new JSObject();
                ret.put("success", false);
                ret.put("error", "Cannot launch app '" + targetPackage + "' (no launchable activity).");
                call.resolve(ret);
            }
        } catch (Exception e) {
            Log.e(TAG, "Error launching package: " + targetPackage, e);
            call.reject("Failed to launch " + appQuery + ": " + e.getMessage());
        }
    }

    @PluginMethod
    public void getInstalledApps(PluginCall call) {
        Context context = getContext();
        PackageManager pm = context.getPackageManager();
        List<ApplicationInfo> apps = pm.getInstalledApplications(PackageManager.GET_META_DATA);

        JSArray appList = new JSArray();
        for (ApplicationInfo info : apps) {
            // Only list launchable apps (skip system background services)
            if (pm.getLaunchIntentForPackage(info.packageName) != null) {
                JSObject obj = new JSObject();
                obj.put("name", info.loadLabel(pm).toString());
                obj.put("package", info.packageName);
                appList.put(obj);
            }
        }

        JSObject ret = new JSObject();
        ret.put("apps", appList);
        call.resolve(ret);
    }

    @PluginMethod
    public void openAppSettings(PluginCall call) {
        Context context = getContext();
        try {
            Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
            intent.setData(Uri.parse("package:" + context.getPackageName()));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
            JSObject ret = new JSObject();
            ret.put("success", true);
            call.resolve(ret);
        } catch (Exception e) {
            call.reject("Could not open app settings: " + e.getMessage());
        }
    }

    @PluginMethod
    public void openAssistantSettings(PluginCall call) {
        Context context = getContext();
        try {
            Intent intent = new Intent(Settings.ACTION_VOICE_INPUT_SETTINGS);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
            JSObject ret = new JSObject();
            ret.put("success", true);
            call.resolve(ret);
        } catch (Exception e) {
            try {
                Intent fallback = new Intent(Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS);
                fallback.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(fallback);
                JSObject ret = new JSObject();
                ret.put("success", true);
                call.resolve(ret);
            } catch (Exception e2) {
                call.reject("Could not open assistant settings: " + e2.getMessage());
            }
        }
    }

    @PluginMethod
    public void isVoicePending(PluginCall call) {
        boolean pending = MainActivity.sPendingVoiceLaunch;
        MainActivity.sPendingVoiceLaunch = false;
        JSObject ret = new JSObject();
        ret.put("pending", pending);
        call.resolve(ret);
    }

    @PluginMethod
    public void openUrl(PluginCall call) {
        String urlString = call.getString("url");
        if (urlString == null || urlString.trim().isEmpty()) {
            call.reject("url parameter is required");
            return;
        }
        try {
            Context context = getContext();
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(urlString.trim()));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
            JSObject ret = new JSObject();
            ret.put("success", true);
            ret.put("url", urlString);
            call.resolve(ret);
        } catch (Exception e) {
            Log.e(TAG, "Failed to open URL: " + urlString, e);
            call.reject("Failed to open URL: " + e.getMessage());
        }
    }

    @PluginMethod
    public void getBatteryStatus(PluginCall call) {
        try {
            Context context = getContext();
            IntentFilter ifilter = new IntentFilter(Intent.ACTION_BATTERY_CHANGED);
            Intent batteryStatus = context.registerReceiver(null, ifilter);
            int level = -1;
            int scale = -1;
            boolean isCharging = false;
            if (batteryStatus != null) {
                level = batteryStatus.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
                scale = batteryStatus.getIntExtra(BatteryManager.EXTRA_SCALE, -1);
                int status = batteryStatus.getIntExtra(BatteryManager.EXTRA_STATUS, -1);
                isCharging = status == BatteryManager.BATTERY_STATUS_CHARGING ||
                             status == BatteryManager.BATTERY_STATUS_FULL;
            }
            int batteryPct = (level >= 0 && scale > 0) ? (int) ((level / (float) scale) * 100) : -1;
            JSObject ret = new JSObject();
            ret.put("success", true);
            ret.put("battery_level", batteryPct);
            ret.put("is_charging", isCharging);
            call.resolve(ret);
        } catch (Exception e) {
            call.reject("Failed to get battery status: " + e.getMessage());
        }
    }

    @PluginMethod
    public void getNetworkStatus(PluginCall call) {
        try {
            Context context = getContext();
            ConnectivityManager cm = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
            boolean isConnected = false;
            String connectionType = "none";
            if (cm != null) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    Network activeNet = cm.getActiveNetwork();
                    if (activeNet != null) {
                        NetworkCapabilities caps = cm.getNetworkCapabilities(activeNet);
                        if (caps != null) {
                            isConnected = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
                            if (caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) {
                                connectionType = "wifi";
                            } else if (caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)) {
                                connectionType = "cellular";
                            } else if (caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)) {
                                connectionType = "ethernet";
                            }
                        }
                    }
                } else {
                    NetworkInfo activeInfo = cm.getActiveNetworkInfo();
                    if (activeInfo != null && activeInfo.isConnected()) {
                        isConnected = true;
                        connectionType = activeInfo.getTypeName().toLowerCase();
                    }
                }
            }
            JSObject ret = new JSObject();
            ret.put("success", true);
            ret.put("connected", isConnected);
            ret.put("connection_type", connectionType);
            call.resolve(ret);
        } catch (Exception e) {
            call.reject("Failed to get network status: " + e.getMessage());
        }
    }

    @PluginMethod
    public void captureScreen(PluginCall call) {
        Activity activity = getActivity();
        if (activity == null || activity.getWindow() == null) {
            call.reject("Activity or Window is not available");
            return;
        }

        View decorView = activity.getWindow().getDecorView();
        int width = decorView.getWidth();
        int height = decorView.getHeight();

        if (width <= 0 || height <= 0) {
            width = 1080;
            height = 1920;
        }

        final Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        int[] location = new int[2];
        decorView.getLocationInWindow(location);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            try {
                PixelCopy.request(
                    activity.getWindow(),
                    new Rect(location[0], location[1], location[0] + width, location[1] + height),
                    bitmap,
                    copyResult -> {
                        if (copyResult == PixelCopy.SUCCESS) {
                            returnBitmapAsBase64(bitmap, call);
                        } else {
                            fallbackViewDraw(decorView, bitmap, call);
                        }
                    },
                    new Handler(Looper.getMainLooper())
                );
                return;
            } catch (Exception e) {
                Log.w(TAG, "PixelCopy request failed, falling back to Canvas draw", e);
            }
        }

        fallbackViewDraw(decorView, bitmap, call);
    }

    private void fallbackViewDraw(View view, Bitmap bitmap, PluginCall call) {
        try {
            Canvas canvas = new Canvas(bitmap);
            view.draw(canvas);
            returnBitmapAsBase64(bitmap, call);
        } catch (Exception e) {
            call.reject("Failed to capture screen view: " + e.getMessage());
        }
    }

    private void returnBitmapAsBase64(Bitmap bitmap, PluginCall call) {
        try {
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            bitmap.compress(Bitmap.CompressFormat.JPEG, 85, baos);
            byte[] imageBytes = baos.toByteArray();
            String base64Image = "data:image/jpeg;base64," + Base64.encodeToString(imageBytes, Base64.NO_WRAP);

            JSObject ret = new JSObject();
            ret.put("success", true);
            ret.put("image_base64", base64Image);
            ret.put("mime_type", "image/jpeg");
            call.resolve(ret);
        } catch (Exception e) {
            call.reject("Error encoding bitmap: " + e.getMessage());
        }
    }

    private boolean isPackageInstalled(PackageManager pm, String packageName) {
        try {
            pm.getPackageInfo(packageName, 0);
            return true;
        } catch (PackageManager.NameNotFoundException e) {
            return false;
        }
    }

    private String findPackageByLabel(PackageManager pm, String query) {
        List<ApplicationInfo> packages = pm.getInstalledApplications(PackageManager.GET_META_DATA);
        for (ApplicationInfo info : packages) {
            String label = info.loadLabel(pm).toString().toLowerCase();
            if (label.contains(query) || query.contains(label)) {
                if (pm.getLaunchIntentForPackage(info.packageName) != null) {
                    return info.packageName;
                }
            }
        }
        return null;
    }
}
