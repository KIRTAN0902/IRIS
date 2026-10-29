package com.kirtan.iris;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.provider.Settings;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "PaymentListener")
public class PaymentPlugin extends Plugin {

    @PluginMethod
    public void isNotificationAccessGranted(PluginCall call) {
        Context context = getContext();
        ComponentName cn = new ComponentName(context, PaymentNotificationListener.class);
        String flat = Settings.Secure.getString(context.getContentResolver(), "enabled_notification_listeners");
        boolean enabled = flat != null && flat.contains(cn.flattenToString());

        JSObject ret = new JSObject();
        ret.put("granted", enabled);
        call.resolve(ret);
    }

    @PluginMethod
    public void openNotificationSettings(PluginCall call) {
        Context context = getContext();
        Intent intent = new Intent("android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS");
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(intent);

        JSObject ret = new JSObject();
        ret.put("success", true);
        call.resolve(ret);
    }

    @PluginMethod
    public void setServerUrl(PluginCall call) {
        String url = call.getString("url");
        if (url == null || url.trim().isEmpty()) {
            call.reject("url parameter is required");
            return;
        }

        Context context = getContext();
        SharedPreferences prefs = context.getSharedPreferences(PaymentNotificationListener.PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit().putString(PaymentNotificationListener.PREF_SERVER_URL, url.trim()).apply();

        JSObject ret = new JSObject();
        ret.put("success", true);
        ret.put("url", url.trim());
        call.resolve(ret);
    }

    @PluginMethod
    public void getServerUrl(PluginCall call) {
        Context context = getContext();
        SharedPreferences prefs = context.getSharedPreferences(PaymentNotificationListener.PREFS_NAME, Context.MODE_PRIVATE);
        String url = prefs.getString(PaymentNotificationListener.PREF_SERVER_URL, "https://irisai.runs-on.dev");

        JSObject ret = new JSObject();
        ret.put("url", url);
        call.resolve(ret);
    }
}
