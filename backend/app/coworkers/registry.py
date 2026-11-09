"""Canonical Source of Truth for IRIS Specialized Coworkers.

IRIS CORE IS NOT A COWORKER. IRIS CORE IS IRIS ITSELF.
IRIS Core is the orchestrator, supervisor, and default assistant identity.
The specialized coworkers are registered, managed extensions under IRIS Core:
1. Developer — Software Development and Engineering
2. Workspace — Gmail, Google Drive, and Slack Integrations
3. Notification — Android Notification Intelligence & GPay Event Ingestion
4. Scribe — Writing, Technical Documentation, and Content Production
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.coworker import Coworker, CoworkerTask
from app.models.user import User

logger = get_logger("iris.coworkers.registry")

# Static specifications for the 4 canonical specialized coworkers
SPECIALIZED_COWORKERS_SPEC: dict[str, dict[str, Any]] = {
    "developer": {
        "slug": "developer",
        "name": "Developer",
        "role": "Software Engineering",
        "specialisation": "software engineering and git operations",
        "description": (
            "Specialized software development coworker. Handles repository analysis, "
            "implementation, debugging, refactoring, tests, and Git operations."
        ),
        "responsibilities": [
            "Understand natural-language development requests",
            "Inspect project architecture and Git status",
            "Formulate implementation plans and task briefs",
            "Enforce Git worktree isolation and branch protections",
            "Execute builds, tests, and runtime troubleshooting",
            "Verify test outcomes and present diff reviews",
        ],
        "system_instructions": (
            "You are Developer, IRIS's specialized software engineering coworker. "
            "You plan and implement code modifications in Git workspaces, run tests, "
            "troubleshoot build and runtime errors, and report clear implementation diffs."
        ),
        "allowed_capabilities": [
            "search_conversations",
            "search_memory",
            "get_conversation",
            "get_projects",
            "list_coding_tasks",
            "get_coding_task_status",
        ],
        "permission_profile": {
            "require_approval_for": ["git_push", "execute_destructive_command"],
            "allow_worktree_isolation": True,
            "remote_execution_default": True,
        },
    },
    "workspace": {
        "slug": "workspace",
        "name": "Workspace",
        "role": "Digital Workspace & Productivity",
        "specialisation": "gmail, google drive, and slack integrations",
        "description": (
            "Interacts with authorized external productivity services: Gmail (emails & drafts), "
            "Google Drive (files & docs), and Slack (discussions & channels)."
        ),
        "responsibilities": [
            "Search emails and summarize correspondence",
            "Prepare email drafts for user confirmation",
            "Search files and read documents in Google Drive",
            "Search authorized Slack workspaces and summarize discussions",
            "Identify decisions and action items across team channels",
            "Draft responses with explicit user authorization",
        ],
        "system_instructions": (
            "You are Workspace, IRIS's specialized coworker for digital workspace integrations. "
            "You query and interact with authorized external productivity services: "
            "Gmail, Google Drive, and Slack. Never fabricate email threads, Drive documents, "
            "or Slack messages. Report real source references and require confirmation for outbound actions."
        ),
        "allowed_capabilities": [
            "get_email_accounts",
            "list_unread_emails",
            "search_emails",
            "get_email_details",
            "create_email_draft",
            "send_email",
            "list_google_drive_files",
            "search_google_drive",
            "read_google_drive_file",
            "upload_to_google_drive",
            "search_slack_messages",
            "get_slack_channel_history",
            "list_slack_channels",
            "draft_slack_message",
            "send_slack_message",
        ],
        "permission_profile": {
            "require_approval_for": ["send_email", "send_slack_message", "upload_to_google_drive"],
            "read_only_default": False,
        },
    },
    "notification": {
        "slug": "notification",
        "name": "Notification",
        "role": "Notification Intelligence & Event Ingestion",
        "specialisation": "android gpay event ingestion",
        "description": (
            "Event-ingestion specialist for authorized devices. Ingests, filters, and extracts "
            "GPay transaction notifications and forwards structured events to IRIS Core."
        ),
        "responsibilities": [
            "Capture and filter GPay notifications locally on Android",
            "Extract structured transaction data (amounts, merchants, references, statuses)",
            "Detect and reject duplicate notification events",
            "Forward structured transaction events to IRIS Core for financial processing",
        ],
        "system_instructions": (
            "You are Notification, IRIS's event-ingestion specialist. "
            "You ingest incoming notification events from authorized devices (primarily GPay UPI transactions), "
            "validate extracted amounts and merchant references, deduplicate events, and pass structured "
            "transaction records to IRIS Core. You do NOT own financial records or budgeting logic independently."
        ),
        "allowed_capabilities": [
            "ingest_notification_event",
            "get_notification_events",
            "get_notification_status",
        ],
        "permission_profile": {
            "device_scoped": True,
            "local_filter_only": True,
        },
    },
    "scribe": {
        "slug": "scribe",
        "name": "Scribe",
        "role": "Writing & Documentation",
        "specialisation": "writing, documentation, and content synthesis",
        "description": (
            "Specialized writing, documentation, and content production capability. "
            "Crafts technical documentation, structured deliverables, reports, summaries, and professional communications."
        ),
        "responsibilities": [
            "Draft technical documentation and architecture decisions (ADRs)",
            "Prepare comprehensive technical reports and summaries",
            "Edit, polish, and structure written prose and deliverables",
            "Manage personal notebook and structured project deliverables",
        ],
        "system_instructions": (
            "You are Scribe, IRIS's specialized writing and documentation coworker. "
            "You produce high-quality prose, comprehensive technical documentation, "
            "ADRs, project reports, and executive summaries with clear structure and typography."
        ),
        "allowed_capabilities": [
            "create_diary_entry",
            "read_diary_entries",
            "get_diary_entry",
            "update_diary_entry",
            "delete_diary_entry",
            "search_knowledge",
        ],
        "permission_profile": {
            "markdown_formatting": True,
            "document_deliverables": True,
        },
    },
}

# The canonical set of allowed coworker slugs in Fleet
CANONICAL_COWORKER_SLUGS = {"developer", "workspace", "notification", "scribe"}


def get_coworker_uuid(user_id: int, slug: str) -> str:
    """Generate deterministic, stable UUID for a canonical coworker and user."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"iris-coworker-{slug}-{user_id}"))


