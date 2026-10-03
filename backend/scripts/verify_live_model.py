"""Live smoke test for whatever model is configured (AI_PROVIDER / AI_MODEL / AI_API_KEY).

Checks the three things the IRIS harness relies on and prints the capabilities
it settled on (including any it had to downgrade at runtime):

1. Plain chat
2. Structured output validated against a Pydantic schema
3. Native tool calling (skipped if the model does not support it)

Usage:
    python scripts/verify_live_model.py
    AI_PROVIDER=ollama AI_MODEL=qwen3:8b python scripts/verify_live_model.py
"""

import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.ai.factory import get_ai_provider  # noqa: E402
from app.ai.provider import ChatMessage, ToolDefinition  # noqa: E402
from app.intelligence.recommendation import DecisionRecommendationOut  # noqa: E402

SYSTEM = "You are IRIS, a personal decision intelligence assistant for a founder-student."
CONTEXT = (
    "Available: 60 minutes. Top task #101 'Customer Discovery Outreach' (STARTUP), "
    "directly unblocks the validation milestone. Goal '100 Customer Interviews' is BEHIND."
)
TASK_TOOL = ToolDefinition(
    name="get_tasks",
    description="Retrieve the user's open tasks.",
    parameters={
        "type": "object",
        "properties": {"limit": {"type": "integer", "description": "Max tasks"}},
    },
)


async def _timed(label, coro):
    start = time.perf_counter()
    try:
        result = await coro
        print(f"  [ok]   {label} ({time.perf_counter() - start:.1f}s)")
        return result
    except Exception as exc:
        print(f"  [fail] {label}: {type(exc).__name__}: {exc}")
        return None


async def main() -> int:
    provider = get_ai_provider()
    print("=" * 64)
    print(f"Provider: {provider.name}   Model: {provider.model}   Enabled: {provider.enabled}")
    if not provider.enabled:
        print("Not configured. Set AI_PROVIDER, AI_MODEL and AI_API_KEY (or AI_BASE_URL).")
        return 1
    print(f"Capabilities (initial): {provider.capabilities.to_dict()}")
    print("=" * 64)

    failures = 0
    if provider.supports_chat:
        res = await _timed(
            "chat",
            provider.chat(
                [
                    ChatMessage(role="system", content=SYSTEM),
                    ChatMessage(
                        role="user", content="Reply with one short sentence: are you ready?"
                    ),
                ]
            ),
        )
        failures += res is None
        if res:
            print(f"         -> {res.content[:160]!r}")
            if res.reasoning:
                print(f"         reasoning captured ({len(res.reasoning)} chars)")

    rec = await _timed(
        "structured output",
        provider.generate_structured(
            system=SYSTEM,
            prompt=f"CONTEXT: {CONTEXT}\n\nWhat should I do right now?",
            schema=DecisionRecommendationOut,
        ),
    )
    failures += rec is None
    if rec:
        print(f"         -> {rec.decision_type}: {rec.title} (task_id={rec.task_id})")

    if provider.supports_chat and provider.capabilities.native_tools:
        res = await _timed(
            "native tool calling",
            provider.chat(
                [
                    ChatMessage(role="system", content=SYSTEM),
                    ChatMessage(role="user", content="Look up my open tasks (limit 5)."),
                ],
                tools=[TASK_TOOL],
            ),
        )
        if res is None:
            failures += 1
        elif res.tool_calls:
            tc = res.tool_calls[0]
            print(f"         -> called {tc.name}({tc.arguments})")
        else:
            print("         -> model answered without calling the tool (harness still works)")
    else:
        print("  [skip] native tool calling: harness will use the structured_json strategy")

    print("=" * 64)
    print(f"Capabilities (after run): {provider.capabilities.to_dict()}")
    strategy = "native_tools" if provider.capabilities.native_tools else "structured_json"
    print(f"Agent strategy: {strategy}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
