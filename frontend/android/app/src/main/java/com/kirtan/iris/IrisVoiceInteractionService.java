package com.kirtan.iris;

import android.os.Bundle;
import android.service.voice.VoiceInteractionService;
import android.util.Log;

public class IrisVoiceInteractionService extends VoiceInteractionService {

    private static final String TAG = "IRIS_VoiceService";

    @Override
    public void onReady() {
        super.onReady();
        Log.i(TAG, "IrisVoiceInteractionService is ready and active as digital assistant.");
    }

    @Override
    public void onShutdown() {
        super.onShutdown();
        Log.i(TAG, "IrisVoiceInteractionService shutdown.");
    }
}
