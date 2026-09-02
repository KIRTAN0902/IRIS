"""Signals package -- cross-domain signal ingestion, providers, and relevance."""

from app.intelligence.signals.base import SignalData, SignalProvider, SignalQuery
from app.intelligence.signals.providers import (
    DEFAULT_SIGNAL_PROVIDERS,
    GoalSignalProvider,
    ScheduleSignalProvider,
    StartupSignalProvider,
    TaskSignalProvider,
)
from app.intelligence.signals.relevance import filter_relevant_signals
from app.intelligence.signals.repository import SignalRepository, signal_repo

__all__ = [
    "DEFAULT_SIGNAL_PROVIDERS",
    "GoalSignalProvider",
    "ScheduleSignalProvider",
    "SignalData",
    "SignalProvider",
    "SignalQuery",
    "SignalRepository",
    "StartupSignalProvider",
    "TaskSignalProvider",
    "filter_relevant_signals",
    "signal_repo",
]
