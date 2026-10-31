package com.kirtan.iris.assistant.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val AssistantColors = darkColorScheme(
    primary = Color(0xFF22D3EE),
    onPrimary = Color(0xFF001018),
    secondary = Color(0xFF7C4DFF),
    background = Color.Transparent,
    surface = Color(0xFF0A1118),
    onSurface = Color(0xFFE6F7FF),
    error = Color(0xFFFF5252),
)

@Composable
fun AssistantTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = AssistantColors,
        content = content,
    )
}
