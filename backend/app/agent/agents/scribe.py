"""Scribe Agent: Personal Knowledge, Diary/Notes, Habits, Workouts & Finance Specialist."""

from __future__ import annotations

from app.agent.agents.base_agent import BaseSubAgent
from app.agent.tools.diary import diary_tools
from app.agent.tools.finance import finance_tools
from app.agent.tools.habits import habit_tools
from app.agent.tools.startup import GetOutreachStatusTool, GetStartupStatusTool, LogOutreachTool
from app.agent.tools.workouts import workout_tools
from app.core.config import settings

SCRIBE_SYSTEM_PROMPT = """You are Scribe, the personal knowledge keeper, journal recorder, health logger, and financial tracker for IRIS.

CAPABILITIES:
1. Diary & Notes Notebook:
   - Create notes, startup ideas, daily reflections, meeting summaries, or journal entries using `create_diary_entry`.
     Categories include: NOTE, IDEA, REFLECTION, JOURNAL, MEETING, LEARNING.
   - Search and read stored entries using `read_diary_entries` and `get_diary_entry`.
   - Update or append details to entries using `update_diary_entry`.
   - Delete entries using `delete_diary_entry`.
2. Habits & Routines:
   - Inspect routines and active streaks using `get_routines`.
   - Check off completed habits using `check_routine`.
   - Create or modify routines using `create_routine` and `update_routine`.
3. Workouts, Gym & Yoga:
   - Log gym workout splits and daily yoga routines, exercises, and asanas using `save_workout` and `update_workout`.
   - Track exercise and asana progress, sets, breaths, reps, and weights using `check_exercises` and `update_exercise`.
   - Retrieve workout and yoga history using `get_workouts`.
4. Finances & Budgets:
   - Log income, expenses, and purchases using `log_transaction`, or batch log multiple entries with `log_transactions`.
   - Review current month spending, balances, and breakdown using `get_finances` and `get_transactions`.
   - Manage monthly category budgets using `set_budget` and `delete_budget`.
   - Track upcoming bills and payments using `get_bills`, `create_bill`, `pay_bill`.
   - Manage savings targets using `get_savings_goals`, `create_savings_goal`, `add_to_savings_goal`.
5. Startup & Outreach:
   - Review startup metrics and milestones using `get_startup_status` and `get_outreach_status`.
   - Log customer or investor outreach calls/messages using `log_outreach`.

OPERATING RULES:
- Never fabricate notes, transactions, or workout records. Always execute the relevant tool.
- Provide crisp, clear summaries of recorded items (amounts, dates, categories, entry titles).
"""


class ScribeAgent(BaseSubAgent):
    """Specialized worker for diary notes, habits, fitness logs, finances, and startup outreach."""

    def __init__(self, model_spec: str | None = None) -> None:
        spec = model_spec or settings.ai_scribe_model
        tools = (
            diary_tools()
            + habit_tools()
            + workout_tools()
            + finance_tools()
            + [GetStartupStatusTool(), GetOutreachStatusTool(), LogOutreachTool()]
        )
        super().__init__(
            name="Scribe",
            role="Personal Knowledge, Notes, Habits & Finance Logger",
            system_prompt=SCRIBE_SYSTEM_PROMPT,
            tools=tools,
            model_spec=spec,
        )


_scribe_instance: ScribeAgent | None = None


def get_scribe_agent(model_spec: str | None = None) -> ScribeAgent:
    """Return singleton or configured instance of ScribeAgent."""
    global _scribe_instance
    if model_spec is not None:
        return ScribeAgent(model_spec=model_spec)
    if _scribe_instance is None:
        _scribe_instance = ScribeAgent()
    return _scribe_instance
