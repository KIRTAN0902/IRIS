package com.kirtan.iris;

import android.app.assist.AssistContent;
import android.app.assist.AssistStructure;
import android.content.Context;
import android.os.Bundle;
import android.service.voice.VoiceInteractionSession;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.FrameLayout;

public class IrisVoiceInteractionSession extends VoiceInteractionSession {

    private static final String TAG = "IRIS_AssistSession";

    private IrisOverlayView mOverlayView;
    private IrisAmbientVoiceManager mVoiceManager;
    private String mForegroundPackage = "";

    public IrisVoiceInteractionSession(Context context) {
        super(context);
    }

    @Override
    public void onCreate() {
        super.onCreate();
        mOverlayView = new IrisOverlayView(getContext());
        mVoiceManager = new IrisAmbientVoiceManager(getContext(), mOverlayView);

        mOverlayView.setOnDismissListener(() -> {
            mVoiceManager.stopSession();
            hide();
        });
    }

    @Override
    public View onCreateContentView() {
        FrameLayout container = new FrameLayout(getContext());
        container.setLayoutParams(new ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        ));
        container.addView(mOverlayView, new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ));
        return container;
    }

    @Override
    public void onShow(Bundle args, int flags) {
        super.onShow(args, flags);
        Log.i(TAG, "VoiceInteractionSession onShow with flags: " + flags);

        // Configure full-screen overlay window flags
        if (getWindow() != null && getWindow().getWindow() != null) {
            getWindow().getWindow().addFlags(
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS |
                WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS
            );
        }

        mVoiceManager.startSession(null);
    }

    @Override
    public void onHandleAssist(Bundle data, AssistStructure structure, AssistContent content) {
        super.onHandleAssist(data, structure, content);
        if (structure != null && structure.getActivityComponent() != null) {
            mForegroundPackage = structure.getActivityComponent().getPackageName();
            Log.i(TAG, "Active foreground application: " + mForegroundPackage);
        }
    }

    @Override
    public void onHide() {
        super.onHide();
        Log.i(TAG, "VoiceInteractionSession onHide");
        if (mVoiceManager != null) {
            mVoiceManager.stopSession();
        }
    }
}
