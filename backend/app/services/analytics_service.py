"""Analytics service.

Derives all metrics from underlying records (focus sessions, time blocks,
tasks, leads, outreach activities) rather than duplicating data.

All durations are expressed in minutes. Day boundaries respect the user's
timezone; comparisons happen in naive UTC.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func as safunc
from sqlalchemy.orm import Session

from app.core.errors import ValidationAppError
from app.models.enums import (
    ExperimentStatus,
    FocusStatus,
    LeadStatus,
    LifeArea,
    OutreachResult,
)
from app.models.experiment import Experiment
from app.models.focus_session import FocusSession
from app.models.goal import Goal
from app.models.lead import Lead
from app.models.outreach import OutreachActivity
from app.models.startup import Startup
from app.models.task import Task
from app.models.time_block import TimeBlock
from app.schemas.analytics import (
    AreaMinutes,
    OutreachTotals,
    ProductivityAnalytics,
    StartupAnalytics,
    StartupPipelineCounts,
    StartupTrends,
    TimeAnalytics,
    WeeklyTrendPoint,
)
from app.services.startup_service import get_startup
from app.utils.datetime import localize_date_boundaries, utcnow

REPLY_RESULTS = {OutreachResult.REPLIED.value}
MEETING_RESULTS = {OutreachResult.MEETING_BOOKED.value}
CONVERSION_RESULTS = {OutreachResult.CONVERTED.value}


def resolve_range(
    period: str,
    tz_name: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return naive-UTC [start, end) for a named period in user's timezone."""
    today_in_tz = utcnow().astimezone(tz=None).date() if tz_name == "UTC" else None
    if today_in_tz is None:
        from zoneinfo import ZoneInfo

        today_in_tz = utcnow().replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(tz_name)).date()

    if period == "today":
        return localize_date_boundaries(today_in_tz, tz_name)
    if period == "week":
        week_start = today_in_tz - timedelta(days=today_in_tz.weekday())
        s, _ = localize_date_boundaries(week_start, tz_name)
        _, e = localize_date_boundaries(today_in_tz + timedelta(days=1), tz_name)
        return s, e
    if period == "month":
        month_start = today_in_tz.replace(day=1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        s, _ = localize_date_boundaries(month_start, tz_name)
        _, e = localize_date_boundaries(next_month, tz_name)
        return s, e
    if period == "custom":
        if start is None or end is None:
            raise ValidationAppError("custom period requires 'start' and 'end' query parameters")
        return start, end
    raise ValidationAppError(f"Unknown period: {period}")


def _empty_area_minutes() -> AreaMinutes:
    return AreaMinutes()


# --- Time analytics ----------------------------------------------------------


def time_analytics(
    db: Session,
    user_id: int,
    *,
    period: str,
    tz_name: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> TimeAnalytics:
    range_start, range_end = resolve_range(period, tz_name, start=start, end=end)

    # Actual focused minutes per area, derived from completed/partial focus sessions.
    focused_rows = (
        db.query(Task.area, safunc.coalesce(safunc.sum(FocusSession.actual_duration), 0))
        .join(FocusSession, FocusSession.task_id == Task.id)
        .filter(
            FocusSession.user_id == user_id,
            FocusSession.started_at >= range_start,
            FocusSession.started_at < range_end,
            FocusSession.status.in_([FocusStatus.COMPLETED.value, FocusStatus.PARTIAL.value]),
        )
        .group_by(Task.area)
        .all()
    )

    # Planned minutes per area from FOCUS-type time blocks (durations summed in Python
    # so this stays dialect-portable).
    block_rows = (
        db.query(Task.area, TimeBlock.start_time, TimeBlock.end_time)
        .join(TimeBlock, TimeBlock.task_id == Task.id)
        .filter(
            TimeBlock.user_id == user_id,
            TimeBlock.start_time >= range_start,
            TimeBlock.start_time < range_end,
            TimeBlock.type == "FOCUS",
        )
        .all()
    )
    planned_by_area = _empty_area_minutes()
    for area, bstart, bend in block_rows:
        minutes = max(0, int((bend - bstart).total_seconds() // 60))
        if area in vars(planned_by_area):
            setattr(
                planned_by_area,
                area,
                round(getattr(planned_by_area, area) + minutes, 1),
            )

    focused = _area_minutes(focused_rows)
    total = sum(vars(focused).values())
    return TimeAnalytics(
        period=period,
        start=range_start,
        end=range_end,
        focused_minutes=focused,
        scheduled_minutes=planned_by_area,
        total_focused_minutes=float(total),
    )


def _area_minutes(rows: list[tuple[str | None, float]]) -> AreaMinutes:
    minutes = _empty_area_minutes()
    for area, value in rows:
        if area in vars(minutes):
            setattr(minutes, area, round(getattr(minutes, area) + float(value or 0), 1))
    return minutes


# --- Productivity analytics --------------------------------------------------


def productivity_analytics(
    db: Session,
    user_id: int,
    *,
    period: str,
    tz_name: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> ProductivityAnalytics:
    range_start, range_end = resolve_range(period, tz_name, start=start, end=end)

    completed = (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.completed_at.is_not(None),
            Task.completed_at >= range_start,
            Task.completed_at < range_end,
        )
        .count()
    )
    created = (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.created_at >= range_start,
            Task.created_at < range_end,
        )
        .count()
    )
    overdue_open = (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.deadline.is_not(None),
            Task.deadline < utcnow(),
            Task.status.in_(["TODO", "IN_PROGRESS"]),
        )
        .count()
    )

    planned_min, actual_min, completed_count = (
        db.query(
            safunc.coalesce(safunc.sum(Task.estimated_duration), 0),
            safunc.coalesce(safunc.sum(Task.actual_duration), 0),
            safunc.count(Task.id),
        )
        .filter(
            Task.user_id == user_id,
            Task.completed_at.is_not(None),
            Task.completed_at >= range_start,
            Task.completed_at < range_end,
        )
        .first()
    )
    avg = (float(actual_min) / completed_count) if completed_count else 0.0

    sessions, focus_minutes = (
        db.query(
            safunc.count(FocusSession.id),
            safunc.coalesce(safunc.sum(FocusSession.actual_duration), 0),
        )
        .filter(
            FocusSession.user_id == user_id,
            FocusSession.started_at >= range_start,
            FocusSession.started_at < range_end,
        )
        .first()
    )

    return ProductivityAnalytics(
        period=period,
        start=range_start,
        end=range_end,
        tasks_completed=completed,
        tasks_created=created,
        tasks_overdue_open=overdue_open,
        completion_rate=round((completed / created * 100.0) if created else 0.0, 1),
        planned_minutes=float(planned_min),
        actual_minutes=float(actual_min),
        average_task_duration_minutes=round(avg, 1),
        focus_sessions_count=sessions,
        focus_minutes=float(focus_minutes),
    )


# --- Startup analytics -------------------------------------------------------


def startup_analytics(db: Session, user_id: int, startup_id: int | None = None) -> StartupAnalytics:
    startup: Startup = get_startup(db, user_id, startup_id)

    status_rows = (
        db.query(Lead.status, safunc.count(Lead.id))
        .filter(Lead.startup_id == startup.id)
        .group_by(Lead.status)
        .all()
    )
    by_status = {status: count for status, count in status_rows}
    leads_total = sum(by_status.values())

    result_rows = (
        db.query(OutreachActivity.result, safunc.count(OutreachActivity.id))
        .filter(OutreachActivity.startup_id == startup.id)
        .group_by(OutreachActivity.result)
        .all()
    )
    counts = {result: count for result, count in result_rows}
    total_outreach = sum(counts.values())
    positive_results = REPLY_RESULTS | MEETING_RESULTS | CONVERSION_RESULTS
    replies = sum(v for k, v in counts.items() if k in positive_results)
    meetings = sum(v for k, v in counts.items() if k in MEETING_RESULTS | CONVERSION_RESULTS)
    conversions = counts.get(OutreachResult.CONVERTED.value, 0)

    def pct(n: int, d: int) -> float:
        return round(n / d * 100.0, 1) if d else 0.0

    active_goals = (
        db.query(Goal)
        .filter(Goal.user_id == user_id, Goal.area == LifeArea.STARTUP.value)
        .filter(Goal.status.in_(["ACTIVE", "BEHIND"]))
        .all()
    )
    goals_behind = [g.name for g in active_goals if g.target_value and g.progress_fraction < 0.5]

    running_experiments = (
        db.query(Experiment)
        .filter(
            Experiment.startup_id == startup.id,
            Experiment.status == ExperimentStatus.RUNNING.value,
        )
        .count()
    )

    return StartupAnalytics(
        startup_id=startup.id,
        startup_name=startup.name,
        pipeline=StartupPipelineCounts(leads_total=leads_total, by_status=by_status),
        outreach=OutreachTotals(
            total=total_outreach,
            sent=counts.get("SENT", 0) + counts.get("NO_REPLY", 0),
            replies=replies,
            meetings_booked=meetings,
            conversions=conversions,
            reply_rate=pct(replies, total_outreach),
            meeting_rate=pct(meetings, total_outreach),
            conversion_rate=pct(conversions, total_outreach),
        ),
        active_goals=len(active_goals),
        goals_behind=goals_behind,
        running_experiments=running_experiments,
        customers=by_status.get(LeadStatus.CUSTOMER.value, 0),
    )


def startup_trends(
    db: Session, user_id: int, *, weeks: int = 8, startup_id: int | None = None
) -> StartupTrends:
    startup = get_startup(db, user_id, startup_id)
    weeks = max(1, min(weeks, 26))
    today = utcnow().date()
    this_week_start = today - timedelta(days=today.weekday())
    first_week_start = this_week_start - timedelta(weeks=weeks - 1)
    first_week_dt = datetime.combine(first_week_start, datetime.min.time())

    points: dict[date, WeeklyTrendPoint] = {}
    for i in range(weeks):
        points[first_week_start + timedelta(weeks=i)] = WeeklyTrendPoint(
            week_start=first_week_start + timedelta(weeks=i)
        )

    new_leads = (
        db.query(safunc.date(Lead.created_at), safunc.count(Lead.id))
        .filter(Lead.startup_id == startup.id, Lead.created_at >= first_week_dt)
        .group_by(safunc.date(Lead.created_at))
        .all()
    )
    outreach_rows = (
        db.query(
            OutreachActivity.result,
            safunc.date(OutreachActivity.timestamp),
            safunc.count(OutreachActivity.id),
        )
        .filter(
            OutreachActivity.startup_id == startup.id,
            OutreachActivity.timestamp >= first_week_dt,
        )
        .group_by(OutreachActivity.result, safunc.date(OutreachActivity.timestamp))
        .all()
    )

    def bucket(d) -> date:
        if isinstance(d, str):
            d = date.fromisoformat(d)
        elif isinstance(d, datetime):
            d = d.date()
        ws = d - timedelta(days=d.weekday())
        return ws if ws in points else first_week_start

    for lead_date, count in new_leads:
        points[bucket(lead_date)].new_leads += count

    for result, ts_date, count in outreach_rows:
        p = points[bucket(ts_date)]
        if result in ("SENT", "NO_REPLY"):
            p.outreach_sent += count
        elif result in REPLY_RESULTS:
            p.replies += count
            p.outreach_sent += count
        elif result in MEETING_RESULTS:
            p.meetings += count
            p.replies += count
            p.outreach_sent += count
        elif result in CONVERSION_RESULTS:
            p.conversions += count
            p.outreach_sent += count

    return StartupTrends(startup_id=startup.id, weeks=[points[k] for k in sorted(points)])
