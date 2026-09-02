import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.providers.omniroute import OmniRouteProvider
from app.intelligence.recommendation import DecisionRecommendationOut

SYSTEM_PROMPT = """You are IRIS, a personal decision intelligence system for a founder-student.
Mission: Given current situation, determine what deserves attention right now.
Respond ONLY with a valid JSON matching DecisionRecommendationOut schema."""


async def main():
    print("=" * 60)
    print("1. Initializing OmniRouteProvider...")
    provider = OmniRouteProvider(
        base_url="http://localhost:20128/v1",
        model="aug/gemini-3.0-flash",
    )
    print(f"Provider: name={provider.name}, model={provider.model}, enabled={provider.enabled}")

    print("\n" + "=" * 60)
    print("2. Testing Query 1: 'What should I do right now?'")
    context_1 = {
        "available_minutes": 60,
        "ranked_tasks": [
            {
                "task": {"id": 101, "title": "Customer Discovery Outreach", "area": "STARTUP"},
                "breakdown": {"total": 45, "notes": ["Directly unblocks validation milestone"]},
            }
        ],
        "goals": [{"name": "100 Customer Interviews", "status": "BEHIND"}],
    }
    prompt_1 = f"CONTEXT:\n{json.dumps(context_1)}\n\nWhat should I do right now?"
    res_1 = await provider.generate_structured(
        system=SYSTEM_PROMPT,
        prompt=prompt_1,
        schema=DecisionRecommendationOut,
    )
    print("Validated Output 1:")
    print(f"  Title: {res_1.title}")
    print(f"  Decision Type: {res_1.decision_type}")
    print(f"  Recommendation Type: {res_1.recommendation_type}")
    print(f"  Task ID: {res_1.task_id}")
    print(f"  Reason: {res_1.reason}")
    print(f"  Confidence: {res_1.confidence}")

    print("\n" + "=" * 60)
    print("3. Testing Query 2: 'I have 90 minutes tonight. What should I work on?'")
    context_2 = {
        "available_minutes": 90,
        "ranked_tasks": [
            {
                "task": {"id": 202, "title": "Implement Analytics Pipeline", "area": "INTERNSHIP"},
                "breakdown": {"total": 50, "notes": ["Deliverable due tomorrow morning"]},
            },
            {
                "task": {"id": 203, "title": "Cold Email Outreach", "area": "STARTUP"},
                "breakdown": {"total": 35, "notes": ["Daily quota 10 emails"]},
            },
        ],
    }
    prompt_2 = (
        f"CONTEXT:\n{json.dumps(context_2)}\n\nI have 90 minutes tonight. What should I work on?"
    )
    res_2 = await provider.generate_structured(
        system=SYSTEM_PROMPT,
        prompt=prompt_2,
        schema=DecisionRecommendationOut,
    )
    print("Validated Output 2:")
    print(f"  Title: {res_2.title}")
    print(f"  Decision Type: {res_2.decision_type}")
    print(f"  Task ID: {res_2.task_id}")
    print(f"  Duration: {res_2.duration_minutes}m")
    print(f"  Reason: {res_2.reason}")
    print(f"  Confidence: {res_2.confidence}")

    print("\n" + "=" * 60)
    print("Live OmniRoute structured verification successful!")


if __name__ == "__main__":
    asyncio.run(main())