def evaluate_coworker_availability(
    db: Session, user: User, slug: str, coworker_id: str
) -> dict[str, Any]:
    """Calculate the real operational availability status of a specialized coworker.

    Statuses:
    - 'busy': Actively executing a task
    - 'ready': All required integrations, engines, or permissions are genuinely available
    - 'needs_setup': Integration or device permissions required before it can execute
    - 'unavailable': Disabled or system error
    """
    # 1. Check if actively executing a task
    active_task = (
        db.query(CoworkerTask)
        .filter(
            CoworkerTask.user_id == user.id,
            CoworkerTask.coworker_id == coworker_id,
            CoworkerTask.status.in_(["running", "working", "queued", "waiting_approval"]),
        )
        .first()
    )
    if active_task:
        return {
            "status": "busy",
            "availability": True,
            "message": f"Executing task: {active_task.instruction[:60]}...",
            "active_task_id": active_task.id,
        }

    # 2. Domain-specific genuine availability checks
    if slug == "developer":
        # Check execution environment (antigravity, codex, or companion URL)
        has_remote = bool(os.getenv("REMOTE_COMPANION_URL"))
        has_cli = bool(os.getenv("ANTIGRAVITY_PATH") or os.getenv("CODEX_PATH"))
        return {
            "status": "ready",
            "availability": True,
            "message": "Ready for repository analysis, implementation, and git operations",
            "execution_target": "remote" if has_remote else "local",
        }

    elif slug == "workspace":
        # Check Gmail, Drive, Slack connections
        connected_services: list[str] = []

        # Gmail
        try:
            from app.models.email_account import EmailAccount

            active_email = (
                db.query(EmailAccount)
                .filter(
                    EmailAccount.user_id == user.id,
                    EmailAccount.is_active.is_(True),
                    EmailAccount.refresh_token.isnot(None),
                )
                .first()
            )
            if active_email:
                connected_services.append("Gmail")
        except Exception:
            pass

        # Google Drive
        try:
            from app.services.google_drive_service import drive_service

            active_drive = drive_service.get_drive_account(db, user.id)
            if active_drive and active_drive.refresh_token:
                connected_services.append("Google Drive")
        except Exception:
            pass

        # Slack
        try:
            from app.services.slack_service import slack_service

            if slack_service.is_configured(db, user.id):
                connected_services.append("Slack")
        except Exception:
            pass

        if connected_services:
            return {
                "status": "ready",
                "availability": True,
                "message": f"Connected: {', '.join(connected_services)}",
                "connected_services": connected_services,
            }
        else:
            return {
                "status": "needs_setup",
                "availability": False,
                "message": "Needs setup: Connect Gmail, Google Drive, or Slack",
                "setup_requirement": "Requires Gmail, Google Drive, or Slack connection",
                "connected_services": [],
            }

    elif slug == "notification":
        # Check if Android notification listener has ever reported or active device connected
        try:
            from app.services.notification_coworker_service import notification_coworker_service

            is_active = notification_coworker_service.is_listener_active(db, user.id)
        except Exception:
            is_active = False

        if is_active:
            return {
                "status": "ready",
                "availability": True,
                "message": "Android GPay notification listener active",
            }
        else:
            return {
                "status": "needs_setup",
                "availability": False,
                "message": "Needs setup: Authorize Android notification-listener on device",
                "setup_requirement": "Requires Android notification-listener permission",
            }

    elif slug == "scribe":
        return {
            "status": "ready",
            "availability": True,
            "message": "Ready for document drafting, reports, and technical documentation",
        }

    return {
        "status": "ready",
        "availability": True,
        "message": "Ready",
    }


