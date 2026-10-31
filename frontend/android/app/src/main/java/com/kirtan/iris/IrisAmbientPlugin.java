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
import com.kirtan.iris.assistant.AssistantBridge;
import com.kirtan.iris.assistant.CapabilityDetector;

@CapacitorPlugin(name = "IrisAmbient")
public class IrisAmbientPlugin extends Plugin {

    private static final String TAG = "IRIS_AmbientPlugin";
    private static final String PREFS_NAME = "iris_settings";
    private static final String KEY_PREFER_SPHERE = "prefer_floating_sphere";

    @PluginMethod
    public void isAssistantRoleGranted(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("granted", CapabilityDetector.isDefaultAssistant(getContext()));
        call.resolve(ret);
    }

    @PluginMethod
    public void requestAssistantRole(PluginCall call) {
        Context context = getContext();
        boolean opened = CapabilityDetector.requestAssistantRole(context);
        JSObject ret = new JSObject();
        ret.put("success", opened);
        ret.put("method", opened ? "role_manager" : "settings");
        call.resolve(ret);
    }

    @PluginMethod
    public void hasOverlayPermission(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("granted", CapabilityDetector.canDrawOverlays(getContext()));
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

    /** Launches the native assistant session, never the full application. */
    @PluginMethod
    public void triggerAmbientSession(PluginCall call) {
        AssistantBridge.launchAssistant(getContext());
        JSObject ret = new JSObject();
        ret.put("success", true);
        call.resolve(ret);
    }

    /** Legacy alias kept for older dashboard bundles. */
    @PluginMethod
    public void triggerFloatingSphere(PluginCall call) {
        AssistantBridge.launchAssistant(getContext());
        JSObject ret = new JSObject();
        ret.put("success", true);
        call.resolve(ret);
    }

    /** The native assistant has no persistent floating overlay to stop. */
    @PluginMethod
    public void stopFloatingSphere(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("success", true);
        call.resolve(ret);
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
        JSObject ret = new JSObject();
        ret.put("preferSphereMode", prefs.getBoolean(KEY_PREFER_SPHERE, false));
        call.resolve(ret);
    }

    @PluginMethod
    public void openAssistantSettings(PluginCall call) {
        AssistantBridge.openSettings(getContext());
        JSObject ret = new JSObject();
        ret.put("success", true);
        call.resolve(ret);
    }

    @PluginMethod
    public void getAssistantCapabilities(PluginCall call) {
        try {
            JSObject ret = new JSObject();
            ret.put("capabilities", new org.json.JSONObject(AssistantBridge.capabilitiesJson(getContext())));
            call.resolve(ret);
        } catch (Exception e) {
            call.reject("Could not read assistant capabilities: " + e.getMessage());
        }
    }

    @PluginMethod
    public void refreshHotword(PluginCall call) {
        AssistantBridge.refreshHotword();
        JSObject ret = new JSObject();
        ret.put("success", true);
        call.resolve(ret);
    }

    @PluginMethod
    public void captureScreenNative(PluginCall call) {
        IrisScreenCaptureManager.captureCurrentDisplay(getContext(), new IrisScreenCaptureManager.CaptureCallback() {
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
