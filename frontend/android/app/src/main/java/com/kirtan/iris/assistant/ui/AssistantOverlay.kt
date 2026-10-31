package com.kirtan.iris.assistant.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.kirtan.iris.assistant.AssistantState
import com.kirtan.iris.assistant.AssistantUiState
import kotlinx.coroutines.flow.StateFlow
import kotlin.math.cos
import kotlin.math.sin

/**
 * Premium, minimal assistant surface. There is no permanent floating shortcut
 * and no oversized ring button: just a luminous energy sphere that exists only
 * while IRIS is invoked, and a small state/transcript layer.
 */
@Composable
fun AssistantOverlay(
    stateFlow: StateFlow<AssistantUiState>,
    onDismiss: () -> Unit,
    onInterrupt: () -> Unit,
    onOpenSettings: () -> Unit,
    onRetry: () -> Unit,
) {
    val state by stateFlow.collectAsStateWithLifecycle()
    val palette = remember(state.state) { paletteFor(state.state) }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    0.0f to Color.Transparent,
                    0.55f to Color.Transparent,
                    1.0f to Color(0x66000000),
                ),
            ),
    ) {
        // Deliberately minimal: no opaque panel, no black circle button.
        Column(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .navigationBarsPadding()
                .padding(horizontal = 24.dp, vertical = 36.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            AnimatedVisibility(
                visible = state.transcript.isNotBlank() && state.state != AssistantState.ERROR,
                enter = fadeIn(),
                exit = fadeOut(),
            ) {
                TranscriptCard(state.transcript)
            }

            Spacer(Modifier.height(18.dp))

            StatusPill(text = state.statusText, accent = palette.accent, state = state.state)

            Spacer(Modifier.height(22.dp))

            EnergyOrb(
                state = state,
                accent = palette.accent,
                secondary = palette.secondary,
                onClick = {
                    when (state.state) {
                        AssistantState.ERROR -> onRetry()
                        AssistantState.DISMISSING -> Unit
                        else -> onInterrupt()
                    }
                },
            )

            Spacer(Modifier.height(18.dp))

            AnimatedVisibility(
                visible = state.state == AssistantState.ERROR,
                enter = fadeIn() + slideInVertically { it / 3 },
                exit = fadeOut() + slideOutVertically { it / 3 },
            ) {
                ErrorActions(
                    message = state.error ?: state.statusText,
                    onOpenSettings = onOpenSettings,
                    onRetry = onRetry,
                    onDismiss = onDismiss,
                )
            }

            AnimatedVisibility(
                visible = state.state == AssistantState.APPROVAL_REQUIRED,
                enter = fadeIn() + slideInVertically { it / 3 },
                exit = fadeOut() + slideOutVertically { it / 3 },
            ) {
                ApprovalActions(text = state.approvalText, onOpenSettings = onOpenSettings)
            }

            if (state.state != AssistantState.ERROR && state.state != AssistantState.APPROVAL_REQUIRED) {
                Spacer(Modifier.height(18.dp))
                Text(
                    text = hintFor(state.state),
                    color = Color(0xFF7DD3E8).copy(alpha = 0.62f),
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Medium,
                )
            }
        }

        Box(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .statusBarsPadding()
                .padding(20.dp)
                .size(38.dp)
                .clip(CircleShape)
                .background(Color(0x33000000))
                .clickable(onClick = onDismiss),
            contentAlignment = Alignment.Center,
        ) {
            Text("×", color = Color(0xFF9FE8F5), fontSize = 20.sp)
        }

        Column(
            modifier = Modifier
                .align(Alignment.TopStart)
                .statusBarsPadding()
                .padding(start = 22.dp, top = 24.dp)
                .alpha(0.6f),
        ) {
            Text(
                text = "IRIS",
                color = Color(0xFF67E8F9),
                fontSize = 13.sp,
                fontWeight = FontWeight.SemiBold,
                letterSpacing = 3.sp,
            )
            Text(
                text = sourceLabel(state),
                color = Color(0xFF8AA6B5),
                fontSize = 10.sp,
                letterSpacing = 0.6.sp,
            )
        }
    }
}

