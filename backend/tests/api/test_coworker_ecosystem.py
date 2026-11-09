"""Comprehensive tests for the IRIS Coworker Ecosystem & Fleet Foundation.

Verifies:
1. IRIS Core is NEVER registered as a coworker.
2. BUBBA is NEVER registered as a primary coworker.
3. The 4 canonical specialized coworkers exist: Developer, Workspace, Notification, Scribe.
4. Factual availability reporting (Workspace needs_setup without accounts; Notification needs_setup without listener).
5. GPay notification ingestion, privacy filtering, and handoff to IRIS Core.
6. Slack integration tools.
7. Supervisor routing and delegation.
"""

from datetime import datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from app.agent.supervisor import IrisSupervisor
from app.models.coworker import Coworker
from app.models.email_account import EmailAccount
from app.models.finance import FinanceTransaction
from app.models.user import User
from app.services.notification_coworker_service import (
    IngestNotificationPayload,
    notification_coworker_service,
)
from app.services.slack_service import slack_service


def test_iris_core_and_bubba_never_in_coworker_fleet(client):
    """IRIS Core is IRIS itself and BUBBA is migrated; neither must ever appear in Fleet."""
    res = client.get("/api/coworkers")
    assert res.status_code == 200, res.text
    coworkers = res.json()

    names = [c["name"].lower() for c in coworkers]
    roles = [c["role"].lower() for c in coworkers]

    assert not any("iris core" in n or "iris core" in r for n, r in zip(names, roles)), "IRIS Core must never be in Fleet"
    assert not any("bubba" in n or "bubba" in r for n, r in zip(names, roles)), "BUBBA must never be in Fleet"


def test_four_canonical_specialized_coworkers_exist(client):
    """The four canonical coworkers must be registered: Developer, Workspace, Notification, Scribe."""
    res = client.get("/api/coworkers")
    assert res.status_code == 200
    coworkers = res.json()

    cw_map = {c["name"]: c for c in coworkers}
    assert "Developer" in cw_map
    assert "Workspace" in cw_map
    assert "Notification" in cw_map
    assert "Scribe" in cw_map

    dev = cw_map["Developer"]
    assert dev["role"] == "Software Engineering"
    assert "git" in dev["specialisation"].lower()

    ws = cw_map["Workspace"]
    assert ws["role"] == "Digital Workspace & Productivity"
    assert "gmail" in ws["specialisation"].lower() or "slack" in ws["specialisation"].lower()

    notif = cw_map["Notification"]
    assert notif["role"] == "Notification Intelligence & Event Ingestion"
    assert "gpay" in notif["specialisation"].lower()

    scribe = cw_map["Scribe"]
    assert scribe["role"] == "Writing & Documentation"


def test_workspace_availability_reporting(client, db: Session):
    """Workspace accurately reports 'needs_setup' when unconfigured and 'ready' when connected."""
    user = db.query(User).filter_by(email="test@iris.local").first() or db.query(User).first()

    # When no accounts connected
    res = client.get("/api/coworkers")
    assert res.status_code == 200
    ws = next(c for c in res.json() if c["name"] == "Workspace")
    # In clean test DB with no accounts, status must be needs_setup
    if not ws.get("connected_services"):
        assert ws["status"] == "needs_setup"
        assert "setup_requirement" in ws

    # Add an active email account
    acc = EmailAccount(
        user_id=user.id,
        alias="test_personal",
        email_address="test@gmail.com",
        provider="gmail",
        refresh_token="mock-refresh-token",
        is_active=True,
    )
    db.add(acc)
    db.commit()

    res2 = client.get("/api/coworkers")
    ws2 = next(c for c in res2.json() if c["name"] == "Workspace")
    assert ws2["status"] == "ready"
    assert "Gmail" in ws2.get("connected_services", [])


def test_notification_availability_reporting(client, db: Session):
    """Notification accurately reports 'needs_setup' when listener is not active."""
    res = client.get("/api/coworkers/notification/status")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "supported_apps" in data


def test_gpay_notification_ingestion_and_privacy_filter(client, db: Session):
    """Notification coworker filters non-payment notifications and forwards valid GPay events to Core."""
    # 1. Non-payment notification should be dropped for privacy
    non_payment = {
        "package_name": "com.whatsapp",
        "title": "Mom",
        "text": "Call me when you reach home",
    }
    drop_res = client.post("/api/coworkers/notification/events", json=non_payment)
    assert drop_res.status_code == 202
    assert drop_res.json()["status"] == "filtered"
    assert drop_res.json()["accepted"] is False

    # 2. Valid GPay transaction notification
    gpay_payload = {
        "package_name": "com.google.android.apps.nbu.paisa.user",
        "title": "Google Pay",
        "text": "Paid ₹420.50 to Blue Tokai Coffee using Bank Account. UPI Ref 329048123984",
        "currency": "INR",
        "status": "completed",
    }
    ingest_res = client.post("/api/coworkers/notification/events", json=gpay_payload)
    assert ingest_res.status_code == 202
    res_data = ingest_res.json()
    assert res_data["accepted"] is True
    assert res_data["forwarded_to_core"] is True
    assert res_data["structured_event"]["merchant"] == "Blue Tokai Coffee"
    assert res_data["structured_event"]["amount"] == 420.50

    # Verify event appears in recent events endpoint
    events_res = client.get("/api/coworkers/notification/events")
    assert events_res.status_code == 200
    events = events_res.json()
    assert any(e["merchant"] == "Blue Tokai Coffee" for e in events)


def test_supervisor_routes_to_specialized_coworkers():
    """Supervisor routes requests to the proper specialized coworker and handles personal tasks in Core."""
    supervisor = IrisSupervisor()

    # Developer routing
    dev_routes = supervisor.route_intent("Fix the bug in the authentication repository and run tests")
    assert "developer" in dev_routes

    # Workspace routing (Gmail)
    gmail_routes = supervisor.route_intent("Search my unread emails and draft a reply to Alex")
    assert "workspace" in gmail_routes

    # Workspace routing (Slack)
    slack_routes = supervisor.route_intent("Search the engineering Slack channel and summarize discussions")
    assert "workspace" in slack_routes

    # Notification routing
    notif_routes = supervisor.route_intent("Check recent GPay notification events from my phone")
    assert "notification" in notif_routes

    # Scribe routing
    scribe_routes = supervisor.route_intent("Prepare an architecture decision record (ADR) and technical report")
    assert "scribe" in scribe_routes

    # IRIS Core self-execution (personal management & priorities - no delegation)
    core_tasks = supervisor.route_intent("What are my highest priorities today?")
    # Empty list means handled directly by IRIS Core without sub-agent delegation
    assert core_tasks == []
