"""AI Reasoning Layer for Decision Intelligence.

Handles:
- Contextual reasoning over facts, preferences, goals, constraints, and current state
- Trade-off and opportunity cost evaluation
- Outcome-oriented recommendation formulation
- Guardrails against AI hallucinations and hard constraint violations
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.factory import get_ai_provider
from app.ai.provider import AIProviderError
from app.core.logging import get_logger
from app.intelligence.recommendation import (
    DecisionRecommendationOut,
)

logger = get_logger("iris.intelligence.reasoning")

DECISION_SYSTEM_PROMPT = """You are IRIS, a personal decision intelligence system \
for a high-performing founder-student.
Your mission is to answer ONE question with precision, rigor, and contextual intelligence:

"Given my current situation, what deserves my attention right now?"

CRITICAL PRINCIPLES:
1. CONTEXTUAL REASONING OVER FIXED FORMULAS:
   - Do NOT use fixed priority rules. Evaluate Facts, Preferences, Goals, Constraints, and State.
   - Situational Examples:
     * No urgent obligations + startup validation behind -> Recommend startup outreach.
     * Urgent college deadline -> Prioritize college assignment first; allocate rest to startup.
     * Urgent internship deliverable due soon -> Complete internship deliverable first.
     * Large free window (e.g. 2-3 hours) -> Generate a realistic multi-step sequence.

2. HARD CONSTRAINTS MUST NEVER BE VIOLATED:
   - Sleep time (23:00) and fixed routine/internship hours are non-negotiable hard constraints.
   - Duration must fit within the remaining flexible window.

3. OUTCOME ORIENTATION & EVIDENCE:
   - Focus on meaningful outcomes, not mere activity.
   - Cite concrete evidence data points in the 'evidence' list.
   - Distinguish OBSERVED facts from DERIVED insights and INFERRED hypotheses.

4. OPPORTUNITY COST:
   - Explicitly articulate trade-offs: Why is this option chosen over alternatives?

5. UNAVAILABLE DOMAINS & MISSING INFORMATION:
   - Check 'unavailable_domains' in context (e.g. EMAIL, FINANCE).
   - If requested information is in an unavailable domain, state clearly that
     the external service is not connected and return ASK_USER. NEVER fabricate
     unread emails, bank balances, or calendar events.
   - If a crucial deadline or constraint is missing, set decision_type to ASK_USER
     and specify 'missing_information'.

6. ZERO HALLUCINATIONS:
   - Reason strictly from the JSON context provided.
   - For recommendation_type = "TASK", task_id MUST be an exact ID from ranked_tasks.

JSON SCHEMA REQUIREMENT:
Respond with a JSON object matching this structure:
{
  "recommendation_type": "TASK" | "BREAK" | "REST" | "STRATEGIC_NOTE" | "SEQUENCE" | "ASK_USER",
  "decision_type": "MUST_DO" | "SHOULD_DO" | "COULD_DO" | "WAIT" | "ASK_USER",
  "decision": "STARTUP_OUTREACH" | "COLLEGE_ASSIGNMENT" | "INTERNSHIP_DELIVERABLE" | "DEEP_WORK",
  "task_id": int or null,
  "title": "Actionable title",
  "reason": "Clear contextual explanation citing concrete facts",
  "evidence": ["Data point 1", "Data point 2"],
  "observed_facts": ["Directly observed fact 1"],
  "derived_insights": ["System derived metric 1"],
  "duration_minutes": int or null,
  "expected_outcome": "Concrete, measurable outcome",
  "confidence": float (0.0 to 1.0),
  "opportunity_cost": "Explanation of trade-offs and what is deferred",
  "sequence": [
    {"step_number": 1, "title": "Step 1", "task_id": int or null, "duration_minutes": 60}
  ],
  "missing_information": str or null
}
"""


def _context_task_ids(context: dict[str, Any]) -> set[int]:
    return {t["task"]["id"] for t in context.get("ranked_tasks", [])}


async def reason_over_context(
    context: dict[str, Any],
    *,
    fallback: DecisionRecommendationOut,
) -> tuple[DecisionRecommendationOut, str]:
    """Invoke AI provider to reason over the decision context and validate guardrails.

    Returns:
        (DecisionRecommendationOut, source) where source is 'AI' or 'DETERMINISTIC'
    """
    provider = get_ai_provider()
    if not provider.enabled:
        return fallback, "DETERMINISTIC"

    context_json = json.dumps(context, default=str)

    try:
        result = await provider.generate_structured(
            system=DECISION_SYSTEM_PROMPT,
            prompt=f"CONTEXT (JSON):\n```json\n{context_json}\n```\n\nWhat should I do right now?",
            schema=DecisionRecommendationOut,
        )

        valid_ids = _context_task_ids(context)

        # Guardrail 1: If recommendation is a TASK, task_id must exist in context
        if result.recommendation_type == "TASK":
            if result.task_id is None or result.task_id not in valid_ids:
                logger.info(
                    "AI task_id %s not found in candidate tasks; falling back to deterministic",
                    result.task_id,
                )
                return fallback, "DETERMINISTIC"

        # Guardrail 2: Enforce hard constraints (duration cannot exceed available window)
        available_m = context.get("available_minutes")
        if available_m and result.duration_minutes:
            if result.duration_minutes > available_m:
                result.duration_minutes = available_m

        # Guardrail 3: In a sequence, filter any invalid task_ids
        if result.sequence:
            clean_seq = []
            for step in result.sequence:
                if step.task_id is not None and step.task_id not in valid_ids:
                    step.task_id = None
                clean_seq.append(step)
            result.sequence = clean_seq

        return result, "AI"

    except (AIProviderError, Exception) as exc:
        from app.ai.health import ai_health

        ai_health.record_failure(provider.name, provider.model, exc)
        logger.warning(
            "Decision reasoning fallback to deterministic due to: %s: %s",
            type(exc).__name__,
            exc,
        )
        return fallback, "DETERMINISTIC"
