package com.kirtan.iris;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(PaymentPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
