package com.kirtan.iris;

import android.app.role.RoleManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.util.Log;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "IrisAmbient")
public class IrisAmbientPlugin extends Plugin {

    private static final String TAG = "IRIS_AmbientPlugin";
    private static final String PREFS_NAME = "iris_settings";
    private static final String KEY_PREFER_SPHERE = "prefer_floating_sphere";

    @PluginMethod
    public void isAssistantRoleGranted(PluginCall call) {
        Context context = getContext();
        boolean isAssistant = false;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            RoleManager roleManager = (RoleManager) context.getSystemService(Context.ROLE_SERVICE);
            if (roleManager != null) {
                isAssistant = roleManager.isRoleHeld(RoleManager.ROLE_ASSISTANT);
            }
        }
        JSObject ret = new JSObject();
        ret.put("granted", isAssistant);
        call.resolve(ret);
    }

    @PluginMethod
    public void requestAssistantRole(PluginCall call) {
        Context context = getContext();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            RoleManager roleManager = (RoleManager) context.getSystemService(Context.ROLE_SERVICE);
            if (roleManager != null && roleManager.isRoleAvailable(RoleManager.ROLE_ASSISTANT)) {
                Intent intent = roleManager.createRequestRoleIntent(RoleManager.ROLE_ASSISTANT);
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(intent);
                JSObject ret = new JSObject();
                ret.put("success", true);
                ret.put("method", "role_manager");
                call.resolve(ret);
                return;
            }
        }

        // Fallback to Voice Input settings
        try {
            Intent intent = new Intent(Settings.ACTION_VOICE_INPUT_SETTINGS);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
            JSObject ret = new JSObject();
            ret.put("success", true);
            ret.put("method", "voice_input_settings");
            call.resolve(ret);
        } catch (Exception e) {
            Log.e(TAG, "Failed to open assistant settings: " + e.getMessage());
            call.reject("Could not open assistant settings: " + e.getMessage());
        }
    }

    @PluginMethod
    public void hasOverlayPermission(PluginCall call) {
        Context context = getContext();
        boolean canDraw = true;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            canDraw = Settings.canDrawOverlays(context);
        }
        JSObject ret = new JSObject();
        ret.put("granted", canDraw);
        call.resolve(ret);
    }

    @PluginMethod
    public void requestOverlayPermission(PluginCall call) {
        Context context = getContext();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            try {
                Intent intent = new Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:" + context.getPackageName())
                );
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(intent);
                JSObject ret = new JSObject();
                ret.put("success", true);
                call.resolve(ret);
                return;
            } catch (Exception e) {
                Log.e(TAG, "Failed to request overlay permission: " + e.getMessage());
            }
        }
        JSObject ret = new JSObject();
        ret.put("success", false);
        call.resolve(ret);
    }

    @PluginMethod
    public void triggerAmbientSession(PluginCall call) {
        Context context = getContext();
        try {
            Intent intent = new Intent(context, AssistantActivity.class);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
            JSObject ret = new JSObject();
            ret.put("success", true);
            call.resolve(ret);
        } catch (Exception e) {
            call.reject("Failed to trigger ambient session: " + e.getMessage());
        }
    }

    @PluginMethod
    public void triggerFloatingSphere(PluginCall call) {
        Context context = getContext();
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && Settings.canDrawOverlays(context)) {
                IrisSphereService.startSphere(context);
            } else {
                Intent intent = new Intent(context, IrisSphereActivity.class);
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(intent);
            }
            JSObject ret = new JSObject();
            ret.put("success", true);
            call.resolve(ret);
        } catch (Exception e) {
            call.reject("Failed to trigger floating sphere: " + e.getMessage());
        }
    }

    @PluginMethod
    public void stopFloatingSphere(PluginCall call) {
        Context context = getContext();
        try {
            IrisSphereService.stopSphere(context);
            JSObject ret = new JSObject();
            ret.put("success", true);
            call.resolve(ret);
        } catch (Exception e) {
            call.reject("Failed to stop floating sphere: " + e.getMessage());
        }
    }

    @PluginMethod
    public void setPreferSphereMode(PluginCall call) {
        boolean enabled = call.getBoolean("enabled", true);
        SharedPreferences prefs = getContext().getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit().putBoolean(KEY_PREFER_SPHERE, enabled).apply();
        JSObject ret = new JSObject();
        ret.put("success", true);
        ret.put("preferSphereMode", enabled);
        call.resolve(ret);
    }

    @PluginMethod
    public void getPreferSphereMode(PluginCall call) {
        SharedPreferences prefs = getContext().getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        boolean enabled = prefs.getBoolean(KEY_PREFER_SPHERE, false);
        JSObject ret = new JSObject();
        ret.put("preferSphereMode", enabled);
        call.resolve(ret);
    }

    @PluginMethod
    public void captureScreenNative(PluginCall call) {
        Context context = getContext();
        IrisScreenCaptureManager.captureCurrentDisplay(context, new IrisScreenCaptureManager.CaptureCallback() {
            @Override
            public void onSuccess(Bitmap bitmap, String base64Jpeg) {
                JSObject ret = new JSObject();
                ret.put("success", true);
                ret.put("image_base64", base64Jpeg);
                call.resolve(ret);
            }

            @Override
            public void onError(String errorMessage) {
                call.reject("Screen capture failed: " + errorMessage);
            }
        });
    }
}
