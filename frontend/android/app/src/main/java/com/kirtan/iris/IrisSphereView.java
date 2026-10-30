package com.kirtan.iris;

import android.animation.Animator;
import android.animation.AnimatorListenerAdapter;
import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RadialGradient;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.SweepGradient;
import android.os.Handler;
import android.os.Looper;
import android.util.AttributeSet;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.view.animation.AccelerateDecelerateInterpolator;
import android.view.animation.DecelerateInterpolator;
import android.view.animation.OvershootInterpolator;

/**
 * Compact, Futuristic Luminous IRIS Floating Sphere.
 *
 * Designed as a standalone, draggable ambient AI presence:
 * - 68dp floating orb with multi-layer depth (core nucleus, dark glass body, orbital energy rings).
 * - Smooth state transitions: Idle, Activating, Listening, Processing, Executing, Speaking, Approval, Error, Dismissing.
 * - Dynamic audio-amplitude modulation (mic/speaker RMS).
 * - Touch-draggable with screen boundary clamping and snap-to-edge animation.
 * - Tap to toggle mute/listening, long-press to dismiss.
 */
public class IrisSphereView extends View implements IrisVisualContainer {

    public static final int STATE_IDLE = 0;
    public static final int STATE_ACTIVATING = 1;
    public static final int STATE_LISTENING = 2;
    public static final int STATE_PROCESSING = 3;
    public static final int STATE_EXECUTING = 4;
    public static final int STATE_SPEAKING = 5;
    public static final int STATE_APPROVAL_REQUIRED = 6;
    public static final int STATE_ERROR = 7;
    public static final int STATE_DISMISSING = 8;

    public interface OnSphereInteractionListener {
        void onSphereTapped();
        void onSphereDismissed();
        void onSphereMoved(int x, int y);
    }

    private int mState = STATE_ACTIVATING;
    private float mAudioAmplitude = 0.0f;
    private float mScale = 0.0f;
    private float mPulsePhase = 0.0f;
    private float mRotationAngle = 0.0f;

    private Paint mCorePaint;
    private Paint mGlassPaint;
    private Paint mGlowPaint;
    private Paint mRingPaint;
    private Paint mParticlePaint;

    private ValueAnimator mPhaseAnimator;
    private ValueAnimator mScaleAnimator;

    private WindowManager mWindowManager;
    private WindowManager.LayoutParams mLayoutParams;
    private OnSphereInteractionListener mListener;

    // Dragging variables
    private float mInitialTouchX;
    private float mInitialTouchY;
    private int mInitialX;
    private int mInitialY;
    private boolean mIsDragging = false;
    private long mTouchDownTime = 0;

    private final Handler mMainHandler = new Handler(Looper.getMainLooper());

    public IrisSphereView(Context context) {
        super(context);
        init();
    }

    public IrisSphereView(Context context, AttributeSet attrs) {
        super(context, attrs);
        init();
    }

    public void setWindowManagerParams(WindowManager wm, WindowManager.LayoutParams params) {
        this.mWindowManager = wm;
        this.mLayoutParams = params;
    }

    public void setOnSphereInteractionListener(OnSphereInteractionListener listener) {
        this.mListener = listener;
    }

    private void init() {
        setClickable(true);
        setFocusable(false);

        mCorePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        mGlassPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        mGlowPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        mRingPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        mRingPaint.setStyle(Paint.Style.STROKE);
        mRingPaint.setStrokeWidth(dpToPx(2.5f));

        mParticlePaint = new Paint(Paint.ANTI_ALIAS_FLAG);

        // Continuous phase animation for breathing and rotating rings
        mPhaseAnimator = ValueAnimator.ofFloat(0.0f, 1.0f);
        mPhaseAnimator.setDuration(2400);
        mPhaseAnimator.setRepeatCount(ValueAnimator.INFINITE);
        mPhaseAnimator.setInterpolator(new AccelerateDecelerateInterpolator());
        mPhaseAnimator.addUpdateListener(animation -> {
            mPulsePhase = (float) animation.getAnimatedValue();
            mRotationAngle = (mRotationAngle + 4.0f) % 360.0f;
            invalidate();
        });
        mPhaseAnimator.start();

        // Entrance scale animation
        animateEntrance();
    }

