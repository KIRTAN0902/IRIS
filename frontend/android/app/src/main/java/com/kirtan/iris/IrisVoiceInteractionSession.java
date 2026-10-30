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

    private IrisVisualContainer mVisualContainer;
    private IrisAmbientVoiceManager mVoiceManager;
    private String mForegroundPackage = "";

    public IrisVoiceInteractionSession(Context context) {
        super(context);
    }

    @Override
    public void onCreate() {
        super.onCreate();
    }

    @Override
    public View onCreateContentView() {
        FrameLayout container = new FrameLayout(getContext());
        container.setLayoutParams(new ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        ));

        android.content.SharedPreferences prefs = getContext().getSharedPreferences(IrisApplication.PREFS_NAME, Context.MODE_PRIVATE);
        boolean preferSphere = prefs.getBoolean(IrisApplication.KEY_PREFER_SPHERE, true);

        if (preferSphere) {
            IrisSphereView sphere = new IrisSphereView(getContext());
            int sphereSize = (int) (88 * getContext().getResources().getDisplayMetrics().density);
            FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(sphereSize, sphereSize);
            lp.gravity = Gravity.TOP | Gravity.END;
            lp.topMargin = (int) (getContext().getResources().getDisplayMetrics().heightPixels * 0.28f);
            lp.rightMargin = 24;
            sphere.setLayoutParams(lp);
            sphere.setOnSphereInteractionListener(new IrisSphereView.OnSphereInteractionListener() {
                @Override
                public void onSphereTapped() {
                    if (mVoiceManager != null) {
                        if (sphere.getState() == IrisVisualContainer.STATE_SPEAKING) {
                            sphere.setState(IrisVisualContainer.STATE_LISTENING);
                        } else if (sphere.getState() == IrisVisualContainer.STATE_IDLE) {
                            mVoiceManager.startSession(null);
                        }
                    }
                }

                @Override
                public void onSphereDismissed() {
                    if (mVoiceManager != null) {
                        mVoiceManager.stopSession();
                    }
                    hide();
                }

                @Override
                public void onSphereMoved(int x, int y) {}
            });
            mVisualContainer = sphere;
            container.addView(sphere);
        } else {
            IrisOverlayView overlay = new IrisOverlayView(getContext());
            overlay.setOnDismissListener(() -> {
                if (mVoiceManager != null) {
                    mVoiceManager.stopSession();
                }
                hide();
            });
            mVisualContainer = overlay;
            container.addView(overlay, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ));
        }

        mVoiceManager = new IrisAmbientVoiceManager(getContext(), mVisualContainer);
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
    public void onHandleScreenshot(android.graphics.Bitmap screenshot) {
        super.onHandleScreenshot(screenshot);
        if (screenshot != null) {
            Log.i(TAG, "OS delivered assistant screenshot: " + screenshot.getWidth() + "x" + screenshot.getHeight());
            IrisScreenCaptureManager.setAssistScreenshot(screenshot);
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
