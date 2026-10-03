"""Canonical names and validation for profile facts the engines depend on.

The scheduling engine needs machine-readable wake/sleep times. Historically
the same fact was stored under two names (``wake`` and ``wake_time``), so an
update to one could silently be ignored by code reading the other. Every
reader and writer goes through ``normalize_facts`` instead: aliases are folded
into the canonical key (the canonical key wins if both exist), and time facts
are always "HH:MM".
"""

from __future__ import annotations

import re
from typing import Any

FACT_ALIASES: dict[str, str] = {"wake": "wake_time", "sleep": "sleep_time"}
TIME_FACTS = frozenset({"wake_time", "sleep_time"})

_TIME_RE = re.compile(r"^\s*(\d{1,2})(?:[:.](\d{2}))?\s*([ap]\.?m\.?)?\s*$", re.IGNORECASE)


def normalize_hhmm(value: Any) -> str:
    """'6:30', '06:30', '6.30', '6:30 am', '11:30 PM', '7pm' -> 'HH:MM'. Raises ValueError."""
    match = _TIME_RE.match(str(value))
    if not match:
        raise ValueError(f"'{value}' is not a time; use HH:MM (e.g. 06:30 or 23:30)")
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    meridiem = (match.group(3) or "").lower().replace(".", "")
    if meridiem:
        if not 1 <= hour <= 12:
            raise ValueError(f"'{value}' is not a valid 12-hour time")
        hour = hour % 12 + (12 if meridiem == "pm" else 0)
    if hour > 23 or minute > 59:
        raise ValueError(f"'{value}' is not a valid time")
    return f"{hour:02d}:{minute:02d}"


def normalize_facts(facts: dict[str, Any] | None, *, strict: bool = False) -> dict[str, Any]:
    """Fold alias keys into canonical ones and normalise time facts.

    With ``strict`` (used on write), an unparseable time raises ValueError; on
    read it is dropped so a bad stored value can never break scheduling.
    """
    out = dict(facts or {})
    for alias, canonical in FACT_ALIASES.items():
        if alias in out:
            value = out.pop(alias)
            out.setdefault(canonical, value)
    for key in TIME_FACTS & out.keys():
        try:
            out[key] = normalize_hhmm(out[key])
        except ValueError:
            if strict:
                raise
            out.pop(key)
    return out
