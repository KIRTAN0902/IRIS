package com.kirtan.iris;

import android.animation.Animator;
import android.animation.AnimatorListenerAdapter;
import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.SweepGradient;
import android.os.Build;
import android.provider.Settings;
import android.util.AttributeSet;
import android.view.MotionEvent;
import android.view.View;
import android.view.animation.AccelerateDecelerateInterpolator;
import android.view.animation.DecelerateInterpolator;

public class IrisOverlayView extends View implements IrisVisualContainer {

    public static final int STATE_IDLE = 0;
    public static final int STATE_ACTIVATING = 1;
    public static final int STATE_LISTENING = 2;
    public static final int STATE_PROCESSING = 3;
    public static final int STATE_EXECUTING = 4;
    public static final int STATE_SPEAKING = 5;
    public static final int STATE_APPROVAL_REQUIRED = 6;
    public static final int STATE_ERROR = 7;
    public static final int STATE_DISMISSING = 8;

    private int mCurrentState = STATE_IDLE;
    private float mAnimationPhase = 0.0f;
    private float mEntranceAlpha = 0.0f;
    private float mAudioAmplitude = 0.0f;
    private float mTargetAmplitude = 0.0f;

    private Paint mBorderPaint;
    private Paint mGlowPaint;
    private Paint mBadgeBackgroundPaint;
    private Paint mBadgeTextPaint;
    private Paint mScrimPaint;

    private RectF mScreenRect = new RectF();
    private RectF mBadgeRect = new RectF();
    private Path mBorderPath = new Path();

    private ValueAnimator mPhaseAnimator;
    private ValueAnimator mEntranceAnimator;
    private ValueAnimator mExitAnimator;

    private OnDismissListener mDismissListener;
    private String mStatusText = "Listening...";

    public interface OnDismissListener {
        void onDismiss();
    }

    public IrisOverlayView(Context context) {
        super(context);
        init();
    }

    public IrisOverlayView(Context context, AttributeSet attrs) {
        super(context, attrs);
        init();
    }

    private void init() {
        setWillNotDraw(false);

        mBorderPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        mBorderPaint.setStyle(Paint.Style.STROKE);
        mBorderPaint.setStrokeWidth(dpToPx(4.5f));

        mGlowPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        mGlowPaint.setStyle(Paint.Style.STROKE);
        mGlowPaint.setStrokeWidth(dpToPx(16.0f));

        mBadgeBackgroundPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        mBadgeBackgroundPaint.setStyle(Paint.Style.FILL);
        mBadgeBackgroundPaint.setColor(Color.parseColor("#E60D1117"));

        mBadgeTextPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        mBadgeTextPaint.setColor(Color.parseColor("#00E5FF"));
        mBadgeTextPaint.setTextSize(dpToPx(13.0f));
        mBadgeTextPaint.setTextAlign(Paint.Align.CENTER);
        mBadgeTextPaint.setFakeBoldText(true);

        mScrimPaint = new Paint();
        mScrimPaint.setColor(Color.parseColor("#26000000")); // Very subtle 15% dark scrim

        setupAnimators();
    }

    private void setupAnimators() {
        mPhaseAnimator = ValueAnimator.ofFloat(0.0f, 1.0f);
        mPhaseAnimator.setDuration(2400);
        mPhaseAnimator.setRepeatCount(ValueAnimator.INFINITE);
        mPhaseAnimator.setInterpolator(new AccelerateDecelerateInterpolator());
        mPhaseAnimator.addUpdateListener(anim -> {
            mAnimationPhase = (float) anim.getAnimatedValue();
            // Smoothly interpolate audio amplitude
            mAudioAmplitude += (mTargetAmplitude - mAudioAmplitude) * 0.25f;
            invalidate();
        });

        mEntranceAnimator = ValueAnimator.ofFloat(0.0f, 1.0f);
        mEntranceAnimator.setDuration(350);
        mEntranceAnimator.setInterpolator(new DecelerateInterpolator());
        mEntranceAnimator.addUpdateListener(anim -> {
            mEntranceAlpha = (float) anim.getAnimatedValue();
            invalidate();
        });

        mExitAnimator = ValueAnimator.ofFloat(1.0f, 0.0f);
        mExitAnimator.setDuration(250);
        mExitAnimator.setInterpolator(new AccelerateDecelerateInterpolator());
        mExitAnimator.addUpdateListener(anim -> {
            mEntranceAlpha = (float) anim.getAnimatedValue();
            invalidate();
        });
        mExitAnimator.addListener(new AnimatorListenerAdapter() {
            @Override
            public void onAnimationEnd(Animator animation) {
                mCurrentState = STATE_IDLE;
                if (mDismissListener != null) {
                    mDismissListener.onDismiss();
                }
            }
        });
    }

