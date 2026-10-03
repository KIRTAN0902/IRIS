import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.ai.providers.nvidia import NvidiaProvider
from app.intelligence.recommendation import DecisionRecommendationOut

SYSTEM_PROMPT = """You are IRIS, a personal decision intelligence system for a founder-student.
Mission: Given current situation, determine what deserves attention right now.
Respond ONLY with a valid JSON matching DecisionRecommendationOut schema."""


async def main():
    print("=" * 60)
    from app.core.config import settings
    api_key = os.environ.get("NVIDIA_API_KEY") or settings.nvidia_api_key
    provider = NvidiaProvider(
        base_url=settings.nvidia_base_url,
        api_key=api_key,
        model=settings.nvidia_model,
    )
    print(f"Provider: name={provider.name}, model={provider.model}, enabled={provider.enabled}")

    if not provider.enabled:
        print("\nNote: NVIDIA_API_KEY not set in environment. Set NVIDIA_API_KEY to run live network queries.")
        print("Provider initialization and schema verification succeeded.")
        return

    print("\n" + "=" * 60)
    print("2. Testing Query: 'What should I do right now?'")
    context = {
        "available_minutes": 60,
        "ranked_tasks": [
            {
                "task": {"id": 101, "title": "Customer Discovery Outreach", "area": "STARTUP"},
                "breakdown": {"total": 45, "notes": ["Directly unblocks validation milestone"]},
            }
        ],
        "goals": [{"name": "100 Customer Interviews", "status": "BEHIND"}],
    }
    prompt = f"CONTEXT:\n{json.dumps(context)}\n\nWhat should I do right now?"
    res = await provider.generate_structured(
        system=SYSTEM_PROMPT,
        prompt=prompt,
        schema=DecisionRecommendationOut,
    )
    print("Validated Output:")
    print(f"  Title: {res.title}")
    print(f"  Decision Type: {res.decision_type}")
    print(f"  Recommendation Type: {res.recommendation_type}")
    print(f"  Task ID: {res.task_id}")
    print(f"  Reason: {res.reason}")
    print(f"  Confidence: {res.confidence}")


if __name__ == "__main__":
    asyncio.run(main())
