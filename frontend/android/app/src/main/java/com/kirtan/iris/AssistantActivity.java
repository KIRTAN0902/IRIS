package com.kirtan.iris;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;

public class AssistantActivity extends Activity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        Intent intent = new Intent(this, MainActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        intent.putExtra("action", "voice");
        startActivity(intent);

        finish();
    }
}