    public void setOnDismissListener(OnDismissListener listener) {
        this.mDismissListener = listener;
    }

    public void setState(int state) {
        if (mCurrentState == state) return;
        mCurrentState = state;

        switch (state) {
            case STATE_ACTIVATING:
                mStatusText = "IRIS";
                if (!mPhaseAnimator.isRunning()) mPhaseAnimator.start();
                mEntranceAnimator.start();
                break;
            case STATE_LISTENING:
                mStatusText = "Listening...";
                mTargetAmplitude = 0.2f;
                mBadgeTextPaint.setColor(Color.parseColor("#00E5FF"));
                break;
            case STATE_PROCESSING:
                mStatusText = "Reasoning...";
                mTargetAmplitude = 0.5f;
                mBadgeTextPaint.setColor(Color.parseColor("#7C4DFF"));
                break;
            case STATE_EXECUTING:
                mStatusText = "Executing action...";
                mTargetAmplitude = 0.7f;
                mBadgeTextPaint.setColor(Color.parseColor("#FFB300"));
                break;
            case STATE_SPEAKING:
                mStatusText = "IRIS";
                mBadgeTextPaint.setColor(Color.parseColor("#00E5FF"));
                break;
            case STATE_APPROVAL_REQUIRED:
                mStatusText = "Approval required";
                mBadgeTextPaint.setColor(Color.parseColor("#FFB300"));
                break;
            case STATE_ERROR:
                mStatusText = "Encountered an issue";
                mBadgeTextPaint.setColor(Color.parseColor("#FF5252"));
                break;
            case STATE_DISMISSING:
                mStatusText = "";
                mExitAnimator.start();
                break;
            case STATE_IDLE:
                mPhaseAnimator.cancel();
                mEntranceAlpha = 0.0f;
                break;
        }
        invalidate();
    }

    public int getState() {
        return mCurrentState;
    }

    public void setAudioAmplitude(float amplitude) {
        // Normalize between 0.0 and 1.0
        mTargetAmplitude = Math.max(0.0f, Math.min(1.0f, amplitude));
    }

    public void setStatusText(String text) {
        this.mStatusText = text;
        invalidate();
    }

    public void dismiss() {
        setState(STATE_DISMISSING);
    }