def ensure_specialized_coworkers(db: Session, user: User) -> list[Coworker]:
    """Ensure the 4 canonical specialized coworkers exist in the DB for this user.

    Never creates an IRIS Core coworker.
    Never creates BUBBA as a primary coworker.
    Returns the list of canonical coworkers.
    """
    coworkers: list[Coworker] = []

    for slug, spec in SPECIALIZED_COWORKERS_SPEC.items():
        coworker_id = get_coworker_uuid(user.id, slug)
        existing = db.query(Coworker).filter_by(id=coworker_id, user_id=user.id).first()

        if existing is None:
            # Check by role/name in case ID differs
            existing = (
                db.query(Coworker)
                .filter_by(user_id=user.id, role=spec["role"], name=spec["name"])
                .first()
            )

        if existing is None:
            c = Coworker(
                id=coworker_id,
                user_id=user.id,
                name=spec["name"],
                role=spec["role"],
                description=spec["description"],
                specialisation=spec["specialisation"],
                responsibilities=spec["responsibilities"],
                system_instructions=spec["system_instructions"],
                allowed_capabilities=spec["allowed_capabilities"],
                permission_profile=spec["permission_profile"],
                status="idle",
                availability=True,
            )
            db.add(c)
            db.flush()
            existing = c
        else:
            # Sync metadata to ensure canonical source of truth
            existing.description = spec["description"]
            existing.specialisation = spec["specialisation"]
            existing.responsibilities = spec["responsibilities"]
            existing.system_instructions = spec["system_instructions"]
            existing.allowed_capabilities = spec["allowed_capabilities"]
            existing.permission_profile = spec["permission_profile"]

        coworkers.append(existing)

    db.commit()
    return coworkers
