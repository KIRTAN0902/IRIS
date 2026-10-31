package com.kirtan.iris.assistant

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

/**
 * Process-wide assistant state. Both the system VoiceInteractionSession and the
 * fallback AssistantEntryActivity render from this same state, so every
 * activation path produces exactly one assistant experience.
 */
object AssistantRuntime {

    private val _state = MutableStateFlow(AssistantUiState())
    val state: StateFlow<AssistantUiState> = _state.asStateFlow()

    fun snapshot(): AssistantUiState = _state.value

    fun update(transform: (AssistantUiState) -> AssistantUiState) {
        _state.update(transform)
    }

    fun setState(state: AssistantState) = update { it.copy(state = state) }

    fun begin(source: AssistantSource, status: String = AssistantMessages.ACTIVATING) = update {
        it.copy(
            state = AssistantState.ACTIVATING,
            source = source,
            statusText = status,
            transcript = "",
            error = null,
            approvalText = "",
            connected = false,
            micLevel = 0f,
            outputLevel = 0f,
        )
    }

    fun connected() = update {
        it.copy(connected = true, state = AssistantState.LISTENING, statusText = AssistantMessages.LISTENING)
    }

    fun listening() = update {
        it.copy(state = AssistantState.LISTENING, statusText = AssistantMessages.LISTENING, error = null)
    }

    fun transcript(text: String) = update {
        it.copy(transcript = text, statusText = if (it.state == AssistantState.SPEAKING) AssistantMessages.SPEAKING else AssistantMessages.THINKING)
    }

    fun status(text: String) = update { it.copy(statusText = text) }

    fun levels(mic: Float? = null, output: Float? = null) = update {
        it.copy(
            micLevel = mic ?: it.micLevel,
            outputLevel = output ?: it.outputLevel,
        )
    }

    fun fail(message: String) = update {
        it.copy(
            state = AssistantState.ERROR,
            statusText = message,
            error = message,
            connected = false,
            micLevel = 0f,
            outputLevel = 0f,
        )
    }

    fun hotword(status: HotwordStatus) = update { it.copy(hotword = status) }

    fun foreground(packageName: String) = update { it.copy(foregroundPackage = packageName) }

    fun approval(text: String) = update {
        it.copy(state = AssistantState.APPROVAL_REQUIRED, statusText = AssistantMessages.APPROVAL, approvalText = text)
    }

    fun standby() {
        _state.value = AssistantUiState(hotword = _state.value.hotword)
    }
}