    public void animateEntrance() {
        mState = STATE_ACTIVATING;
        if (mScaleAnimator != null && mScaleAnimator.isRunning()) {
            mScaleAnimator.cancel();
        }
        mScaleAnimator = ValueAnimator.ofFloat(0.0f, 1.0f);
        mScaleAnimator.setDuration(450);
        mScaleAnimator.setInterpolator(new OvershootInterpolator(1.4f));
        mScaleAnimator.addUpdateListener(anim -> {
            mScale = (float) anim.getAnimatedValue();
            invalidate();
        });
        mScaleAnimator.addListener(new AnimatorListenerAdapter() {
            @Override
            public void onAnimationEnd(Animator animation) {
                mScale = 1.0f;
                if (mState == STATE_ACTIVATING) {
                    setState(STATE_LISTENING);
                }
            }
        });
        mScaleAnimator.start();
    }

    public void animateDismissal(Runnable onComplete) {
        mState = STATE_DISMISSING;
        if (mScaleAnimator != null && mScaleAnimator.isRunning()) {
            mScaleAnimator.cancel();
        }
        mScaleAnimator = ValueAnimator.ofFloat(mScale, 0.0f);
        mScaleAnimator.setDuration(320);
        mScaleAnimator.setInterpolator(new AccelerateDecelerateInterpolator());
        mScaleAnimator.addUpdateListener(anim -> {
            mScale = (float) anim.getAnimatedValue();
            invalidate();
        });
        mScaleAnimator.addListener(new AnimatorListenerAdapter() {
            @Override
            public void onAnimationEnd(Animator animation) {
                mScale = 0.0f;
                if (onComplete != null) {
                    onComplete.run();
                }
                if (mListener != null) {
                    mListener.onSphereDismissed();
                }
            }
        });
        mScaleAnimator.start();
    }

    public void setState(int newState) {
        if (this.mState == newState) return;
        this.mState = newState;
        mMainHandler.post(this::invalidate);
    }

    private String mStatusText = "";

    @Override
    public void setStatusText(String text) {
        this.mStatusText = text != null ? text : "";
    }

    public int getState() {
        return mState;
    }

    public void setAudioAmplitude(float normalizedAmp) {
        this.mAudioAmplitude = Math.max(0.0f, Math.min(1.0f, normalizedAmp));
        mMainHandler.post(this::invalidate);
    }

    @Override
    protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
        int defaultSize = (int) dpToPx(88); // 88dp total bounds including dynamic glow rings
        setMeasuredDimension(
            resolveSize(defaultSize, widthMeasureSpec),
            resolveSize(defaultSize, heightMeasureSpec)
        );
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        if (mScale <= 0.001f) return;

        float cx = getWidth() / 2.0f;
        float cy = getHeight() / 2.0f;
        float baseRadius = dpToPx(28.0f) * mScale; // ~56dp core sphere

        // Colors based on state
        int primaryColor;
        int secondaryColor;
        int glowColor;

        switch (mState) {
            case STATE_LISTENING:
                primaryColor = Color.parseColor("#00E5FF");    // Cyan
                secondaryColor = Color.parseColor("#00B0FF");  // Electric Blue
                glowColor = Color.parseColor("#4000E5FF");
                break;
            case STATE_PROCESSING:
                primaryColor = Color.parseColor("#7C4DFF");    // Deep Violet
                secondaryColor = Color.parseColor("#B388FF");  // Lavender
                glowColor = Color.parseColor("#407C4DFF");
                break;
            case STATE_EXECUTING:
                primaryColor = Color.parseColor("#FFB300");    // Amber
                secondaryColor = Color.parseColor("#FFE082");  // Gold
                glowColor = Color.parseColor("#40FFB300");
                break;
            case STATE_SPEAKING:
                primaryColor = Color.parseColor("#00E5FF");    // Neon Cyan Pulse
                secondaryColor = Color.parseColor("#7C4DFF");  // Violet blend
                glowColor = Color.parseColor("#6000E5FF");
                break;
            case STATE_APPROVAL_REQUIRED:
                primaryColor = Color.parseColor("#FF9100");    // Warning Amber
                secondaryColor = Color.parseColor("#FFD180");
                glowColor = Color.parseColor("#50FF9100");
                break;
            case STATE_ERROR:
                primaryColor = Color.parseColor("#FF5252");    // Crimson
                secondaryColor = Color.parseColor("#FF8A80");
                glowColor = Color.parseColor("#40FF5252");
                break;
            case STATE_IDLE:
            default:
                primaryColor = Color.parseColor("#37474F");    // Obsidian Slate
                secondaryColor = Color.parseColor("#546E7A");
                glowColor = Color.parseColor("#2000E5FF");
                break;
        }

