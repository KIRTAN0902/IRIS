"""Analytics service tests -- metrics derived from real activity records."""

from __future__ import annotations

from datetime import timedelta

from app.models.focus_session import FocusSession
from app.models.lead import Lead
from app.models.outreach import OutreachActivity
from app.models.startup import Startup
from app.services import analytics_service
from tests.conftest import make_task, utcnow


def _seed_startup(db, user_id) -> Startup:
    s = Startup(user_id=user_id, name="TestStartup", status="LAUNCHED")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_productivity_analytics_counts_completions(db, user_id):
    done = make_task(db, user_id, title="Done", status="COMPLETED")
    done.completed_at = utcnow()
    make_task(db, user_id, title="Open", deadline=utcnow() - timedelta(hours=1))
    db.commit()

    result = analytics_service.productivity_analytics(
        db, user_id, period="week", tz_name="Asia/Kolkata"
    )
    assert result.tasks_completed == 1
    assert result.tasks_overdue_open == 1


def test_time_analytics_uses_focus_sessions(db, user_id):
    task = make_task(db, user_id, area="STARTUP")
    db.add(
        FocusSession(
            user_id=user_id,
            task_id=task.id,
            started_at=utcnow(),
            ended_at=utcnow() + timedelta(minutes=50),
            planned_duration=60,
            actual_duration=50,
            status="COMPLETED",
        )
    )
    db.commit()

    result = analytics_service.time_analytics(db, user_id, period="today", tz_name="Asia/Kolkata")
    assert result.focused_minutes.STARTUP == 50.0
    assert result.total_focused_minutes == 50.0


def test_startup_funnel_metrics(db, user_id):
    startup = _seed_startup(db, user_id)
    lead = Lead(startup_id=startup.id, name="Prospect A")
    customer = Lead(startup_id=startup.id, name="Customer B", status="CUSTOMER")
    db.add_all([lead, customer])
    db.commit()
    db.refresh(lead)

    rows = [
        OutreachActivity(lead_id=lead.id, startup_id=startup.id, result="SENT"),
        OutreachActivity(lead_id=lead.id, startup_id=startup.id, result="NO_REPLY"),
        OutreachActivity(lead_id=lead.id, startup_id=startup.id, result="REPLIED"),
        OutreachActivity(lead_id=lead.id, startup_id=startup.id, result="MEETING_BOOKED"),
        OutreachActivity(lead_id=customer.id, startup_id=startup.id, result="CONVERTED"),
    ]
    db.add_all(rows)
    db.commit()

    result = analytics_service.startup_analytics(db, user_id)
    assert result.pipeline.leads_total == 2
    outreach = result.outreach
    assert outreach.total == 5
    # REPLIED + MEETING_BOOKED + CONVERTED count as positive replies.
    assert outreach.replies == 3
    assert outreach.meetings_booked == 2  # MEETING_BOOKED + CONVERTED
    assert outreach.conversions == 1
    assert outreach.reply_rate == 60.0
    assert result.customers == 1


def test_weekly_trends_buckets_are_contiguous(db, user_id):
    startup = _seed_startup(db, user_id)
    lead = Lead(startup_id=startup.id, name="L1")
    db.add(lead)
    db.commit()
    db.refresh(lead)
    db.add(
        OutreachActivity(lead_id=lead.id, startup_id=startup.id, timestamp=utcnow(), result="SENT")
    )
    db.commit()

    trends = analytics_service.startup_trends(db, user_id, weeks=4)
    assert len(trends.weeks) == 4
    total_sent = sum(w.outreach_sent for w in trends.weeks)
    assert total_sent == 1