@Composable
private fun StatusPill(text: String, accent: Color, state: AssistantState) {
    val pulse by rememberInfiniteTransition(label = "statusPulse").animateFloat(
        initialValue = 0.55f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(1600, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "statusAlpha",
    )
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(Color(0x66060C12))
            .padding(horizontal = 14.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center,
    ) {
        Box(
            Modifier
                .size(6.dp)
                .alpha(if (state == AssistantState.STANDBY) 0.4f else pulse)
                .clip(CircleShape)
                .background(accent),
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text = text,
            color = Color(0xFFE7FBFF),
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium,
            letterSpacing = 0.3.sp,
        )
    }
}

@Composable
private fun TranscriptCard(text: String) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(20.dp))
            .background(Color(0xCC05090E))
            .padding(horizontal = 18.dp, vertical = 14.dp),
    ) {
        BasicText(
            text = text.takeLast(360),
            style = androidx.compose.ui.text.TextStyle(
                color = Color(0xFFD7F3FB),
                fontSize = 14.sp,
                lineHeight = 20.sp,
                textAlign = TextAlign.Center,
            ),
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun EnergyOrb(
    state: AssistantUiState,
    accent: Color,
    secondary: Color,
    onClick: () -> Unit,
) {
    val transition = rememberInfiniteTransition(label = "orb")
    val rotation by transition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(if (state.state == AssistantState.PROCESSING) 2600 else 9000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "rotation",
    )
    val counterRotation by transition.animateFloat(
        initialValue = 360f,
        targetValue = 0f,
        animationSpec = infiniteRepeatable(
            animation = tween(14000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "counterRotation",
    )
    val breathe by transition.animateFloat(
        initialValue = 0.94f,
        targetValue = 1.06f,
        animationSpec = infiniteRepeatable(
            animation = tween(2400, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "breathe",
    )

    val targetSize = when (state.state) {
        AssistantState.STANDBY -> 96f
        AssistantState.ACTIVATING -> 112f
        AssistantState.LISTENING -> 148f
        AssistantState.PROCESSING -> 132f
        AssistantState.EXECUTING -> 128f
        AssistantState.SPEAKING -> 158f
        AssistantState.APPROVAL_REQUIRED -> 120f
        AssistantState.ERROR -> 104f
        AssistantState.DISMISSING -> 72f
    }
    val size by animateFloatAsState(targetValue = targetSize, animationSpec = tween(420), label = "orbSize")
    val level by animateFloatAsState(
        targetValue = when (state.state) {
            AssistantState.LISTENING -> state.micLevel
            AssistantState.SPEAKING -> state.outputLevel
            else -> 0.12f
        },
        animationSpec = tween(120),
        label = "orbLevel",
    )

    Box(
        modifier = Modifier
            .size(size.dp)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(modifier = Modifier.fillMaxSize()) {
            val center = Offset(this.size.width / 2f, this.size.height / 2f)
            val base = this.size.minDimension / 2f * breathe
            val energy = base * (1f + level * 0.22f)

            // Volumetric outer glow (no solid circular button).
            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(accent.copy(alpha = 0.44f), accent.copy(alpha = 0.10f), Color.Transparent),
                    center = center,
                    radius = energy * 1.48f,
                ),
                radius = energy * 1.48f,
                center = center,
            )

            // Two restrained orbital arcs, never oversized rings.
            rotate(rotation, center) {
                drawArc(
                    brush = Brush.sweepGradient(
                        listOf(Color.Transparent, accent.copy(alpha = 0.85f), Color.Transparent),
                        center,
                    ),
                    startAngle = 18f,
                    sweepAngle = 118f,
                    useCenter = false,
                    topLeft = Offset(center.x - energy * 1.12f, center.y - energy * 1.12f),
                    size = Size(energy * 2.24f, energy * 2.24f),
                    style = Stroke(width = 2.2f, cap = StrokeCap.Round),
                )
            }
            rotate(counterRotation, center) {
                drawArc(
                    color = secondary.copy(alpha = 0.38f),
                    startAngle = 210f,
                    sweepAngle = 74f,
                    useCenter = false,
                    topLeft = Offset(center.x - energy * 1.24f, center.y - energy * 1.24f),
                    size = Size(energy * 2.48f, energy * 2.48f),
                    style = Stroke(width = 1.4f, cap = StrokeCap.Round),
                )
            }

            // The sphere itself: dark glass with a volumetric cyan core.
            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(
                        Color(0xFFF2FDFF),
                        accent.copy(alpha = 0.98f),
                        secondary.copy(alpha = 0.82f),
                        Color(0xFF071018),
                        Color(0xFF02060A),
                    ),
                    center = Offset(center.x - energy * 0.16f, center.y - energy * 0.22f),
                    radius = energy * 1.06f,
                ),
                radius = base,
                center = center,
            )

            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(Color.White.copy(alpha = 0.30f), Color.Transparent),
                    center = Offset(center.x - base * 0.30f, center.y - base * 0.38f),
                    radius = base * 0.56f,
                ),
                radius = base * 0.56f,
                center = Offset(center.x - base * 0.30f, center.y - base * 0.38f),
            )

            // Fine particle shimmer around the core.
            val particleCount = 7
            for (i in 0 until particleCount) {
                val angle = Math.toRadians((rotation * 0.55 + i * (360.0 / particleCount)).toDouble())
                val orbit = base * (1.18 + 0.04 * sin((rotation + i * 33) * Math.PI / 180.0))
                val x = center.x + (cos(angle) * orbit).toFloat()
                val y = center.y + (sin(angle) * orbit).toFloat()
                drawCircle(
                    color = Color.White.copy(alpha = 0.18f + 0.20f * level),
                    radius = 0.9f,
                    center = Offset(x, y),
                )
            }
        }
    }
}