        // 1. Outer Diffuse Glow
        float pulseAmp = (mState == STATE_LISTENING || mState == STATE_SPEAKING)
            ? (mAudioAmplitude * 0.45f)
            : (0.1f * (float) Math.sin(mPulsePhase * Math.PI * 2));
        float glowRadius = (baseRadius * 1.55f) * (1.0f + pulseAmp);

        RadialGradient glowGradient = new RadialGradient(
            cx, cy, Math.max(1.0f, glowRadius),
            new int[]{glowColor, Color.TRANSPARENT},
            null,
            Shader.TileMode.CLAMP
        );
        mGlowPaint.setShader(glowGradient);
        canvas.drawCircle(cx, cy, glowRadius, mGlowPaint);

        // 2. Concentric Acoustic Rings (Active when listening or speaking)
        if (mState == STATE_LISTENING || mState == STATE_SPEAKING) {
            float ring1Radius = baseRadius + dpToPx(6.0f) + (mAudioAmplitude * dpToPx(12.0f));
            float ring2Radius = baseRadius + dpToPx(13.0f) + (mAudioAmplitude * dpToPx(18.0f));

            mRingPaint.setColor(primaryColor);
            mRingPaint.setAlpha((int) (180 * (1.0f - mAudioAmplitude * 0.3f)));
            canvas.drawCircle(cx, cy, ring1Radius, mRingPaint);

            mRingPaint.setAlpha((int) (90 * (1.0f - mAudioAmplitude * 0.5f)));
            canvas.drawCircle(cx, cy, ring2Radius, mRingPaint);
        }

        // 3. Orbital Rotating Ring (Active when processing or executing)
        if (mState == STATE_PROCESSING || mState == STATE_EXECUTING) {
            canvas.save();
            canvas.rotate(mRotationAngle, cx, cy);
            SweepGradient sweep = new SweepGradient(
                cx, cy,
                new int[]{primaryColor, secondaryColor, Color.TRANSPARENT, primaryColor},
                null
            );
            mRingPaint.setShader(sweep);
            mRingPaint.setAlpha(240);
            RectF ringBounds = new RectF(
                cx - baseRadius * 1.15f,
                cy - baseRadius * 1.15f,
                cx + baseRadius * 1.15f,
                cy + baseRadius * 1.15f
            );
            canvas.drawArc(ringBounds, 0, 270, false, mRingPaint);
            mRingPaint.setShader(null);
            canvas.restore();
        }

        // 4. Dark Obsidian Glass Body
        RadialGradient glassGradient = new RadialGradient(
            cx - baseRadius * 0.25f,
            cy - baseRadius * 0.3f,
            baseRadius * 1.1f,
            new int[]{Color.parseColor("#1C2430"), Color.parseColor("#080A0F"), Color.parseColor("#030407")},
            null,
            Shader.TileMode.CLAMP
        );
        mGlassPaint.setShader(glassGradient);
        canvas.drawCircle(cx, cy, baseRadius, mGlassPaint);

        // 5. Luminous Core Nucleus
        float nucleusRadius = baseRadius * (0.38f + 0.15f * mAudioAmplitude);
        RadialGradient coreGradient = new RadialGradient(
            cx, cy, Math.max(1.0f, nucleusRadius),
            new int[]{Color.WHITE, primaryColor, secondaryColor, Color.TRANSPARENT},
            new float[]{0.0f, 0.45f, 0.85f, 1.0f},
            Shader.TileMode.CLAMP
        );
        mCorePaint.setShader(coreGradient);
        canvas.drawCircle(cx, cy, nucleusRadius, mCorePaint);

