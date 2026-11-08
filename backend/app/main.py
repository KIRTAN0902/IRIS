"""IRIS -- Intelligent Responsive Information System. FastAPI application."""

from __future__ import annotations

import logging
import re
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import request_id_context, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    from app.core.execution_provider import is_serverless_runtime

    # Function instances can be created and retired for individual requests.
    # Do not run recovery writes or start process-local managers/loops here.
    if is_serverless_runtime():
        yield
        return

    # Ensure the default single-user account exists (v1 auth stub).
    from app.core.database import SessionLocal
    from app.core.security import get_current_user

    try:
        db = SessionLocal()
        try:
            get_current_user(db)
            from app.coworkers.execution import recover_interrupted_tasks
            recover_interrupted_tasks(db)
        finally:
            db.close()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "startup_database_initialization_failed error_type=%s", type(exc).__name__
        )

    # Start sovereign laptop relay daemon if on local host (not serverless)
    import asyncio

    from app.coding.headless import headless_manager
    from app.coding.persistence import persist_headless_loop, persist_headless_sessions
    from app.services.agy_bridge import agy_manager
    from app.services.mesh_relay_service import relay_daemon

    agy_manager.start(asyncio.get_running_loop())
    session_persistence_task = asyncio.create_task(persist_headless_loop())
    await relay_daemon.start()

    # Durable knowledge jobs run off the request path and survive restarts via
    # leased database rows. Serverless deployments never start this loop and
    # instead drain a bounded batch through POST /api/knowledge/jobs/drain.
    knowledge_stop = asyncio.Event()
    knowledge_task = None
    if settings.knowledge_worker_enabled:
        from app.core.database import SessionLocal
        from app.knowledge.jobs import recover_stale_jobs, worker_loop

        try:
            db = SessionLocal()
            try:
                recover_stale_jobs(db)
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001 - migration may be pending
            logging.getLogger(__name__).warning(
                "knowledge_job_recovery_skipped error_type=%s", type(exc).__name__
            )
        knowledge_task = asyncio.create_task(worker_loop(knowledge_stop))

    yield

    if knowledge_task is not None:
        knowledge_stop.set()
        knowledge_task.cancel()
        await asyncio.gather(knowledge_task, return_exceptions=True)
    session_persistence_task.cancel()
    await asyncio.gather(session_persistence_task, return_exceptions=True)
    await asyncio.to_thread(persist_headless_sessions)
    await agy_manager.shutdown()
    headless_manager.shutdown()
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
    # Capacitor's bundled Android WebView uses https://localhost as its origin.
    # Allow only the app-local origins needed to call the configured API host.
    for app_origin in ["https://localhost", "capacitor://localhost"]:
        if app_origin not in cors_origins:
            cors_origins.append(app_origin)
    if settings.is_development:
        for dev_origin in ["http://localhost:5173", "http://127.0.0.1:5173"]:
            if dev_origin not in cors_origins:
                cors_origins.append(dev_origin)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
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

    @app.middleware("http")
    async def request_diagnostics(request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if re.fullmatch(r"[A-Za-z0-9._-]{1,80}", supplied) else uuid4().hex
        request.state.correlation_id = request_id
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logging.getLogger("iris.http").info(
                "request_complete method=%s path=%s status=%s duration_ms=%.1f",
                request.method,
                request.url.path,
                response.status_code,
                (time.perf_counter() - started) * 1000,
            )
            return response
        finally:
            request_id_context.reset(token)

    from app.api.routes import (
        agy,
        ai,
        analytics,
        assistant,
        chat,
        coding,
        coding_execution,
        computer,
        coworkers,
        diary,
        drive,
        email,
        finance,
        focus,
        goals,
        habits,
        health,
        intelligence,
        mesh,
        projects,
        remote_workspaces,
        reviews,
        schedule,
        startup,
        tasks,
        ui_orchestrator,
        users,
        vision,
        voice,
        workouts,
        knowledge,
    )

    api = settings.api_prefix
    app.include_router(health.router)  # /health at root (Vercel/health-check probes)
    app.include_router(health.router, prefix=api)  # /api/health for frontend api.get("/health")
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
    app.include_router(knowledge.router, prefix=api)
    app.include_router(intelligence.router, prefix=api)
    app.include_router(chat.router, prefix=api)
    app.include_router(assistant.router, prefix=api)
    app.include_router(voice.router, prefix=api)
    app.include_router(email.router, prefix=api)
    app.include_router(drive.router, prefix=api)
    app.include_router(coding.router, prefix=api)
    app.include_router(coding_execution.router, prefix=api)
    app.include_router(coding_execution.task_router, prefix=api)
    app.include_router(coworkers.router, prefix=api)
    app.include_router(remote_workspaces.router, prefix=api)
    app.include_router(ui_orchestrator.router, prefix=api)
    app.include_router(mesh.router, prefix=api)
    app.include_router(agy.router, prefix=api)
    app.include_router(vision.router, prefix=api)
    app.include_router(finance.router, prefix=api)
    app.include_router(habits.router, prefix=api)
    app.include_router(workouts.router, prefix=api)
    app.include_router(diary.router, prefix=api)
    app.include_router(computer.router, prefix=api)

    from fastapi.responses import HTMLResponse

    @app.get("/companion", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/mesh/companion", response_class=HTMLResponse, include_in_schema=False)
    def root_companion():
        return mesh.get_companion_page()

    return app


app = create_app()
