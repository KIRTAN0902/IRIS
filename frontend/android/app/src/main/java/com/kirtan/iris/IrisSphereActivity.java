package com.kirtan.iris;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.util.Log;
import android.view.Gravity;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.Toast;

/**
 * Native Activation Entry Point for IRIS Floating Sphere.
 *
 * Receives the Realme Screen-off Gesture, Assistant Invocation, or Launcher Shortcut.
 * Immediately dispatches IrisSphereService and backgrounds itself without mounting
 * the heavy Capacitor/React WebView application.
 */
public class IrisSphereActivity extends Activity implements IrisSphereView.OnSphereInteractionListener {

    private static final String TAG = "IRIS_SphereActivity";
    private static final int REQUEST_OVERLAY_PERMISSION = 2028;

    private IrisSphereView mSphereView;
    private IrisAmbientVoiceManager mVoiceManager;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Check if overlay permission is granted
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && Settings.canDrawOverlays(this)) {
            Log.i(TAG, "Overlay permission granted. Dispatching standalone IrisSphereService.");
            IrisSphereService.startSphere(this);

            // Move to back immediately so the underlying application stays in the foreground
            moveTaskToBack(true);
            finish();
            overridePendingTransition(0, 0);
            return;
        }

        // Fallback for first run when overlay permission is not yet granted:
        // Render sphere directly in translucent, borderless activity
        Log.i(TAG, "Rendering fallback sphere in translucent activity window.");
        if (getWindow() != null) {
            getWindow().addFlags(
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS |
                WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS
            );
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                getWindow().setDecorFitsSystemWindows(false);
            }
        }

        FrameLayout container = new FrameLayout(this);
        container.setLayoutParams(new ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        ));

        // Place sphere on top right
        mSphereView = new IrisSphereView(this);
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
            (int) (88 * getResources().getDisplayMetrics().density),
            (int) (88 * getResources().getDisplayMetrics().density)
        );
        lp.gravity = Gravity.TOP | Gravity.END;
        lp.topMargin = (int) (getResources().getDisplayMetrics().heightPixels * 0.28f);
        lp.rightMargin = 16;
        mSphereView.setLayoutParams(lp);
        mSphereView.setOnSphereInteractionListener(this);

        container.addView(mSphereView);
        setContentView(container);

        mVoiceManager = new IrisAmbientVoiceManager(this, mSphereView);
        mVoiceManager.startSession(null);

        // Prompt user to grant permanent overlay permission so future activations float over all apps
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "Enable 'Display over other apps' for IRIS to float everywhere", Toast.LENGTH_LONG).show();
            Intent intent = new Intent(
                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:" + getPackageName())
            );
            startActivityForResult(intent, REQUEST_OVERLAY_PERMISSION);
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQUEST_OVERLAY_PERMISSION) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && Settings.canDrawOverlays(this)) {
                IrisSphereService.startSphere(this);
                finish();
                overridePendingTransition(0, 0);
            }
        }
    }

    @Override
    public void onSphereTapped() {
        if (mVoiceManager != null) {
            if (mSphereView.getState() == IrisVisualContainer.STATE_SPEAKING) {
                mSphereView.setState(IrisVisualContainer.STATE_LISTENING);
            } else if (mSphereView.getState() == IrisVisualContainer.STATE_IDLE) {
                mVoiceManager.startSession(null);
            }
        }
    }

    @Override
    public void onSphereDismissed() {
        if (mVoiceManager != null) {
            mVoiceManager.stopSession();
        }
        finish();
        overridePendingTransition(0, android.R.anim.fade_out);
    }

    @Override
    public void onSphereMoved(int x, int y) {}

    @Override
    protected void onPause() {
        super.onPause();
        if (mVoiceManager != null) {
            mVoiceManager.stopSession();
        }
        finish();
    }

    @Override
    protected void onDestroy() {
        if (mVoiceManager != null) {
            mVoiceManager.stopSession();
        }
        super.onDestroy();
    }
}