    @Override
    protected void onSizeChanged(int w, int h, int oldw, int oldh) {
        super.onSizeChanged(w, h, oldw, oldh);
        float inset = dpToPx(3.0f);
        mScreenRect.set(inset, inset, w - inset, h - inset);

        float cornerRadius = dpToPx(32.0f); // Curved corner display for Realme GT 7T
        mBorderPath.reset();
        mBorderPath.addRoundRect(mScreenRect, cornerRadius, cornerRadius, Path.Direction.CW);

        // Center bottom badge (pill)
        float badgeWidth = dpToPx(190.0f);
        float badgeHeight = dpToPx(38.0f);
        float badgeBottom = h - dpToPx(48.0f);
        float badgeLeft = (w - badgeWidth) / 2.0f;
        mBadgeRect.set(badgeLeft, badgeBottom - badgeHeight, badgeLeft + badgeWidth, badgeBottom);
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        if (mCurrentState == STATE_IDLE || mEntranceAlpha <= 0.0f) return;

        int width = getWidth();
        int height = getHeight();
        if (width <= 0 || height <= 0) return;

        // 1. Draw subtle ambient backdrop scrim
        mScrimPaint.setAlpha((int) (mEntranceAlpha * 40));
        canvas.drawRect(0, 0, width, height, mScrimPaint);

        // 2. Select dynamic palette based on state
        int color1, color2, color3, color4;
        if (mCurrentState == STATE_EXECUTING || mCurrentState == STATE_APPROVAL_REQUIRED) {
            color1 = Color.parseColor("#FFB300"); // Gold
            color2 = Color.parseColor("#FF6D00");
            color3 = Color.parseColor("#FFD54F");
            color4 = Color.parseColor("#FFB300");
        } else if (mCurrentState == STATE_ERROR) {
            color1 = Color.parseColor("#FF5252"); // Crimson
            color2 = Color.parseColor("#D50000");
            color3 = Color.parseColor("#FF8A80");
            color4 = Color.parseColor("#FF5252");
        } else {
            // JARVIS Sovereign Neon Cyan / Violet / Electric Blue palette
            color1 = Color.parseColor("#00E5FF"); // Cyan
            color2 = Color.parseColor("#7C4DFF"); // Violet
            color3 = Color.parseColor("#00B0FF"); // Electric Blue
            color4 = Color.parseColor("#00E5FF");
        }

        // Animated gradient angle based on phase
        float angle = (mAnimationPhase * 360.0f);
        SweepGradient sweepGradient = new SweepGradient(
            width / 2.0f,
            height / 2.0f,
            new int[]{color1, color2, color3, color4, color1},
            null
        );

        canvas.save();
        canvas.rotate(angle, width / 2.0f, height / 2.0f);
        mBorderPaint.setShader(sweepGradient);
        mGlowPaint.setShader(sweepGradient);
        canvas.restore();

        // Modulate alpha with audio amplitude during speaking/listening
        float pulseFactor = 0.7f + 0.3f * mAudioAmplitude;
        int glowAlpha = (int) (mEntranceAlpha * pulseFactor * 130);
        int borderAlpha = (int) (mEntranceAlpha * 255);

        mGlowPaint.setAlpha(glowAlpha);
        mBorderPaint.setAlpha(borderAlpha);

        // 3. Draw outer ambient luminous glow
        canvas.drawPath(mBorderPath, mGlowPaint);

        // 4. Draw sharp interior glowing border
        canvas.drawPath(mBorderPath, mBorderPaint);

        // 5. Draw floating status pill at bottom
        float badgeRadius = dpToPx(19.0f);
        mBadgeBackgroundPaint.setAlpha((int) (mEntranceAlpha * 240));
        canvas.drawRoundRect(mBadgeRect, badgeRadius, badgeRadius, mBadgeBackgroundPaint);

        // Badge border
        Paint badgeStroke = new Paint(Paint.ANTI_ALIAS_FLAG);
        badgeStroke.setStyle(Paint.Style.STROKE);
        badgeStroke.setStrokeWidth(dpToPx(1.5f));
        badgeStroke.setColor(color1);
        badgeStroke.setAlpha((int) (mEntranceAlpha * 200));
        canvas.drawRoundRect(mBadgeRect, badgeRadius, badgeRadius, badgeStroke);

        // Badge text label
        mBadgeTextPaint.setAlpha((int) (mEntranceAlpha * 255));
        float textY = mBadgeRect.centerY() - ((mBadgeTextPaint.descent() + mBadgeTextPaint.ascent()) / 2.0f);
        canvas.drawText(mStatusText, mBadgeRect.centerX(), textY, mBadgeTextPaint);
    }

    @Override
    public boolean onTouchEvent(MotionEvent event) {
        if (event.getAction() == MotionEvent.ACTION_DOWN) {
            float x = event.getX();
            float y = event.getY();

            // If tapped on the center badge, dismiss or handle click
            if (mBadgeRect.contains(x, y)) {
                dismiss();
                return true;
            }

            // Tapping anywhere outside the interactive badge dismisses the ambient session
            dismiss();
            return true;
        }
        return super.onTouchEvent(event);
    }

    private float dpToPx(float dp) {
        return dp * getResources().getDisplayMetrics().density;
    }
}
