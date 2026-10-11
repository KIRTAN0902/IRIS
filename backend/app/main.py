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

    # Start sovereign laptop relay daemon if on local host (not serverless)
    import os
    from app.services.mesh_relay_service import relay_daemon
    if not os.environ.get("VERCEL") and not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        await relay_daemon.start()

    yield

    if not os.environ.get("VERCEL") and not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        await relay_daemon.stop()


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
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_origin_regex=r"^https?://.*",
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    elif cors_origins:
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
        assistant,
        chat,
        coding,
        email,
        finance,
        habits,
        focus,
        goals,
        health,
        intelligence,
        mesh,
        projects,
        reviews,
        schedule,
        startup,
        tasks,
        users,
        voice,
        workouts,
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
    app.include_router(assistant.router, prefix=api)
    app.include_router(voice.router, prefix=api)
    app.include_router(email.router, prefix=api)
    app.include_router(coding.router, prefix=api)
    app.include_router(mesh.router, prefix=api)
    app.include_router(finance.router, prefix=api)
    app.include_router(habits.router, prefix=api)
    app.include_router(workouts.router, prefix=api)

    from fastapi.responses import HTMLResponse

    @app.get("/companion", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/mesh/companion", response_class=HTMLResponse, include_in_schema=False)
    def root_companion():
        return mesh.get_companion_page()

    return app


app = create_app()
