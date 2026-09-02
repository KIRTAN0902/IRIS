"""Live Supabase Transaction Pooler Operation & Sequence Verification."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import normalize_database_url
from app.models.enums import LifeArea, TaskPriority, TaskStatus
from app.models.goal import Goal
from app.models.lead import Lead
from app.models.recurring_schedule import RecurringSchedule
from app.models.task import Task
from app.models.user import User


def main():
    print("=" * 70)
    print("LIVE SUPABASE TRANSACTION POOLER (:6543) CRUD & SEQUENCE TEST")
    print("=" * 70)

    url = normalize_database_url(settings.database_url)
    engine = create_engine(url, poolclass=NullPool, pool_pre_ping=True)
    SessionMaker = sessionmaker(bind=engine, autoflush=False)
    session: Session = SessionMaker()

    try:
        # 1. Query User
        user = session.execute(select(User)).scalars().first()
        assert user is not None, "User record not found in Supabase"
        print(f"[OK] User found: id={user.id}, email='{user.email}', name='{user.name}'")

        # 2. Query Existing Migrated Data
        task_count = session.query(Task).filter(Task.user_id == user.id).count()
        goal_count = session.query(Goal).filter(Goal.user_id == user.id).count()
        lead_count = session.query(Lead).count()
        routine_count = (
            session.query(RecurringSchedule)
            .filter(RecurringSchedule.user_id == user.id)
            .count()
        )
        print(
            f"[OK] Migrated records: tasks={task_count}, goals={goal_count}, "
            f"leads={lead_count}, routines={routine_count}"
        )

        # 3. Test New Record Insertion (Sequence Check)
        print("\n[Testing Sequence & Auto-Increment]")
        new_task = Task(
            user_id=user.id,
            title="Live Supabase Verification Task",
            area=LifeArea.STARTUP.value,
            priority=TaskPriority.HIGH.value,
            status=TaskStatus.TODO.value,
            estimated_duration=20,
        )
        session.add(new_task)
        session.commit()
        session.refresh(new_task)
        print(
            f"[OK] Successfully inserted new task with auto-generated ID={new_task.id} "
            "(Sequence working!)"
        )

        # 4. Test Update
        new_task.status = TaskStatus.COMPLETED.value
        session.commit()
        session.refresh(new_task)
        assert new_task.status == TaskStatus.COMPLETED.value
        print(f"[OK] Successfully updated task status to '{new_task.status}'")

        # 5. Test Deletion
        session.delete(new_task)
        session.commit()
        print("[OK] Successfully deleted temporary verification task")

        print("\n" + "=" * 70)
        print("ALL LIVE SUPABASE OPERATIONS (READ, WRITE, SEQUENCE, DELETE) PASSED!")
        print("=" * 70)

    finally:
        session.close()


if __name__ == "__main__":
    main()
