package com.kirtan.iris;

import android.app.Activity;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.WindowManager;

public class AssistantActivity extends Activity {

    private IrisOverlayView mOverlayView;
    private IrisAmbientVoiceManager mVoiceManager;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Make window translucent, edge-to-edge, and borderless
        if (getWindow() != null) {
            getWindow().addFlags(
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS |
                WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS
            );
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                getWindow().setDecorFitsSystemWindows(false);
            }
        }

        mOverlayView = new IrisOverlayView(this);
        setContentView(mOverlayView);

        mVoiceManager = new IrisAmbientVoiceManager(this, mOverlayView);
        mOverlayView.setOnDismissListener(() -> {
            if (mVoiceManager != null) {
                mVoiceManager.stopSession();
            }
            finish();
            overridePendingTransition(0, android.R.anim.fade_out);
        });

        mVoiceManager.startSession(null);
    }

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
