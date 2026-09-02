"""Startup service -- startups, leads, outreach, experiments.

Outreach logging can auto-advance lead status so pipeline metrics are always
consistent with activity records.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.enums import (
    ExperimentStatus,
    LeadStatus,
    OutreachResult,
    StartupStatus,
)
from app.models.experiment import Experiment
from app.models.lead import Lead
from app.models.outreach import OutreachActivity
from app.models.startup import Startup
from app.utils.datetime import utcnow

# Result -> the lead status it implies (only forward movement).
RESULT_TO_LEAD_STATUS: dict[str, LeadStatus] = {
    OutreachResult.SENT: LeadStatus.CONTACTED,
    OutreachResult.REPLIED: LeadStatus.REPLIED,
    OutreachResult.MEETING_BOOKED: LeadStatus.MEETING,
    OutreachResult.CONVERTED: LeadStatus.CUSTOMER,
}

LEAD_RANK = {status.value: i for i, status in enumerate(LeadStatus)}


# --- Startups ------------------------------------------------------------------


def get_startup(db: Session, user_id: int, startup_id: int | None = None) -> Startup:
    q = db.query(Startup).filter(Startup.user_id == user_id)
    startup = q.filter(Startup.id == startup_id).first() if startup_id else q.first()
    if not startup:
        raise NotFoundError("Startup not found.", code="STARTUP_NOT_FOUND")
    return startup


def list_startups(db: Session, user_id: int) -> list[Startup]:
    return db.query(Startup).filter(Startup.user_id == user_id).all()


def create_startup(db: Session, user_id: int, data: dict) -> Startup:
    startup = Startup(user_id=user_id, **data)
    db.add(startup)
    db.commit()
    db.refresh(startup)
    return startup


def update_startup(db: Session, user_id: int, startup_id: int, data: dict) -> Startup:
    startup = get_startup(db, user_id, startup_id)
    for key, value in data.items():
        setattr(startup, key, value)
    db.commit()
    db.refresh(startup)
    return startup


# --- Leads ----------------------------------------------------------------------


def list_leads(
    db: Session,
    user_id: int,
    *,
    startup_id: int | None = None,
    status: str | None = None,
    follow_up_due: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Lead], int]:
    q = (
        db.query(Lead)
        .join(Startup, Lead.startup_id == Startup.id)
        .filter(Startup.user_id == user_id)
    )
    if startup_id:
        q = q.filter(Lead.startup_id == startup_id)
    if status:
        q = q.filter(Lead.status == status)
    if follow_up_due:
        from app.utils.datetime import utcnow

        q = q.filter(
            Lead.next_follow_up.is_not(None),
            Lead.next_follow_up <= utcnow(),
            Lead.status.notin_([LeadStatus.CUSTOMER.value, LeadStatus.LOST.value]),
        )
    total = q.count()
    return (
        q.order_by(Lead.updated_at.desc()).offset(offset).limit(limit).all(),
        total,
    )


def create_lead(db: Session, user_id: int, data: dict) -> Lead:
    get_startup(db, user_id, data["startup_id"])  # ownership check
    lead = Lead(**data)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def get_lead(db: Session, user_id: int, lead_id: int) -> Lead:
    lead = (
        db.query(Lead)
        .join(Startup, Lead.startup_id == Startup.id)
        .filter(Lead.id == lead_id, Startup.user_id == user_id)
        .first()
    )
    if not lead:
        raise NotFoundError("Lead not found.", code="LEAD_NOT_FOUND")
    return lead


def update_lead(db: Session, user_id: int, lead_id: int, data: dict) -> Lead:
    lead = get_lead(db, user_id, lead_id)
    for key, value in data.items():
        setattr(lead, key, value)
    db.commit()
    db.refresh(lead)
    return lead


def delete_lead(db: Session, user_id: int, lead_id: int) -> None:
    lead = get_lead(db, user_id, lead_id)
    db.delete(lead)
    db.commit()


# --- Outreach ---------------------------------------------------------------


def log_outreach(
    db: Session, user_id: int, data: dict, *, update_lead_status: bool = True
) -> OutreachActivity:
    lead = get_lead(db, user_id, data["lead_id"])
    if data.get("startup_id") != lead.startup_id:
        raise NotFoundError("Lead does not belong to that startup.", code="LEAD_STARTUP_MISMATCH")

    # `update_lead_status` is a service directive, not a column.
    data.pop("update_lead_status", None)
    activity = OutreachActivity(**data)
    if activity.timestamp is None:
        activity.timestamp = utcnow()
    db.add(activity)

    if update_lead_status:
        new_status = RESULT_TO_LEAD_STATUS.get(activity.result or "")
        if new_status and LEAD_RANK[new_status.value] > LEAD_RANK.get(lead.status, -1):
            lead.status = new_status.value
        lead.last_contacted = activity.timestamp

    db.commit()
    db.refresh(activity)
    return activity


def update_outreach(db: Session, user_id: int, activity_id: int, data: dict) -> OutreachActivity:
    activity = (
        db.query(OutreachActivity)
        .join(Startup, OutreachActivity.startup_id == Startup.id)
        .filter(OutreachActivity.id == activity_id, Startup.user_id == user_id)
        .first()
    )
    if not activity:
        raise NotFoundError("Outreach activity not found.", code="OUTREACH_NOT_FOUND")
    for key, value in data.items():
        setattr(activity, key, value)
    db.commit()
    db.refresh(activity)
    return activity


# --- Experiments ------------------------------------------------------------


def list_experiments(
    db: Session,
    user_id: int,
    *,
    startup_id: int | None = None,
    status: str | None = None,
) -> list[Experiment]:
    q = (
        db.query(Experiment)
        .join(Startup, Experiment.startup_id == Startup.id)
        .filter(Startup.user_id == user_id)
    )
    if startup_id:
        q = q.filter(Experiment.startup_id == startup_id)
    if status:
        q = q.filter(Experiment.status == status)
    return q.order_by(Experiment.started_at.desc().nulls_last()).all()


def get_experiment(db: Session, user_id: int, experiment_id: int) -> Experiment:
    experiment = (
        db.query(Experiment)
        .join(Startup, Experiment.startup_id == Startup.id)
        .filter(Experiment.id == experiment_id, Startup.user_id == user_id)
        .first()
    )
    if not experiment:
        raise NotFoundError("Experiment not found.", code="EXPERIMENT_NOT_FOUND")
    return experiment


def create_experiment(db: Session, user_id: int, data: dict) -> Experiment:
    get_startup(db, user_id, data["startup_id"])
    if data.get("status") == ExperimentStatus.RUNNING.value and not data.get("started_at"):
        from app.utils.datetime import utcnow as _utcnow

        data["started_at"] = _utcnow()
    experiment = Experiment(**data)
    db.add(experiment)
    db.commit()
    db.refresh(experiment)
    return experiment


def update_experiment(db: Session, user_id: int, experiment_id: int, data: dict) -> Experiment:
    experiment = get_experiment(db, user_id, experiment_id)
    if data.get("status") == ExperimentStatus.COMPLETED.value and not data.get("ended_at"):
        from app.utils.datetime import utcnow as _utcnow

        data["ended_at"] = _utcnow()
    for key, value in data.items():
        setattr(experiment, key, value)
    db.commit()
    db.refresh(experiment)
    return experiment


def active_startup_status_values() -> list[str]:
    return [s.value for s in StartupStatus]
