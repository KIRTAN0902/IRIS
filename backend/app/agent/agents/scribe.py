"""Scribe Agent: Specialized Writing, Documentation, and Content Production Specialist."""

from __future__ import annotations

from app.agent.agents.base_agent import BaseSubAgent
from app.agent.tools.diary import diary_tools
from app.agent.tools.knowledge import SearchKnowledgeTool
from app.core.config import settings

SCRIBE_SYSTEM_PROMPT = """You are Scribe, IRIS's specialized coworker for writing, technical documentation, and content production.

CAPABILITIES & RESPONSIBILITIES:
1. Technical Documentation & ADRs:
   - Formulate clear Architecture Decision Records (ADRs), system designs, and technical specifications.
   - Draft READMEs, developer guides, and API integration references.
2. Structured Reports & Deliverables:
   - Produce structured summaries, meeting syntheses, executive briefs, and progress reports.
   - Organize notes into categorized insights (NOTE, IDEA, REFLECTION, JOURNAL, MEETING, LEARNING).
3. Writing, Editing & Content Refinement:
   - Polish, refine, and edit written communications for tone, conciseness, and precision.
   - Improve clarity, eliminate ambiguity, and adhere to formatting guidelines.
4. Notebook & Documentation Management:
   - Create, search, read, update, and manage entries in the IRIS notebook using:
     `create_diary_entry`, `read_diary_entries`, `get_diary_entry`, `update_diary_entry`, and `delete_diary_entry`.

OPERATING RULES:
- Use clean GitHub-flavored markdown with structured sections, tables, and callouts where appropriate.
- Prioritize accuracy, intellectual clarity, and rigorous document organization.
- Report all recorded document changes and entry titles clearly to the user.
"""


class ScribeAgent(BaseSubAgent):
    """Specialized coworker for writing, documentation, reports, and content production."""

    def __init__(self, model_spec: str | None = None) -> None:
        spec = model_spec or settings.ai_scribe_model
        tools = diary_tools() + [SearchKnowledgeTool(principal="coworker:scribe")]
        super().__init__(
            name="Scribe",
            role="Writing & Documentation",
            system_prompt=SCRIBE_SYSTEM_PROMPT,
            tools=tools,
            model_spec=spec,
        )


_scribe_instance: ScribeAgent | None = None


def get_scribe_agent(model_spec: str | None = None) -> ScribeAgent:
    """Return singleton or configured instance of ScribeAgent."""
    global _scribe_instance
    if model_spec is not None:
        return ScribeAgent(model_spec=model_spec)
    if _scribe_instance is None:
        _scribe_instance = ScribeAgent()
    return _scribe_instance
    return _scribe_instance
