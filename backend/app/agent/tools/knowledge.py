"""Knowledge tools exposed to IRIS Supervisor and authorised coworkers.

Retrieval is always permission-filtered by the knowledge service. These tools
never read knowledge tables directly and never bypass sensitivity checks.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.schemas import ToolResult
from app.agent.tools.base import RiskLevel, Tool, VerificationStrategy
from app.knowledge.pipeline import capture_text
from app.knowledge.retrieval import knowledge_retrieval
from app.knowledge.service import knowledge_service
from app.models.user import User


class SearchKnowledgeParams(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="What to recall from the knowledge base")
    limit: int = Field(8, ge=1, le=20, description="Maximum number of authorised claims")
    include_history: bool = Field(False, description="Include superseded historical claims")


class SearchKnowledgeTool(Tool):
    name = "search_knowledge"
    description = (
        "Search the user's durable knowledge base (entities, facts, decisions, projects, "
        "goals, experiences and inferences) with provenance and verification status."
    )
    parameters_schema = SearchKnowledgeParams
    risk_level = RiskLevel.READ_ONLY
    category = "knowledge"

    def __init__(self, principal: str = "iris_core") -> None:
        self.principal = principal

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        result = knowledge_retrieval.search(
            db,
            user_id=user.id,
            query=kwargs["query"],
            principal=self.principal,
            limit=kwargs.get("limit", 8),
            include_history=kwargs.get("include_history", False),
        )
        claims = [
            {
                "claim_id": item["claim_id"],
                "node": item["node_name"],
                "claim": item["claim_text"],
                "type": item["claim_type"],
                "verification": item["verification_status"],
                "confidence": item["confidence"],
                "source": item["source"]["ref"] if item.get("source") else None,
            }
            for item in result["results"]
        ]
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"claims": claims, "count": len(claims)},
            summary=(
                f"Found {len(claims)} authorised knowledge claim(s) for '{kwargs['query']}'."
                if claims
                else "No authorised knowledge matched that query."
            ),
        )


class CaptureKnowledgeParams(BaseModel):
    text: str = Field(..., min_length=4, max_length=8000, description="Durable information to store")
    title: str | None = Field(None, max_length=200, description="Optional short title")
    source_type: str = Field("user_explicit", description="Origin kind: user_explicit, document, meeting")


class CaptureKnowledgeTool(Tool):
    name = "capture_knowledge"
    description = (
        "Explicitly save durable information the user asked IRIS to remember. "
        "Routine conversation capture happens automatically; use this for explicit "
        "'remember this' requests or supplied documents."
    )
    parameters_schema = CaptureKnowledgeParams
    risk_level = RiskLevel.ORDINARY_WRITE
    verification_strategy = VerificationStrategy.DB_CHECK
    read_only = False
    category = "knowledge"

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        result = capture_text(
            db,
            user_id=user.id,
            text=kwargs["text"],
            source_type=kwargs.get("source_type", "user_explicit"),
            title=kwargs.get("title"),
            origin="user",
        )
        return ToolResult(
            tool_name=self.name,
            success=True,
            data=result,
            summary="Stored in the knowledge base; extraction is queued durably.",
        )

    async def verify(self, db: Session, user: User, result: ToolResult, **kwargs: Any) -> bool:
        source_id = result.data.get("source_id") if isinstance(result.data, dict) else None
        if not source_id:
            return False
        from app.models.knowledge import KnowledgeSource

        return (
            db.query(KnowledgeSource.id)
            .filter(KnowledgeSource.id == source_id, KnowledgeSource.user_id == user.id)
            .first()
            is not None
        )


class KnowledgeOverviewParams(BaseModel):
    limit: int = Field(10, ge=1, le=25)


class KnowledgeOverviewTool(Tool):
    name = "get_knowledge_overview"
    description = "Summarise the user's current knowledge base: recent entities, claims, insights and conflicts."
    parameters_schema = KnowledgeOverviewParams
    risk_level = RiskLevel.READ_ONLY
    category = "knowledge"

    def __init__(self, principal: str = "iris_core") -> None:
        self.principal = principal

    async def run(self, db: Session, user: User, **kwargs: Any) -> ToolResult:
        data = knowledge_service.overview(db, user.id, principal=self.principal)
        limit = kwargs.get("limit", 10)
        claims = [
            {
                "node": claim.node.canonical_name if claim.node else None,
                "text": claim.claim_text,
                "type": claim.claim_type,
                "verification": claim.verification_status,
            }
            for claim in data["recent_claims"][:limit]
        ]
        nodes = [
            {"name": node.canonical_name, "type": node.node_type}
            for node in data["recent_nodes"][:limit]
        ]
        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "totals": data["totals"],
                "recent_nodes": nodes,
                "recent_claims": claims,
                "open_reviews": len(data["reviews"]),
            },
            summary=(
                f"Knowledge base: {data['totals']['nodes']} entities, "
                f"{data['totals']['claims']} active claims, "
                f"{len(data['reviews'])} open review(s)."
            ),
        )


def knowledge_tools(principal: str = "iris_core") -> list[Tool]:
    return [
        SearchKnowledgeTool(principal=principal),
        CaptureKnowledgeTool(),
        KnowledgeOverviewTool(principal=principal),
    ]
