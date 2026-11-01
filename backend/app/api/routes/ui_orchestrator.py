"""Shared UI definitions, preferences, layouts, proposals and recovery."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.intelligence.situation import build_situation
from app.models.coworker import CoworkerTask
from app.models.ui_workspace import UIChangeProposal, UIWorkspaceConfig
from app.models.user import User

router = APIRouter(prefix="/ui-orchestrator", tags=["UI Orchestrator"])

WIDGETS = [
    {
        "id": "priorities",
        "title": "Priorities",
        "description": "Tasks that need attention today.",
        "data": ["situation.tasks", "attention"],
        "platforms": ["desktop", "android"],
        "sizes": ["compact", "standard", "wide"],
    },
    {
        "id": "schedule",
        "title": "Schedule",
        "description": "What is happening now and next.",
        "data": ["situation.schedule"],
        "platforms": ["desktop", "android"],
        "sizes": ["compact", "standard", "wide"],
    },
    {
        "id": "routines",
        "title": "Routines",
        "description": "Today's routines and completion state.",
        "data": ["habits"],
        "platforms": ["desktop", "android"],
        "sizes": ["compact", "standard", "wide"],
    },
    {
        "id": "coworkers",
        "title": "Coworkers",
        "description": "Active coworker tasks and approvals.",
        "data": ["coworkers"],
        "platforms": ["desktop", "android"],
        "sizes": ["compact", "standard", "wide"],
    },
    {
        "id": "progress",
        "title": "Day progress",
        "description": "Progress across planned tasks and routines.",
        "data": ["situation", "habits"],
        "platforms": ["desktop", "android"],
        "sizes": ["compact", "standard"],
    },
]
WIDGET_IDS = {w["id"] for w in WIDGETS}
DEFAULT_LAYOUT = {
    "desktop": [
        {
            "id": "progress",
            "visible": True,
            "size": "standard",
            "locked": False,
            "config": {},
            "lifecycle": "persistent",
            "expires_at": None,
        },
        {
            "id": "priorities",
            "visible": True,
            "size": "standard",
            "locked": False,
            "config": {},
            "lifecycle": "persistent",
            "expires_at": None,
        },
        {
            "id": "schedule",
            "visible": True,
            "size": "standard",
            "locked": False,
            "config": {},
            "lifecycle": "persistent",
            "expires_at": None,
        },
        {
            "id": "routines",
            "visible": True,
            "size": "standard",
            "locked": False,
            "config": {},
            "lifecycle": "persistent",
            "expires_at": None,
        },
        {
            "id": "coworkers",
            "visible": True,
            "size": "compact",
            "locked": False,
            "config": {},
            "lifecycle": "persistent",
            "expires_at": None,
        },
    ],
    "android": [
        {
            "id": "priorities",
            "visible": True,
            "size": "standard",
            "locked": False,
            "config": {},
            "lifecycle": "persistent",
            "expires_at": None,
        },
        {
            "id": "schedule",
            "visible": True,
            "size": "standard",
            "locked": False,
            "config": {},
            "lifecycle": "persistent",
            "expires_at": None,
        },
        {
            "id": "routines",
            "visible": True,
            "size": "standard",
            "locked": False,
            "config": {},
            "lifecycle": "persistent",
            "expires_at": None,
        },
        {
            "id": "progress",
            "visible": True,
            "size": "compact",
            "locked": False,
            "config": {},
            "lifecycle": "persistent",
            "expires_at": None,
        },
        {
            "id": "coworkers",
            "visible": True,
            "size": "compact",
            "locked": False,
            "config": {},
            "lifecycle": "persistent",
            "expires_at": None,
        },
    ],
}


class LayoutWidget(BaseModel):
    id: str
    visible: bool = True
    size: str = "standard"
    locked: bool = False
    config: dict = Field(default_factory=dict)
    lifecycle: str = "persistent"
    expires_at: datetime | None = None


class LayoutUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    widgets: list[LayoutWidget] = Field(max_length=20)


class PreferencesUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    density: str | None = None
    interaction_learning: bool | None = None
    week_start: str | None = None
    theme: str | None = None


class ProposalCreate(BaseModel):
    platform: str
    title: str = Field(min_length=1, max_length=160)
    reason: str = Field(default="", max_length=500)
    widgets: list[LayoutWidget] = Field(max_length=20)


class ProposalDecision(BaseModel):
    decision: str


def _get(db: Session, user_id: int, create: bool = True) -> UIWorkspaceConfig:
    row = db.get(UIWorkspaceConfig, user_id)
    if row is None and create:
        row = UIWorkspaceConfig(
            user_id=user_id,
            version=1,
            preferences={
                "density": "comfortable",
                "interaction_learning": False,
                "week_start": "monday",
                "theme": "light",
            },
            layouts=deepcopy(DEFAULT_LAYOUT),
            history=[],
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    if row is None:
        raise HTTPException(404, "UI configuration not found")
    return row


def _validate_layout(raw: list[LayoutWidget], current: list[dict] | None = None) -> list[dict]:
    values = [item.model_dump(mode="json") for item in raw]
    ids = [item["id"] for item in values]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "A widget can appear only once in a layout")
    for item in values:
        spec = next((w for w in WIDGETS if w["id"] == item["id"]), None)
        if spec is None:
            raise HTTPException(422, f"Unsupported widget: {item['id']}")
        if item["size"] not in spec["sizes"]:
            raise HTTPException(422, f"Unsupported size for widget: {item['id']}")
        if len(str(item["config"])) > 2000:
            raise HTTPException(422, "Widget configuration is too large")
        if item["lifecycle"] not in ("persistent", "temporary"):
            raise HTTPException(422, "Unsupported widget lifecycle")
        expiry = item["expires_at"]
        if item["lifecycle"] == "temporary":
            if isinstance(expiry, str):
                expiry = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            if expiry is None or expiry.tzinfo is None or expiry <= datetime.now(UTC):
                raise HTTPException(422, "Temporary widgets need a future timezone-aware expiry")
        elif expiry is not None:
            raise HTTPException(422, "Persistent widgets cannot have an expiry")
    if current:
        next_by_id = {item["id"]: item for item in values}
        new_positions = {item["id"]: index for index, item in enumerate(values)}
        for old_index, old in enumerate(current):
            if old.get("locked") and (
                old["id"] not in next_by_id
                or next_by_id[old["id"]] != old
                or new_positions.get(old["id"]) != old_index
            ):
                raise HTTPException(409, f"Widget '{old['id']}' is locked")
    return values


def _snapshot(row: UIWorkspaceConfig, kind: str) -> None:
    row.history = [
        *list(row.history or []),
        {
            "version": row.version,
            "kind": kind,
            "preferences": deepcopy(row.preferences),
            "layouts": deepcopy(row.layouts),
            "created_at": datetime.now(UTC).isoformat(),
        },
    ][-50:]
    row.version += 1


def _record_layout_choice(row: UIWorkspaceConfig, platform: str, layout: list[dict]) -> None:
    """Record only opted-in layout choices, separate from rollback history."""
    if not (row.preferences or {}).get("interaction_learning"):
        return
    preferences = dict(row.preferences or {})
    patterns = list(preferences.get("learned_layout_orders", []))
    patterns.append(
        {
            "platform": platform,
            "order": [item["id"] for item in layout if item.get("visible")],
            "at": datetime.now(UTC).isoformat(),
        }
    )
    preferences["learned_layout_orders"] = patterns[-50:]
    row.preferences = preferences


def _apply_learned_order(row: UIWorkspaceConfig, platform: str, proposed: list[dict]) -> list[dict]:
    if not (row.preferences or {}).get("interaction_learning"):
        return proposed
    patterns = [
        p
        for p in (row.preferences or {}).get("learned_layout_orders", [])
        if p.get("platform") == platform
    ]
    if not patterns:
        return proposed
    scores: dict[str, int] = {}
    for pattern in patterns[-20:]:
        for position, widget_id in enumerate(pattern.get("order", [])):
            scores[widget_id] = scores.get(widget_id, 0) + max(1, 10 - position)
    slots = [index for index, item in enumerate(proposed) if not item.get("locked")]
    unlocked = sorted(
        (proposed[index] for index in slots), key=lambda item: -scores.get(item["id"], 0)
    )
    result = list(proposed)
    for index, item in zip(slots, unlocked, strict=True):
        result[index] = item
    return result


@router.get("/state")
def get_state(user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = _get(db, user.id)
    proposals = (
        db.query(UIChangeProposal)
        .filter_by(user_id=user.id, status="pending")
        .order_by(UIChangeProposal.created_at.desc())
        .all()
    )
    return {
        "version": row.version,
        "preferences": row.preferences,
        "layouts": row.layouts,
        "history": row.history,
        "proposals": [_proposal_out(p) for p in proposals],
    }


@router.get("/catalog")
def get_catalog():
    return {
        "schema_version": 1,
        "widgets": WIDGETS,
        "platforms": ["desktop", "android"],
        "safety": "Only registered widgets and declarative configuration are supported.",
    }


@router.get("/context")
def get_context(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Return a small page context built from IRIS's current domain services."""
    situation = build_situation(db, user)
    active_coworkers = (
        db.query(CoworkerTask)
        .filter(
            CoworkerTask.user_id == user.id,
            CoworkerTask.status.in_(["queued", "running", "awaiting_approval", "waiting"]),
        )
        .count()
    )
    return {
        "page": "home",
        "local_time": situation.get("now", {}).get("local_time"),
        "attention_count": len(situation.get("tasks", {}).get("overdue", [])),
        "has_schedule": bool(situation.get("today_schedule")),
        "active_coworker_tasks": active_coworkers,
        "available_widgets": sorted(WIDGET_IDS),
    }