        // 6. Highlight Arc (Glass Reflection)
        Paint highlightPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        highlightPaint.setStyle(Paint.Style.STROKE);
        highlightPaint.setStrokeWidth(dpToPx(1.5f));
        highlightPaint.setColor(Color.WHITE);
        highlightPaint.setAlpha(90);
        RectF highlightRect = new RectF(
            cx - baseRadius * 0.75f,
            cy - baseRadius * 0.75f,
            cx + baseRadius * 0.75f,
            cy + baseRadius * 0.75f
        );
        canvas.drawArc(highlightRect, 200, 70, false, highlightPaint);
    }

    @Override
    public boolean onTouchEvent(MotionEvent event) {
        if (mWindowManager == null || mLayoutParams == null) {
            return super.onTouchEvent(event);
        }

        switch (event.getAction()) {
            case MotionEvent.ACTION_DOWN:
                mInitialX = mLayoutParams.x;
                mInitialY = mLayoutParams.y;
                mInitialTouchX = event.getRawX();
                mInitialTouchY = event.getRawY();
                mTouchDownTime = System.currentTimeMillis();
                mIsDragging = false;
                return true;

            case MotionEvent.ACTION_MOVE:
                float dx = event.getRawX() - mInitialTouchX;
                float dy = event.getRawY() - mInitialTouchY;

                if (Math.abs(dx) > 10 || Math.abs(dy) > 10 || mIsDragging) {
                    mIsDragging = true;
                    mLayoutParams.x = mInitialX + (int) dx;
                    mLayoutParams.y = mInitialY + (int) dy;

                    // Clamp to screen boundaries
                    int screenWidth = getResources().getDisplayMetrics().widthPixels;
                    int screenHeight = getResources().getDisplayMetrics().heightPixels;
                    int halfWidth = getWidth() / 2;
                    int halfHeight = getHeight() / 2;

                    mLayoutParams.x = Math.max(-halfWidth, Math.min(screenWidth - halfWidth, mLayoutParams.x));
                    mLayoutParams.y = Math.max(0, Math.min(screenHeight - halfHeight, mLayoutParams.y));

                    try {
                        mWindowManager.updateViewLayout(this, mLayoutParams);
                        if (mListener != null) {
                            mListener.onSphereMoved(mLayoutParams.x, mLayoutParams.y);
                        }
                    } catch (Exception ignored) {}
                }
                return true;

            case MotionEvent.ACTION_UP:
                long duration = System.currentTimeMillis() - mTouchDownTime;
                if (!mIsDragging && duration < 350) {
                    // Tap detected!
                    performClick();
                    if (mListener != null) {
                        mListener.onSphereTapped();
                    }
                } else if (mIsDragging) {
                    // Snap to nearest horizontal edge (left or right)
                    snapToEdge();
                }
                mIsDragging = false;
                return true;
        }
        return super.onTouchEvent(event);
    }

    @Override
    public boolean performClick() {
        super.performClick();
        return true;
    }

    private void snapToEdge() {
        if (mWindowManager == null || mLayoutParams == null) return;
        int screenWidth = getResources().getDisplayMetrics().widthPixels;
        int targetX = (mLayoutParams.x + getWidth() / 2 < screenWidth / 2) ? 16 : (screenWidth - getWidth() - 16);

        ValueAnimator snapAnim = ValueAnimator.ofInt(mLayoutParams.x, targetX);
        snapAnim.setDuration(240);
        snapAnim.setInterpolator(new DecelerateInterpolator());
        snapAnim.addUpdateListener(anim -> {
            if (mLayoutParams != null && mWindowManager != null) {
                mLayoutParams.x = (int) anim.getAnimatedValue();
                try {
                    mWindowManager.updateViewLayout(this, mLayoutParams);
                } catch (Exception ignored) {}
            }
        });
        snapAnim.start();
    }

    private float dpToPx(float dp) {
        return dp * getResources().getDisplayMetrics().density;
    }

    @Override
    protected void onDetachedFromWindow() {
        if (mPhaseAnimator != null) {
            mPhaseAnimator.cancel();
        }
        if (mScaleAnimator != null) {
            mScaleAnimator.cancel();
        }
        super.onDetachedFromWindow();
    }
}
