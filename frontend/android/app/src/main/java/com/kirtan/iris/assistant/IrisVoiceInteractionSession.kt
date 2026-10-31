package com.kirtan.iris.assistant

import android.app.assist.AssistContent
import android.app.assist.AssistStructure
import android.content.Context
import android.graphics.Bitmap
import android.os.Bundle
import android.service.voice.VoiceInteractionSession
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.FrameLayout
import androidx.compose.ui.platform.ComposeView
import androidx.lifecycle.setViewTreeLifecycleOwner
import androidx.lifecycle.setViewTreeViewModelStoreOwner
import androidx.savedstate.setViewTreeSavedStateRegistryOwner
import com.kirtan.iris.IrisScreenCaptureManager
import com.kirtan.iris.assistant.ui.AssistantOverlay
import com.kirtan.iris.assistant.ui.AssistantTheme
import com.kirtan.iris.assistant.voice.VoiceSessionController

/**
 * The actual system assistant session. Its window is owned by Android, appears
 * over the current application (and over keyguard where Android permits), and
 * is completely independent of MainActivity and the Capacitor WebView.
 */
class IrisVoiceInteractionSession(context: Context) : VoiceInteractionSession(context) {

    companion object {
        private const val TAG = "IRIS_AssistSession"
    }

    private var controller: VoiceSessionController? = null
    private var lifecycleOwner: AssistantViewLifecycleOwner? = null
    private var source: AssistantSource = AssistantSource.IN_APP

    override fun onCreateContentView(): View {
        val owner = AssistantViewLifecycleOwner()
        lifecycleOwner = owner

        val container = FrameLayout(getContext()).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            )
            setBackgroundColor(android.graphics.Color.TRANSPARENT)
        }

        val compose = ComposeView(getContext()).apply {
            setViewTreeLifecycleOwner(owner)
            setViewTreeSavedStateRegistryOwner(owner)
            setViewTreeViewModelStoreOwner(owner)
            setContent {
                AssistantTheme {
                    AssistantOverlay(
                        stateFlow = AssistantRuntime.state,
                        onDismiss = { controller?.stop(AssistantState.DISMISSING) ?: hide() },
                        onInterrupt = { controller?.interrupt() },
                        onOpenSettings = { AssistantLauncher.openSettings(getContext()) },
                        onRetry = { controller?.restart() },
                    )
                }
            }
        }
        container.addView(
            compose,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT,
            ),
        )
        return container
    }

    override fun onShow(args: Bundle?, flags: Int) {
        super.onShow(args, flags)
        source = runCatching {
            AssistantSource.valueOf(args?.getString(IrisVoiceInteractionService.EXTRA_SOURCE) ?: "")
        }.getOrDefault(AssistantSource.ASSIST_GESTURE)

        Log.i(TAG, "Session shown from $source, flags=$flags")

        window?.window?.apply {
            addFlags(
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS or
                    WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS,
            )
            setGravity(Gravity.BOTTOM)
            setDimAmount(0.12f)
        }

        controller?.stop()
        controller = VoiceSessionController(getContext(), source) {
            hide()
        }
        controller?.start()
    }

    override fun onHandleAssist(
        data: Bundle?,
        structure: AssistStructure?,
        content: AssistContent?,
    ) {
        super.onHandleAssist(data, structure, content)
        val packageName = structure?.activityComponent?.packageName
        if (!packageName.isNullOrBlank()) {
            AssistantRuntime.foreground(packageName)
            Log.i(TAG, "Foreground app at activation: $packageName")
        }
    }

    override fun onHandleScreenshot(screenshot: Bitmap?) {
        super.onHandleScreenshot(screenshot)
        if (screenshot != null) {
            Log.i(TAG, "OS assist screenshot ${screenshot.width}x${screenshot.height} captured in memory")
            IrisScreenCaptureManager.setAssistScreenshot(screenshot)
        }
    }

    override fun onHide() {
        Log.i(TAG, "Session hidden")
        controller?.stop()
        controller = null
        AssistantRuntime.standby()
        lifecycleOwner?.destroy()
        lifecycleOwner = null
        super.onHide()
    }
}