@Composable
private fun ErrorActions(
    message: String,
    onOpenSettings: () -> Unit,
    onRetry: () -> Unit,
    onDismiss: () -> Unit,
) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = message,
            color = Color(0xFFFFB4AB),
            fontSize = 12.sp,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(horizontal = 12.dp),
        )
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.Center) {
            GlassButton("Settings", onOpenSettings)
            Spacer(Modifier.width(10.dp))
            GlassButton("Retry", onRetry)
            Spacer(Modifier.width(10.dp))
            GlassButton("Close", onDismiss)
        }
    }
}

@Composable
private fun ApprovalActions(text: String, onOpenSettings: () -> Unit) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = text,
            color = Color(0xFFFFE0A3),
            fontSize = 12.sp,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(10.dp))
        GlassButton("Review in IRIS", onOpenSettings)
    }
}

@Composable
private fun GlassButton(label: String, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(Color(0xCC0B141C))
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        Text(text = label, color = Color(0xFFBDEFFF), fontSize = 11.sp, fontWeight = FontWeight.Medium)
    }
}

private data class OrbPalette(val accent: Color, val secondary: Color)

private fun paletteFor(state: AssistantState): OrbPalette = when (state) {
    AssistantState.LISTENING -> OrbPalette(Color(0xFF22E8FF), Color(0xFF0EA5E9))
    AssistantState.PROCESSING -> OrbPalette(Color(0xFF9B7BFF), Color(0xFF6D28D9))
    AssistantState.EXECUTING -> OrbPalette(Color(0xFFFFC24B), Color(0xFFF97316))
    AssistantState.SPEAKING -> OrbPalette(Color(0xFF4DF3FF), Color(0xFF8B5CF6))
    AssistantState.APPROVAL_REQUIRED -> OrbPalette(Color(0xFFFFD166), Color(0xFFB45309))
    AssistantState.ERROR -> OrbPalette(Color(0xFFFF6B6B), Color(0xFF991B1B))
    AssistantState.ACTIVATING -> OrbPalette(Color(0xFF67E8F9), Color(0xFF2563EB))
    AssistantState.DISMISSING -> OrbPalette(Color(0xFF67E8F9), Color(0xFF1E3A8A))
    AssistantState.STANDBY -> OrbPalette(Color(0xFF4DD0E1), Color(0xFF1E40AF))
}

private fun hintFor(state: AssistantState): String = when (state) {
    AssistantState.LISTENING -> "Tap the sphere to stop listening"
    AssistantState.SPEAKING -> "Tap the sphere to interrupt"
    AssistantState.PROCESSING -> "Working through the IRIS reasoning layer"
    AssistantState.EXECUTING -> "Executing through the IRIS capability registry"
    AssistantState.ACTIVATING -> "Connecting to IRIS"
    AssistantState.DISMISSING -> "Closing"
    AssistantState.STANDBY -> "Say \"Hey IRIS\""
    AssistantState.APPROVAL_REQUIRED -> "Approval is required"
    AssistantState.ERROR -> "Tap Retry or open Settings"
}

private fun sourceLabel(state: AssistantUiState): String = when (state.source) {
    com.kirtan.iris.assistant.AssistantSource.HOTWORD -> "HOTWORD"
    com.kirtan.iris.assistant.AssistantSource.ASSIST_GESTURE -> "ASSISTANT GESTURE"
    com.kirtan.iris.assistant.AssistantSource.QUICK_TILE -> "QUICK SETTINGS"
    com.kirtan.iris.assistant.AssistantSource.SHORTCUT -> "SHORTCUT"
    com.kirtan.iris.assistant.AssistantSource.WIDGET -> "WIDGET"
    com.kirtan.iris.assistant.AssistantSource.NOTIFICATION -> "NOTIFICATION"
    com.kirtan.iris.assistant.AssistantSource.IN_APP -> "IN APP"
    com.kirtan.iris.assistant.AssistantSource.TEST -> "DIAGNOSTIC"
}
