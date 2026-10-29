package com.kirtan.iris;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.util.Log;

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
    private static final String DEFAULT_API_URL = "https://irisai.runs-on.dev/api/finance/auto-log";
    private static final String CHANNEL_ID = "iris_finance_alerts";
    public static final String PREFS_NAME = "iris_preferences";
    public static final String PREF_SERVER_URL = "server_base_url";

    // Known UPI / payment app package IDs in India & Global
    private static final Set<String> PAYMENT_PACKAGES = new HashSet<>(Arrays.asList(
        "com.google.android.apps.nbu.paisa.user", // Google Pay (Tez India)
        "com.google.android.apps.walletnfcrel",  // Google Wallet / Pay
        "com.phonepe.app",                       // PhonePe
        "net.one97.paytm",                       // Paytm
        "com.dreamplug.androidapp",              // CRED
        "in.org.npci.upiapp",                    // BHIM
        "com.sbi.upi",                           // BHIM SBI Pay
        "com.icicibank.pockets",                 // ICICI Pockets
        "com.csam.icici.bank.imobile",           // iMobile Pay
        "com.hdfcbank.payzapp",                  // PayZapp
        "com.snapwork.hdfc",                     // HDFC MobileBanking
        "com.axis.mobile"                        // Axis Mobile
    ));

    // Common SMS apps (for bank debit/credit alerts)
    private static final Set<String> SMS_PACKAGES = new HashSet<>(Arrays.asList(
        "com.google.android.apps.messaging",
        "com.samsung.android.messaging"
    ));

    // Regex for amounts: ₹450, Rs. 1,200.50, INR 500, Rs 50
    private static final Pattern AMOUNT_PATTERN = Pattern.compile(
        "(?:₹|rs\\.?|inr)\\s*([0-9,]+(?:\\.[0-9]{1,2})?)",
        Pattern.CASE_INSENSITIVE
    );

    // Regex for merchant / payee
    private static final Pattern MERCHANT_PATTERN = Pattern.compile(
        "(?:paid to|sent to|transfer to|payment to|to|at|vpa|from)\\s+([^.,\\n\\r]+?)(?:\\s+using|\\s+via|\\s+on|\\s+for|\\s+with|\\s+ref|\\.|$)",
        Pattern.CASE_INSENSITIVE
    );

    // Regex for transaction reference (12-digit UPI RRN / UTR / Txn ID)
    private static final Pattern REF_PATTERN = Pattern.compile(
        "(?:ref(?:\\s*no)?|rrn|utr|txn\\s*id|transaction\\s*id|upi\\s*ref)[:\\s]*([0-9a-zA-Z]{10,24})",
        Pattern.CASE_INSENSITIVE
    );

    // Regex for sensitive account balance / card number redaction
    private static final Pattern BALANCE_REDACTION_PATTERN = Pattern.compile(
        "(?:bal(?:ance)?|avl\\s*bal(?:ance)?|available\\s*balance)[:\\s]*(?:₹|rs\\.?|inr)?\\s*[0-9,]+(?:\\.[0-9]{1,2})?",
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

        // If it's an SMS app, only inspect if it explicitly looks like a banking or financial transaction alert
        if (isSmsApp) {
            boolean hasFinKeyword = lowerMessage.contains("debited") || lowerMessage.contains("spent") ||
                lowerMessage.contains("paid") || lowerMessage.contains("credited") || lowerMessage.contains("received");
            boolean hasCurrency = lowerMessage.contains("inr") || lowerMessage.contains("rs") || lowerMessage.contains("₹");
            if (!hasFinKeyword || !hasCurrency) return;
        }

        // 1. Determine Direction
        String direction;
        if (lowerMessage.contains("failed") || lowerMessage.contains("declined") || lowerMessage.contains("unsuccessful") || lowerMessage.contains("cancelled")) {
            direction = "failed";
        } else if (lowerMessage.contains("refund") || lowerMessage.contains("reversal") || lowerMessage.contains("reversed")) {
            direction = "refund";
        } else if (lowerMessage.contains("credited") || lowerMessage.contains("received") || lowerMessage.contains("added to your account") || lowerMessage.contains("cashback received")) {
            direction = "income";
        } else if (lowerMessage.contains("paid") || lowerMessage.contains("debited") || lowerMessage.contains("sent") ||
                   lowerMessage.contains("spent") || lowerMessage.contains("transfer to") || lowerMessage.contains("successful")) {
            direction = "expense";
        } else {
            // Not a financial movement notification
            return;
        }

        // 2. Extract Amount
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

        // 3. Extract Merchant / Payee
        String merchant = direction.equals("income") ? "Received Money" : "UPI Payment";
        Matcher merchantMatcher = MERCHANT_PATTERN.matcher(fullMessage);
        if (merchantMatcher.find()) {
            String candidate = merchantMatcher.group(1).trim();
            if (candidate.length() > 1 && candidate.length() < 60) {
                merchant = candidate;
            }
        } else if (!title.isEmpty() && !title.equalsIgnoreCase("Google Pay") && !title.equalsIgnoreCase("PhonePe") && !title.equalsIgnoreCase("Paytm")) {
            merchant = title.trim();
        }

        // 4. Extract UPI Reference (RRN / Txn ID)
        String transactionRef = null;
        Matcher refMatcher = REF_PATTERN.matcher(fullMessage);
        if (refMatcher.find()) {
            transactionRef = refMatcher.group(1).trim();
        }

        // 5. Redact Sensitive Information for Privacy (e.g. Account balances)
        String redactedText = BALANCE_REDACTION_PATTERN.matcher(fullMessage).replaceAll("[Balance Redacted]");

        final String finalMerchant = merchant;
        final String finalRef = transactionRef;
        final String finalDirection = direction;
        final String source = isPaymentApp ? packageName.substring(packageName.lastIndexOf('.') + 1) : "bank_sms";

        Log.i(TAG, "Detected transaction: ₹" + amount + " (" + finalDirection + ") counterparty: '" +
            finalMerchant + "' ref: " + finalRef + " from " + source);

        // 6. Send async HTTP POST to IRIS Backend
        new Thread(() -> sendPaymentToBackend(amount, finalMerchant, finalDirection, finalRef, redactedText, source)).start();
    }

    private String getEndpointUrl() {
        try {
            SharedPreferences prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
            String customUrl = prefs.getString(PREF_SERVER_URL, null);
            if (customUrl != null && !customUrl.trim().isEmpty()) {
                String base = customUrl.replaceAll("/+$", "");
                return base.endsWith("/api") ? base + "/finance/auto-log" : base + "/api/finance/auto-log";
            }
        } catch (Exception e) {
            Log.w(TAG, "Could not read preferences for custom server URL", e);
        }
        return DEFAULT_API_URL;
    }

    private void sendPaymentToBackend(double amount, String merchant, String direction, String transactionRef, String rawText, String source) {
        HttpURLConnection conn = null;
        try {
            URL url = new URL(getEndpointUrl());
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
            payload.put("direction", direction);
            if (transactionRef != null && !transactionRef.isEmpty()) {
                payload.put("transaction_ref", transactionRef);
            }
            payload.put("raw_text", rawText);
            payload.put("source", source);
            payload.put("currency", "INR");

            byte[] jsonBytes = payload.toString().getBytes(StandardCharsets.UTF_8);
            try (OutputStream os = conn.getOutputStream()) {
                os.write(jsonBytes);
                os.flush();
            }

            int responseCode = conn.getResponseCode();
            if (responseCode == 200 || responseCode == 201) {
                Log.i(TAG, "Successfully sent payment to IRIS backend");
                if ("expense".equals(direction) || "income".equals(direction) || "refund".equals(direction)) {
                    showConfirmationNotification(amount, merchant, direction);
                }
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

    private void showConfirmationNotification(double amount, String merchant, String direction) {
        new Handler(Looper.getMainLooper()).post(() -> {
            try {
                NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
                if (nm != null) {
                    String prefix = "income".equals(direction) || "refund".equals(direction) ? "Auto-logged +" : "Auto-logged ";
                    Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
                        .setSmallIcon(R.mipmap.ic_launcher)
                        .setContentTitle("IRIS Finance")
                        .setContentText(prefix + "₹" + String.format("%.2f", amount) + " (" + merchant + ")")
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
