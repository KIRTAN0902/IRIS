"""IRIS Decision Intelligence Layer.

Provides contextual decision making, constraint evaluation, goal analysis,
deterministic priority ranking, and AI reasoning.
"""

from __future__ import annotations

from app.intelligence.constraint_engine import (
    ConstraintEvaluation,
    RoutineBlock,
    evaluate_constraints,
    sanitize_duration_against_constraints,
)
from app.intelligence.context import (
    DecisionContextBuilder,
    build_decision_context,
    context_builder_instance,
)
from app.intelligence.decision_engine import decide_now, deterministic_decision
from app.intelligence.goal_engine import analyze_goals
from app.intelligence.priority_engine import (
    DEADLINE_TIERS,
    PriorityBreakdown,
    breakdown_to_dict,
    rank_tasks,
    score_task,
)
from app.intelligence.reasoning import DECISION_SYSTEM_PROMPT, reason_over_context
from app.intelligence.recommendation import (
    AlternativeOption,
    DecisionRecommendationOut,
    DecisionStep,
    DecisionType,
)

__all__ = [
    "decide_now",
    "deterministic_decision",
    "build_decision_context",
    "DecisionContextBuilder",
    "context_builder_instance",
    "evaluate_constraints",
    "sanitize_duration_against_constraints",
    "RoutineBlock",
    "ConstraintEvaluation",
    "analyze_goals",
    "score_task",
    "rank_tasks",
    "PriorityBreakdown",
    "DEADLINE_TIERS",
    "breakdown_to_dict",
    "reason_over_context",
    "DECISION_SYSTEM_PROMPT",
    "DecisionRecommendationOut",
    "DecisionType",
    "DecisionStep",
    "AlternativeOption",
]
