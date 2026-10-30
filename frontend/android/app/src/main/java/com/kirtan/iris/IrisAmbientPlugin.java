package com.kirtan.iris;

import android.app.role.RoleManager;
import android.content.Context;
import android.content.Intent;
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
}
