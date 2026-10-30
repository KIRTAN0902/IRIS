package com.kirtan.iris;

/**
 * Common contract for IRIS ambient visual interfaces (OverlayView and Floating SphereView).
 */
public interface IrisVisualContainer {
    int STATE_IDLE = 0;
    int STATE_ACTIVATING = 1;
    int STATE_LISTENING = 2;
    int STATE_PROCESSING = 3;
    int STATE_EXECUTING = 4;
    int STATE_SPEAKING = 5;
    int STATE_APPROVAL_REQUIRED = 6;
    int STATE_ERROR = 7;
    int STATE_DISMISSING = 8;

    void setState(int state);
    void setAudioAmplitude(float normalizedAmp);
    void setStatusText(String text);
    int getState();
}