@router.put("/preferences")
def update_preferences(
    payload: PreferencesUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = _get(db, user.id)
    _check_version(row, payload.expected_version)
    values = payload.model_dump(exclude={"expected_version"}, exclude_none=True)
    if values.get("density") not in (None, "compact", "comfortable", "spacious"):
        raise HTTPException(422, "Unsupported density")
    if values.get("week_start") not in (None, "monday", "sunday", "saturday"):
        raise HTTPException(422, "Unsupported week start")
    if values.get("theme") not in (None, "light", "dark", "system"):
        raise HTTPException(422, "Unsupported theme")
    if values:
        _snapshot(row, "preferences")
        row.preferences = {**(row.preferences or {}), **values}
        db.commit()
    return {"version": row.version, "preferences": row.preferences}


@router.put("/layouts/{platform}")
def update_layout(
    platform: str,
    payload: LayoutUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if platform not in ("desktop", "android"):
        raise HTTPException(404, "Unknown platform")
    row = _get(db, user.id)
    _check_version(row, payload.expected_version)
    current = (row.layouts or {}).get(platform, [])
    new_layout = _validate_layout(payload.widgets, current)
    _snapshot(row, f"layout:{platform}")
    row.layouts = {**(row.layouts or {}), platform: new_layout}
    _record_layout_choice(row, platform, new_layout)
    db.commit()
    return {"version": row.version, "platform": platform, "widgets": new_layout}


@router.post("/proposals", status_code=201)
def create_proposal(
    payload: ProposalCreate, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if payload.platform not in ("desktop", "android"):
        raise HTTPException(422, "Unknown platform")
    row = _get(db, user.id)
    layout = _validate_layout(payload.widgets, (row.layouts or {}).get(payload.platform, []))
    layout = _apply_learned_order(row, payload.platform, layout)
    proposal = UIChangeProposal(
        id=str(uuid4()),
        user_id=user.id,
        title=payload.title,
        reason=payload.reason,
        layout={"platform": payload.platform, "widgets": layout},
        status="pending",
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return _proposal_out(proposal)


@router.post("/proposals/{proposal_id}/decision")
def decide_proposal(
    proposal_id: str,
    payload: ProposalDecision,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if payload.decision not in ("approve", "reject"):
        raise HTTPException(422, "Decision must be approve or reject")
    proposal = db.query(UIChangeProposal).filter_by(id=proposal_id, user_id=user.id).first()
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(409, "Proposal is already decided")
    row = _get(db, user.id)
    if payload.decision == "approve":
        platform = proposal.layout["platform"]
        layout = _validate_layout(
            [LayoutWidget(**w) for w in proposal.layout["widgets"]],
            (row.layouts or {}).get(platform, []),
        )
        _snapshot(row, f"proposal:{platform}")
        row.layouts = {**(row.layouts or {}), platform: layout}
        _record_layout_choice(row, platform, layout)
        proposal.status = "approved"
    else:
        proposal.status = "rejected"
    proposal.decided_at = datetime.now(UTC)
    db.commit()
    return {"proposal": _proposal_out(proposal), "version": row.version}


@router.post("/rollback")
def rollback(user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = _get(db, user.id)
    if not row.history:
        raise HTTPException(409, "There is no earlier UI configuration to restore")
    previous = row.history[-1]
    _snapshot(row, "rollback")
    row.preferences = deepcopy(previous["preferences"])
    row.layouts = deepcopy(previous["layouts"])
    db.commit()
    return {"version": row.version, "preferences": row.preferences, "layouts": row.layouts}


def _check_version(row: UIWorkspaceConfig, expected: int) -> None:
    if row.version != expected:
        raise HTTPException(
            409,
            {
                "message": "UI state changed elsewhere; refresh before saving",
                "version": row.version,
            },
        )


def _proposal_out(p: UIChangeProposal):
    return {
        "id": p.id,
        "title": p.title,
        "reason": p.reason,
        "layout": p.layout,
        "status": p.status,
        "created_at": p.created_at,
        "decided_at": p.decided_at,
    }
