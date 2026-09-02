"""Deterministic priority engine.

Scores open tasks on a 0-100 scale using transparent, configurable weights.
Gemini never computes priorities; it only reasons over this engine's output.

Re-exports and wraps the intelligence layer's priority engine for seamless backward compatibility.
"""

from __future__ import annotations

from app.intelligence.priority_engine import (
    DEADLINE_TIERS,
    EFFORT_FIT_BONUS,
    EFFORT_MISFIT_PENALTY,
    ENERGY_FIT_BONUS,
    FAR_DEADLINE_SCORE,
    GOAL_ALIGNMENT_SCORE,
    GOAL_NEAR_COMPLETION_BONUS,
    IN_PROGRESS_BOOST,
    NO_DEADLINE_SCORE,
    OVERDUE_PENALTY,
    PRIORITY_SCORES,
    PriorityBreakdown,
    _deadline_score,
    _goal_alignment,
    _strategic_score,
    breakdown_to_dict,
    rank_tasks,
    score_task,
)

__all__ = [
    "DEADLINE_TIERS",
    "NO_DEADLINE_SCORE",
    "FAR_DEADLINE_SCORE",
    "PRIORITY_SCORES",
    "OVERDUE_PENALTY",
    "GOAL_ALIGNMENT_SCORE",
    "GOAL_NEAR_COMPLETION_BONUS",
    "EFFORT_FIT_BONUS",
    "EFFORT_MISFIT_PENALTY",
    "IN_PROGRESS_BOOST",
    "ENERGY_FIT_BONUS",
    "PriorityBreakdown",
    "_deadline_score",
    "_strategic_score",
    "_goal_alignment",
    "score_task",
    "rank_tasks",
    "breakdown_to_dict",
]
