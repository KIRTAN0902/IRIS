"""Import all models so Base.metadata and Alembic autogenerate see them."""

from app.models.ai_conversation import AIConversation, AIMessage
from app.models.ai_memory import AIMemory
from app.models.ai_recommendation import AIRecommendation
from app.models.calendar_event import CalendarEvent
from app.models.daily_review import DailyReview
from app.models.email_account import EmailAccount
from app.models.experiment import Experiment
from app.models.finance import FinanceBill, FinanceBudget, FinanceTransaction, SavingsGoal
from app.models.focus_session import FocusSession
from app.models.goal import Goal
from app.models.habit import Habit, HabitLog
from app.models.lead import Lead
from app.models.metric import Metric
from app.models.outreach import OutreachActivity
from app.models.project import Project
from app.models.recurring_schedule import RecurringSchedule
from app.models.signal import Signal
from app.models.startup import Startup
from app.models.task import Task
from app.models.time_block import TimeBlock
from app.models.user import User
from app.models.workout import Workout, WorkoutExercise, WorkoutLog

__all__ = [
    "AIConversation",
    "AIMemory",
    "AIMessage",
    "AIRecommendation",
    "CalendarEvent",
    "DailyReview",
    "EmailAccount",
    "Experiment",
    "FinanceBill",
    "FinanceBudget",
    "FinanceTransaction",
    "FocusSession",
    "Goal",
    "Habit",
    "HabitLog",
    "Lead",
    "Metric",
    "OutreachActivity",
    "Project",
    "SavingsGoal",
    "RecurringSchedule",
    "Signal",
    "Startup",
    "Task",
    "TimeBlock",
    "User",
    "Workout",
    "WorkoutExercise",
    "WorkoutLog",
]

