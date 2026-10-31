package com.kirtan.iris.assistant

import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import android.service.quicksettings.TileService
import androidx.annotation.RequiresApi

/**
 * Quick Settings tile. It shows the real system assistant session when IRIS is
 * the default assistant; otherwise it opens the translucent native session.
 */
@RequiresApi(Build.VERSION_CODES.N)
class AssistantTileService : TileService() {

    override fun onClick() {
        super.onClick()

        if (CapabilityDetector.isDefaultAssistant(this) &&
            IrisVoiceInteractionService.requestShowSession(AssistantSource.QUICK_TILE)
        ) {
            return
        }

        val intent = AssistantLauncher.entryIntent(this, AssistantSource.QUICK_TILE)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            val pending = PendingIntent.getActivity(
                this,
                0,
                intent,
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
            startActivityAndCollapse(pending)
        } else {
            @Suppress("DEPRECATION")
            startActivityAndCollapse(intent)
        }
    }
}
