"""Central enum definitions.

Single source of truth for all categorical values in IRIS. Stored as plain
strings in the database for portability; validated via these Python enums at
the schema/service boundary.
"""

from __future__ import annotations

from enum import StrEnum


class StrEnum(StrEnum):
    """String-valued enum base so values serialize cleanly to JSON."""


class LifeArea(StrEnum):
    COLLEGE = "COLLEGE"
    INTERNSHIP = "INTERNSHIP"
    STARTUP = "STARTUP"
    PERSONAL = "PERSONAL"


class TaskPriority(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TaskStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


class EnergyLevel(StrEnum):
    DEEP_WORK = "DEEP_WORK"
    NORMAL = "NORMAL"
    LOW_ENERGY = "LOW_ENERGY"


class ProjectStatus(StrEnum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    ON_HOLD = "ON_HOLD"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class GoalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ACHIEVED = "ACHIEVED"
    BEHIND = "BEHIND"
    PAUSED = "PAUSED"
    ABANDONED = "ABANDONED"


class TimeBlockType(StrEnum):
    FOCUS = "FOCUS"
    BREAK = "BREAK"
    MEETING = "MEETING"
    PERSONAL = "PERSONAL"
    OTHER = "OTHER"


class TimeBlockStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class EventSource(StrEnum):
    INTERNAL = "INTERNAL"
    GOOGLE_CALENDAR = "GOOGLE_CALENDAR"
    OTHER = "OTHER"


class FocusStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    ABANDONED = "ABANDONED"


class LeadStatus(StrEnum):
    LEAD = "LEAD"
    CONTACTED = "CONTACTED"
    REPLIED = "REPLIED"
    INTERESTED = "INTERESTED"
    MEETING = "MEETING"
    CUSTOMER = "CUSTOMER"
    NOT_INTERESTED = "NOT_INTERESTED"
    LOST = "LOST"


class OutreachType(StrEnum):
    EMAIL = "EMAIL"
    LINKEDIN = "LINKEDIN"
    CALL = "CALL"
    WHATSAPP = "WHATSAPP"
    OTHER = "OTHER"


class OutreachResult(StrEnum):
    SENT = "SENT"
    NO_REPLY = "NO_REPLY"
    REPLIED = "REPLIED"
    MEETING_BOOKED = "MEETING_BOOKED"
    NOT_INTERESTED = "NOT_INTERESTED"
    CONVERTED = "CONVERTED"


class ExperimentStatus(StrEnum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class StartupStatus(StrEnum):
    IDEA = "IDEA"
    BUILDING = "BUILDING"
    LAUNCHED = "LAUNCHED"
    GROWING = "GROWING"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class AIRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"
    TOOL = "TOOL"


class ScheduleBlockType(StrEnum):
    FIXED = "FIXED"
    FLEXIBLE = "FLEXIBLE"
    UNAVAILABLE = "UNAVAILABLE"
    WORK = "WORK"
    PERSONAL = "PERSONAL"
    SLEEP = "SLEEP"
    BUFFER = "BUFFER"


class InformationProvenance(StrEnum):
    USER_PROVIDED = "USER_PROVIDED"
    SYSTEM_DERIVED = "SYSTEM_DERIVED"
    AI_INFERRED = "AI_INFERRED"
    UNKNOWN = "UNKNOWN"


class SignalDomain(StrEnum):
    TASKS = "TASKS"
    GOALS = "GOALS"
    COLLEGE = "COLLEGE"
    INTERNSHIP = "INTERNSHIP"
    STARTUP = "STARTUP"
    CALENDAR = "CALENDAR"
    EMAIL = "EMAIL"
    FINANCE = "FINANCE"
    DOCUMENTS = "DOCUMENTS"
    PERSONAL = "PERSONAL"
    SYSTEM = "SYSTEM"


class SignalType(StrEnum):
    DEADLINE_APPROACHING = "DEADLINE_APPROACHING"
    GOAL_BEHIND = "GOAL_BEHIND"
    OPPORTUNITY_INBOUND = "OPPORTUNITY_INBOUND"
    MEETING_UPCOMING = "MEETING_UPCOMING"
    ANOMALY_DETECTED = "ANOMALY_DETECTED"
    MISSING_INFO = "MISSING_INFO"
    STATUS_UPDATE = "STATUS_UPDATE"


class SignalSource(StrEnum):
    INTERNAL_TASKS = "INTERNAL_TASKS"
    INTERNAL_GOALS = "INTERNAL_GOALS"
    INTERNAL_SCHEDULE = "INTERNAL_SCHEDULE"
    INTERNAL_STARTUP = "INTERNAL_STARTUP"
    EXTERNAL_EMAIL = "EXTERNAL_EMAIL"
    EXTERNAL_CALENDAR = "EXTERNAL_CALENDAR"
    EXTERNAL_FINANCE = "EXTERNAL_FINANCE"
    MANUAL_INPUT = "MANUAL_INPUT"


class DecisionFeedbackStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"


class AttentionItemType(StrEnum):
    URGENT_DEADLINE = "URGENT_DEADLINE"
    MISSED_GOAL = "MISSED_GOAL"
    OVERDUE_TASK = "OVERDUE_TASK"
    SCHEDULE_CONFLICT = "SCHEDULE_CONFLICT"
    STARTUP_TARGET_BEHIND = "STARTUP_TARGET_BEHIND"
    UNANSWERED_IMPORTANT_SIGNAL = "UNANSWERED_IMPORTANT_SIGNAL"
    MISSING_INFORMATION = "MISSING_INFORMATION"


AREA_STRATEGIC_WEIGHT: dict[str, float] = {
    LifeArea.STARTUP: 1.5,
    LifeArea.COLLEGE: 1.0,
    LifeArea.INTERNSHIP: 1.0,
    LifeArea.PERSONAL: 0.7,
}


# --- Personal finance ----------------------------------------------------------


class TransactionKind(StrEnum):
    EXPENSE = "EXPENSE"
    INCOME = "INCOME"


class PaymentAccount(StrEnum):
    UPI = "UPI"
    CASH = "CASH"
    CARD = "CARD"
    BANK = "BANK"
    WALLET = "WALLET"
    OTHER = "OTHER"


class BillFrequency(StrEnum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"
    ONCE = "ONCE"


class SavingsGoalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ACHIEVED = "ACHIEVED"
    ARCHIVED = "ARCHIVED"
