"""IRIS -- Intelligent Responsive Information System. FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    # Ensure the default single-user account exists (v1 auth stub).
    from app.core.database import SessionLocal
    from app.core.security import get_current_user

    db = SessionLocal()
    try:
        get_current_user(db)
    finally:
        db.close()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="IRIS API",
        description=(
            "**IRIS — Intelligent Responsive Information System** · "
            "*Your personal command center.*\n\n"
            "Backend for managing college, internship, startup, and personal life: "
            "tasks, goals, scheduling, focus, CRM, analytics, and Gemini-powered "
            "recommendations built on deterministic priority engines."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    cors_origins = list(settings.cors_origins)
    if settings.is_development:
        for dev_origin in ["http://localhost:5173", "http://127.0.0.1:5173"]:
            if dev_origin not in cors_origins:
                cors_origins.append(dev_origin)

    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)

    from app.api.routes import (
        ai,
        analytics,
        chat,
        focus,
        goals,
        health,
        intelligence,
        projects,
        reviews,
        schedule,
        startup,
        tasks,
        users,
    )

    api = settings.api_prefix
    app.include_router(health.router)  # /health stays at root
    app.include_router(users.router, prefix=api)
    app.include_router(tasks.router, prefix=api)
    app.include_router(goals.router, prefix=api)
    app.include_router(projects.router, prefix=api)
    app.include_router(schedule.router, prefix=api)
    app.include_router(focus.router, prefix=api)
    app.include_router(reviews.router, prefix=api)
    app.include_router(startup.router, prefix=api)
    app.include_router(analytics.router, prefix=api)
    app.include_router(ai.router, prefix=api)
    app.include_router(intelligence.router, prefix=api)
    app.include_router(chat.router, prefix=api)

    return app


app = create_app()
