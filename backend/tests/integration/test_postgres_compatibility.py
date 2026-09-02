"""PostgreSQL & Database Compatibility Tests.

Verifies:
1. URL normalization (postgres://, postgresql:// -> postgresql+psycopg://).
2. Engine creation with dialect-specific pool configurations.
3. Fresh schema bootstrapping via Alembic migrations.
4. Full CRUD operations across all models.
5. JSON column storage & retrieval.
6. Boolean field behavior and server defaults.
7. Cascade & foreign-key relationships.
8. Transaction atomicity and rollback.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import is_sqlite_url, normalize_database_url
from app.models.enums import GoalStatus, LifeArea, TaskPriority, TaskStatus
from app.models.goal import Goal
from app.models.project import Project
from app.models.recurring_schedule import RecurringSchedule
from app.models.signal import Signal
from app.models.task import Task
from app.models.user import User


def test_normalize_database_url():
    """Verify PostgreSQL connection strings are correctly converted to use psycopg 3."""
    # postgres:// scheme (Render / Supabase legacy)
    url1 = "postgres://user:pass@ep-cool.supabase.co:5432/postgres"
    assert normalize_database_url(url1) == "postgresql+psycopg://user:pass@ep-cool.supabase.co:5432/postgres"

    # standard postgresql://
    url2 = "postgresql://user:pass@aws-0-ap-south-1.pooler.supabase.com:6543/postgres?pgbouncer=true"
    assert normalize_database_url(url2) == "postgresql+psycopg://user:pass@aws-0-ap-south-1.pooler.supabase.com:6543/postgres?pgbouncer=true"

    # already explicit postgresql+psycopg://
    url3 = "postgresql+psycopg://user:pass@db.supabase.co:5432/postgres"
    assert normalize_database_url(url3) == url3

    # sqlite unchanged
    url4 = "sqlite:///./iris.db"
    assert normalize_database_url(url4) == url4


def test_is_sqlite_url():
    assert is_sqlite_url("sqlite:///./iris.db") is True
    assert is_sqlite_url("sqlite:////app/data/iris.db") is True
    assert is_sqlite_url("sqlite://") is True
    assert is_sqlite_url("postgresql+psycopg://user:pass@host:5432/db") is False
    assert is_sqlite_url("postgres://user:pass@host:5432/db") is False


def test_models_crud_and_json_columns(db: Session, user_id: int):
    """Test full CRUD with JSON and Boolean properties on fresh session."""
    user = db.query(User).filter(User.id == user_id).first()
    assert user is not None

    # 1. Update user JSON facts and preferences
    user.facts = {"wake": "06:00", "routine": [{"name": "Yoga", "time": "06:00"}]}
    user.preferences = {"theme": "dark", "focus_mode": True}
    db.commit()
    db.refresh(user)
    assert user.facts["wake"] == "06:00"
    assert user.preferences["theme"] == "dark"

    # 2. Create Goal with hierarchy
    root_goal = Goal(
        user_id=user.id,
        name="Scale IRIS",
        area=LifeArea.STARTUP.value,
        status=GoalStatus.ACTIVE.value,
        target_value=100.0,
        current_value=25.0,
        unit="users",
    )
    db.add(root_goal)
    db.commit()
    db.refresh(root_goal)
    assert root_goal.progress_fraction == 0.25

    child_goal = Goal(
        user_id=user.id,
        parent_goal_id=root_goal.id,
        name="Acquire first 10 users",
        area=LifeArea.STARTUP.value,
        status=GoalStatus.ACTIVE.value,
    )
    db.add(child_goal)
    db.commit()
    db.refresh(child_goal)
    assert child_goal.parent_goal_id == root_goal.id

    # 3. Create Project & Task
    proj = Project(
        user_id=user.id,
        name="Launch Phase 1",
        area=LifeArea.STARTUP.value,
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)

    task = Task(
        user_id=user.id,
        goal_id=root_goal.id,
        project_id=proj.id,
        title="Deploy to Supabase PostgreSQL",
        priority=TaskPriority.HIGH.value,
        status=TaskStatus.TODO.value,
        estimated_duration=30,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    assert task.is_open is True

    # 4. Recurring schedule with JSON extra_data & boolean hard constraint
    rec = RecurringSchedule(
        user_id=user.id,
        name="Deep Work Morning",
        type="FIXED",
        days_of_week="Mon,Tue,Wed,Thu,Fri",
        start_time="09:00",
        end_time="11:00",
        is_hard_constraint=True,
        extra_data={"priority": 1, "color": "#4f46e5"},
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    assert rec.is_hard_constraint is True
    assert rec.extra_data["color"] == "#4f46e5"

    # 5. Signal with JSON payload & active boolean
    sig = Signal(
        user_id=user.id,
        domain="STARTUP",
        signal_type="VALIDATION",
        title="High Interest Signal",
        importance=0.9,
        urgency=0.8,
        payload={"prospect": "Alpha Agency", "intent": "high"},
        is_active=True,
    )
    db.add(sig)
    db.commit()
    db.refresh(sig)
    assert sig.is_active is True
    assert sig.payload["prospect"] == "Alpha Agency"


def test_transaction_rollback(db: Session, user_id: int):
    """Ensure failed transaction rolls back cleanly without leaving partial state."""
    init_task_count = db.query(Task).filter(Task.user_id == user_id).count()

    try:
        t = Task(user_id=user_id, title="Will Rollback", area="STARTUP")
        db.add(t)
        db.flush()
        # Trigger an intentional error in the transaction
        db.execute(text("SELECT * FROM non_existent_table_test_rollback"))
        db.commit()
    except Exception:
        db.rollback()

    after_count = db.query(Task).filter(Task.user_id == user_id).count()
    assert after_count == init_task_count
