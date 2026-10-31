package com.kirtan.iris.assistant

import android.content.Context
import android.content.Intent

/**
 * Every supported activation path funnels into this object. If IRIS is the
 * selected digital assistant it asks the live VoiceInteractionService to show the
 * real system session. Otherwise it opens the same native assistant UI as a
 * translucent activity over whatever the user is doing.
 */
object AssistantLauncher {

    const val EXTRA_SOURCE = "com.kirtan.iris.assistant.EXTRA_SOURCE"
    const val ACTION_WAKE = "com.kirtan.iris.assistant.ACTION_WAKE"
    const val ACTION_SETTINGS = "com.kirtan.iris.assistant.ACTION_SETTINGS"
    const val ACTION_CAPTURE_SCREEN = "com.kirtan.iris.assistant.ACTION_CAPTURE_SCREEN"

    @JvmStatic
    fun launch(context: Context, source: AssistantSource) {
        if (CapabilityDetector.isDefaultAssistant(context) &&
            IrisVoiceInteractionService.requestShowSession(source)
        ) {
            return
        }
        context.startActivity(entryIntent(context, source))
    }

    fun entryIntent(context: Context, source: AssistantSource): Intent {
        return Intent(context, AssistantEntryActivity::class.java).apply {
            action = ACTION_WAKE
            putExtra(EXTRA_SOURCE, source.name)
            addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK or
                    Intent.FLAG_ACTIVITY_CLEAR_TOP or
                    Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS,
            )
        }
    }

    @JvmStatic
    fun openSettings(context: Context) {
        context.startActivity(
            Intent(context, AssistantSettingsActivity::class.java).addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP,
            ),
        )
    }

    fun sourceFrom(intent: Intent?): AssistantSource {
        val raw = intent?.getStringExtra(EXTRA_SOURCE) ?: return AssistantSource.IN_APP
        return runCatching { AssistantSource.valueOf(raw) }.getOrDefault(AssistantSource.IN_APP)
    }
}
