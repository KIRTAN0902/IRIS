"""Recommender feature -- thin module exposing the recommendation generator.

Lives in the AI layer so callers (services, routes) import from ``app.ai``
rather than reaching into orchestration internals.
"""

from __future__ import annotations

from app.ai.features import generate_recommendation

__all__ = ["generate_recommendation"]
