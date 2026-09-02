"""Shared pytest fixtures.

Environment variables are set BEFORE any ``app`` import so that
``app.core.config.settings`` binds to an isolated throwaway database and AI is
disabled (deterministic-only) unless a test explicitly mocks Gemini.

Each test gets a fresh schema: drop_all -> create_all on the shared engine.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

_TMP_DIR = Path(tempfile.mkdtemp(prefix="iris-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP_DIR / 'test.db').as_posix()}"
os.environ["AI_PROVIDER"] = "gemini"
os.environ["GEMINI_API_KEY"] = ""
os.environ["OMNIROUTE_BASE_URL"] = ""
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEFAULT_TIMEZONE", "Asia/Kolkata")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.models  # noqa: F401,E402 -- register all models on Base.metadata
from app.ai.factory import reset_ai_provider  # noqa: E402
from app.core.database import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_ai():
    """Ensure clean AI provider state between tests."""
    reset_ai_provider()
    yield
    reset_ai_provider()


@pytest.fixture()
def db() -> Session:
    """Fresh, empty database per test."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db) -> TestClient:
    """Test client; lifespan creates the default single user in the test DB."""
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def user_id(db: Session) -> int:
    """The default single user, created on demand."""
    from app.core.security import get_current_user

    return get_current_user(db).id


# --- factories ----------------------------------------------------------------


def hours_from_now(h: float) -> datetime:
    return utcnow() + timedelta(hours=h)


def days_from_now(d: float) -> datetime:
    return utcnow() + timedelta(days=d)


def utcnow() -> datetime:
    from app.utils.datetime import utcnow as _utcnow

    return _utcnow()


def make_task(db: Session, user_id: int, **overrides):
    from app.models.task import Task

    defaults = {
        "title": "Task",
        "area": "STARTUP",
        "priority": "MEDIUM",
        "status": "TODO",
    }
    defaults.update(overrides)
    task = Task(user_id=user_id, **defaults)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def make_goal(db: Session, user_id: int, **overrides):
    from app.models.goal import Goal

    defaults = {"name": "Goal", "area": "STARTUP", "status": "ACTIVE"}
    defaults.update(overrides)
    goal = Goal(user_id=user_id, **defaults)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal
