"""Proactive briefing: what the user needs to know right now, unprompted.

The briefing is always computed deterministically from the situation and the
personal model, so it works with no AI at all. When a model is available it can
be narrated into a short spoken-style briefing.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.logging import get_logger

logger = get_logger("iris.intelligence.briefing")


class BriefingNarrative(BaseModel):
    text: str = Field(..., description="Spoken-style briefing, 3-6 sentences")


def _dur(minutes: int | None) -> str:
    m = int(minutes or 0)
    if m < 60:
        return f"{m}m"
    return f"{m // 60}h {m % 60}m" if m % 60 else f"{m // 60}h"


def _in_window(hour: int, window: str) -> bool:
    try:
        start = int(window.split("-")[0][:2])
    except (ValueError, IndexError):
        return False
    return any((start + k) % 24 == hour for k in range(3))


def build_briefing(situation: dict[str, Any], personal_model: dict[str, Any]) -> dict[str, Any]:
    now, tasks, done = situation["now"], situation["tasks"], situation["done"]
    first_name = (personal_model.get("name") or "").split(" ")[0] or "there"
    part = now["part_of_day"]
    greeting = f"Working late, {first_name}." if part == "night" else f"Good {part}, {first_name}."

    points: list[dict[str, str]] = []

    def add(kind: str, text: str) -> None:
        points.append({"kind": kind, "text": text})

    if now.get("current_block"):
        add(
            "now",
            f"You're in {now['current_block']}, {_dur(now.get('minutes_left_in_block'))} left.",
        )
    if now.get("next_commitment"):
        add(
            "next",
            f"Next up: {now['next_commitment']} in {_dur(now.get('minutes_until_next_commitment'))}.",
        )

    if tasks["overdue"]:
        names = ", ".join(t["title"] for t in tasks["overdue"][:3])
        add("risk", f"{len(tasks['overdue'])} overdue: {names}.")
    if tasks["due_today"]:
        names = ", ".join(f"{t['title']} ({t['due']})" for t in tasks["due_today"][:3])
        add("deadline", f"Due today: {names}.")

    top = tasks["top_priorities"][0] if tasks["top_priorities"] else None
    if top:
        area = (top.get("area") or "").title()
        why = (top.get("why") or "").lower()
        detail = ", ".join(x for x in (area, why) if x)
        add("focus", f"Top priority: {top['title']}" + (f" ({detail})." if detail else "."))

    obs = personal_model.get("observed") or {}
    peak = obs.get("peak_hours")
    try:
        hour = int(now["local_time"].rsplit(", ", 1)[-1][:2])
    except (ValueError, IndexError):
        hour = -1
    if peak and hour >= 0:
        if _in_window(hour, peak["window"]):
            add(
                "energy",
                f"You're in your usual peak window ({peak['window']}): good time for deep work.",
            )
        else:
            add("energy", f"Your peak window is usually {peak['window']}; plan deep work there.")

    est = obs.get("estimation")
    if top and est and est["ratio"] > 1.15:
        add("tip", f"Plan buffer: {est['verdict']}.")

    since = situation.get("since_last_conversation")
    if since and since.get("became_overdue"):
        add(
            "change",
            f"Since we last talked, {', '.join(since['became_overdue'][:3])} became overdue.",
        )

    if done["today"]:
        add(
            "done",
            f"Done today: {len(done['today'])} ({', '.join(t['title'] for t in done['today'][:3])}).",
        )
    elif part in {"evening", "night"} and tasks["open_count"]:
        add("done", "Nothing marked done yet today.")

    if not tasks["open_count"]:
        add("focus", "No open tasks: a good moment to plan or rest.")

    headline = next(
        (p["text"] for p in points if p["kind"] in {"risk", "deadline", "focus"}),
        points[0]["text"] if points else "All clear.",
    )
    text = " ".join([greeting, *[p["text"] for p in points]])
    return {
        "greeting": greeting,
        "headline": headline,
        "points": points,
        "text": text,
        "source": "DETERMINISTIC",
    }


async def narrate_briefing(
    briefing: dict[str, Any], situation_text: str, profile_text: str
) -> dict[str, Any]:
    """Rewrite the briefing in natural spoken style with the active model, if available."""
    from app.ai.factory import get_ai_provider

    provider = get_ai_provider()
    if not provider.enabled:
        return briefing
    try:
        result = await provider.generate_structured(
            system=(
                "You are IRIS, a JARVIS-style personal assistant. Write a short spoken briefing "
                "(3-6 sentences) for the user: greet them, say what matters most right now, flag "
                "risks, and suggest the single best next move, tailored to how they work. Use only "
                "the facts provided; never invent tasks or times."
            ),
            prompt=(
                f"{profile_text}\n\n{situation_text}\n\n"
                f"Deterministic briefing points:\n{briefing['text']}"
            ),
            schema=BriefingNarrative,
        )
    except Exception as exc:
        logger.warning("Briefing narration failed, using deterministic briefing: %s", exc)
        return briefing
    return {**briefing, "text": result.text.strip(), "source": "AI"}
