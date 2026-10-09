"""Assistant awareness endpoints: live situation, personal model, proactive briefing."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.intelligence.briefing import build_briefing, narrate_briefing
from app.intelligence.personal_model import build_personal_model, render_personal_model
from app.intelligence.situation import build_situation, last_user_message_at, render_situation
from app.models.user import User

router = APIRouter(prefix="/assistant", tags=["Assistant"])


@router.get("/situation", summary="Live situation snapshot (contextual memory)")
def get_situation(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return build_situation(db, user, since=last_user_message_at(db, user.id))


@router.get("/profile", summary="Personal model: stated + observed (external memory)")
def get_profile(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return build_personal_model(db, user)


@router.get("/behavior", summary="Follow-through patterns IRIS has learned (deadlines, routines, workouts, money)")
def get_behavior(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.intelligence.behavior import observe_behavior

    return observe_behavior(db, user)


@router.get("/briefing", summary="Proactive briefing for right now")
async def get_briefing(
    narrate: bool = Query(False, description="Have the active AI model narrate the briefing"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    situation = build_situation(db, user, since=last_user_message_at(db, user.id))
    personal_model = build_personal_model(db, user)
    briefing = build_briefing(situation, personal_model)
    if narrate:
        briefing = await narrate_briefing(
            briefing, render_situation(situation), render_personal_model(personal_model)
        )
    return briefing
