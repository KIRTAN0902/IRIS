package com.kirtan.iris;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.util.Log;
import android.widget.Toast;

import androidx.core.app.NotificationCompat;

import org.json.JSONObject;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class PaymentNotificationListener extends NotificationListenerService {

    private static final String TAG = "IRIS_PaymentListener";
    private static final String API_URL = "https://irisai.runs-on.dev/api/finance/auto-log";
    private static final String CHANNEL_ID = "iris_finance_alerts";

    // Known UPI / payment app package IDs in India
    private static final Set<String> PAYMENT_PACKAGES = new HashSet<>(Arrays.asList(
        "com.google.android.apps.nbu.paisa.user", // Google Pay (Tez)
        "com.phonepe.app",                       // PhonePe
        "net.one97.paytm",                        // Paytm
        "com.dreamplug.androidapp",               // CRED
        "in.org.npci.upiapp",                    // BHIM
        "com.sbi.upi"                            // BHIM SBI Pay
    ));

    // Common SMS apps (for bank alerts)
    private static final Set<String> SMS_PACKAGES = new HashSet<>(Arrays.asList(
        "com.google.android.apps.messaging",
        "com.samsung.android.messaging"
    ));

    // Regex for amounts: ₹450, Rs. 1,200.50, INR 500
    private static final Pattern AMOUNT_PATTERN = Pattern.compile(
        "(?:₹|rs\\.?|inr)\\s*([0-9,]+(?:\\.[0-9]{1,2})?)",
        Pattern.CASE_INSENSITIVE
    );

    // Regex for merchant / payee
    private static final Pattern MERCHANT_PATTERN = Pattern.compile(
        "(?:paid to|sent to|transfer to|payment to|to|at)\\s+([^.,\\n\\r]+?)(?:\\s+using|\\s+via|\\s+on|\\s+for|\\s+with|\\s+ref|\\.|$)",
        Pattern.CASE_INSENSITIVE
    );

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        Log.i(TAG, "PaymentNotificationListener initialized");
    }

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        if (sbn == null || sbn.getNotification() == null) return;

        String packageName = sbn.getPackageName();
        boolean isPaymentApp = PAYMENT_PACKAGES.contains(packageName);
        boolean isSmsApp = SMS_PACKAGES.contains(packageName);

        if (!isPaymentApp && !isSmsApp) return;

        Bundle extras = sbn.getNotification().extras;
        String title = extras.getString(Notification.EXTRA_TITLE, "");
        CharSequence textCs = extras.getCharSequence(Notification.EXTRA_TEXT);
        CharSequence bigTextCs = extras.getCharSequence(Notification.EXTRA_BIG_TEXT);

        String text = textCs != null ? textCs.toString() : "";
        if (bigTextCs != null && bigTextCs.length() > text.length()) {
            text = bigTextCs.toString();
        }

        String fullMessage = (title + " " + text).trim();
        String lowerMessage = fullMessage.toLowerCase();

        // If it's an SMS app, only inspect if it explicitly looks like a bank debit alert
        if (isSmsApp) {
            boolean hasDebitKeyword = lowerMessage.contains("debited") || lowerMessage.contains("spent") || lowerMessage.contains("paid");
            boolean hasCurrency = lowerMessage.contains("inr") || lowerMessage.contains("rs") || lowerMessage.contains("₹");
            if (!hasDebitKeyword || !hasCurrency) return;
        }

        // Ignore incoming money, credits, cashbacks
        if (lowerMessage.contains("credited") || lowerMessage.contains("received") || lowerMessage.contains("cashback received")) {
            return;
        }

        // Must look like an expenditure / debit
        if (!lowerMessage.contains("paid") && !lowerMessage.contains("debited") && !lowerMessage.contains("sent") && !lowerMessage.contains("spent") && !lowerMessage.contains("successful")) {
            return;
        }

        // 1. Extract Amount
        Matcher amountMatcher = AMOUNT_PATTERN.matcher(fullMessage);
        if (!amountMatcher.find()) return;

        String amountRaw = amountMatcher.group(1).replace(",", "");
        final double amount;
        try {
            amount = Double.parseDouble(amountRaw);
            if (amount <= 0) return;
        } catch (NumberFormatException e) {
            return;
        }

        // 2. Extract Merchant / Payee
        String merchant = "UPI Payment";
        Matcher merchantMatcher = MERCHANT_PATTERN.matcher(fullMessage);
        if (merchantMatcher.find()) {
            String candidate = merchantMatcher.group(1).trim();
            if (candidate.length() > 1 && candidate.length() < 60) {
                merchant = candidate;
            }
        } else if (!title.isEmpty() && !title.equalsIgnoreCase("Google Pay") && !title.equalsIgnoreCase("PhonePe") && !title.equalsIgnoreCase("Paytm")) {
            merchant = title.trim();
        }

        final String finalMerchant = merchant;
        final String source = isPaymentApp ? packageName.substring(packageName.lastIndexOf('.') + 1) : "bank_sms";

        Log.i(TAG, "Detected payment: ₹" + amount + " to '" + finalMerchant + "' from " + source);

        // 3. Send async HTTP POST to IRIS Backend
        new Thread(() -> sendPaymentToBackend(amount, finalMerchant, fullMessage, source)).start();
    }

    private void sendPaymentToBackend(double amount, String merchant, String rawText, String source) {
        HttpURLConnection conn = null;
        try {
            URL url = new URL(API_URL);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
            conn.setRequestProperty("Accept", "application/json");
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(8000);
            conn.setDoOutput(true);

            JSONObject payload = new JSONObject();
            payload.put("amount", amount);
            payload.put("merchant", merchant);
            payload.put("raw_text", rawText);
            payload.put("source", source);

            byte[] jsonBytes = payload.toString().getBytes(StandardCharsets.UTF_8);
            try (OutputStream os = conn.getOutputStream()) {
                os.write(jsonBytes);
                os.flush();
            }

            int responseCode = conn.getResponseCode();
            if (responseCode == 200 || responseCode == 201) {
                Log.i(TAG, "Successfully sent payment to IRIS backend");
                showConfirmationNotification(amount, merchant);
            } else {
                Log.w(TAG, "Backend returned HTTP " + responseCode);
            }
        } catch (Exception e) {
            Log.e(TAG, "Failed to send payment to IRIS backend", e);
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    private void showConfirmationNotification(double amount, String merchant) {
        new Handler(Looper.getMainLooper()).post(() -> {
            try {
                NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
                if (nm != null) {
                    Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
                        .setSmallIcon(R.mipmap.ic_launcher)
                        .setContentTitle("IRIS Finance")
                        .setContentText("Auto-logged ₹" + String.format("%.2f", amount) + " to " + merchant)
                        .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                        .setAutoCancel(true)
                        .build();
                    nm.notify((int) System.currentTimeMillis(), notification);
                }
            } catch (Exception e) {
                Log.e(TAG, "Error posting confirmation", e);
            }
        });
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "Payment Alerts",
                NotificationManager.IMPORTANCE_DEFAULT
            );
            channel.setDescription("Notifications when IRIS auto-logs a payment");
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                nm.createNotificationChannel(channel);
            }
        }
    }
}
