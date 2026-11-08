"""Knowledge permission enforcement.

Permissions are enforced in the service layer *before* any claim text is
placed in a prompt, API response or export. Frontend filtering is never
trusted as a security boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.knowledge.types import (
    AccessLevel,
    SENSITIVITY_ORDER,
    Sensitivity,
    max_sensitivity,
    utcnow,
)
from app.models.knowledge import KnowledgePermission, KnowledgeNode

logger = get_logger("iris.knowledge.permissions")


@dataclass(frozen=True)
class PrincipalPolicy:
    name: str
    description: str
    allowed_node_types: frozenset[str] | None = None
    allowed_categories: frozenset[str] | None = None
    max_sensitivity: str = Sensitivity.ORDINARY.value
    allowed_access_levels: frozenset[str] = field(
        default_factory=lambda: frozenset({AccessLevel.SHARED.value})
    )
    can_write: bool = False
    can_export: bool = False


ALL_NODE_TYPES = None

PRINCIPAL_POLICIES: dict[str, PrincipalPolicy] = {
    "iris_core": PrincipalPolicy(
        name="iris_core",
        description="IRIS Supervisor: global authorised retrieval across the knowledge base.",
        allowed_node_types=ALL_NODE_TYPES,
        allowed_categories=None,
        max_sensitivity=Sensitivity.SENSITIVE.value,
        allowed_access_levels=frozenset({AccessLevel.SHARED.value, AccessLevel.PERSONAL.value}),
        can_write=True,
        can_export=True,
    ),
    "user": PrincipalPolicy(
        name="user",
        description="The knowledge owner through the IRIS interface.",
        allowed_node_types=ALL_NODE_TYPES,
        allowed_categories=None,
        max_sensitivity=Sensitivity.SENSITIVE.value,
        allowed_access_levels=frozenset({AccessLevel.SHARED.value, AccessLevel.PERSONAL.value}),
        can_write=True,
        can_export=True,
    ),
    "coworker:developer": PrincipalPolicy(
        name="coworker:developer",
        description="Technical project, architecture and decision knowledge only.",
        allowed_node_types=frozenset(
            {
                "project", "technology", "concept", "document", "decision",
                "goal", "organisation", "event", "topic",
            }
        ),
        allowed_categories=frozenset({"projects", "learning", "decisions", "work", "goals"}),
        max_sensitivity=Sensitivity.ORDINARY.value,
        allowed_access_levels=frozenset({AccessLevel.SHARED.value}),
        can_write=False,
    ),
    "coworker:workspace": PrincipalPolicy(
        name="coworker:workspace",
        description="Work projects, connected documents and project events.",
        allowed_node_types=frozenset(
            {"project", "document", "organisation", "event", "technology", "decision", "topic"}
        ),
        allowed_categories=frozenset({"work", "projects", "learning", "daily", "decisions"}),
        max_sensitivity=Sensitivity.ORDINARY.value,
        allowed_access_levels=frozenset({AccessLevel.SHARED.value}),
        can_write=False,
    ),
    "coworker:notification": PrincipalPolicy(
        name="coworker:notification",
        description="Processed transaction-event records only; never a private knowledge channel.",
        allowed_node_types=frozenset({"event", "document"}),
        allowed_categories=frozenset({"work", "financial", "daily"}),
        max_sensitivity=Sensitivity.ORDINARY.value,
        allowed_access_levels=frozenset({AccessLevel.SHARED.value}),
        can_write=False,
    ),
    "coworker:scribe": PrincipalPolicy(
        name="coworker:scribe",
        description="Documentation and summarisation over shareable project knowledge.",
        allowed_node_types=frozenset(
            {"project", "document", "decision", "goal", "concept", "technology", "event", "topic"}
        ),
        allowed_categories=frozenset({"projects", "decisions", "goals", "learning", "work"}),
        max_sensitivity=Sensitivity.ORDINARY.value,
        allowed_access_levels=frozenset({AccessLevel.SHARED.value}),
        can_write=False,
    ),
    "coworker:researcher": PrincipalPolicy(
        name="coworker:researcher",
        description="Shareable research, project and technical knowledge.",
        allowed_node_types=frozenset(
            {"project", "technology", "concept", "document", "topic", "organisation", "decision", "goal"}
        ),
        allowed_categories=frozenset({"projects", "learning", "decisions", "work", "goals"}),
        max_sensitivity=Sensitivity.ORDINARY.value,
        allowed_access_levels=frozenset({AccessLevel.SHARED.value}),
        can_write=False,
    ),
}

DEFAULT_PRINCIPAL = "iris_core"


def _default_policy(principal: str) -> PrincipalPolicy:
    return PrincipalPolicy(
        name=principal,
        description="Unrecognised principal: only ordinary shareable knowledge.",
        max_sensitivity=Sensitivity.ORDINARY.value,
        allowed_access_levels=frozenset({AccessLevel.SHARED.value}),
    )


def resolve_policy(principal: str) -> PrincipalPolicy:
    key = (principal or DEFAULT_PRINCIPAL).strip().lower()
    if key in PRINCIPAL_POLICIES:
        return PRINCIPAL_POLICIES[key]
    if key.startswith("coworker:"):
        return _default_policy(key)
    return _default_policy(key)


def split_principal(principal: str) -> tuple[str, str]:
    raw = (principal or DEFAULT_PRINCIPAL).strip().lower()
    if ":" in raw:
        kind, value = raw.split(":", 1)
        return kind, value
    return "role", raw


@dataclass
class PermissionContext:
    user_id: int
    principal: str
    policy: PrincipalPolicy
    grants: list[KnowledgePermission] = field(default_factory=list)

    @property
    def is_owner(self) -> bool:
        return self.policy.name in {"iris_core", "user"}

    def explicit_grants(
        self,
        *,
        node_id: str | None = None,
        claim_id: str | None = None,
        category: str | None = None,
    ) -> list[KnowledgePermission]:
        kind, value = split_principal(self.principal)
        matching: list[KnowledgePermission] = []
        now = utcnow()
        for grant in self.grants:
            if not grant.can_read:
                continue
            if grant.expires_at and grant.expires_at < now:
                continue
            if grant.principal_type not in {kind, "*"}:
                continue
            if grant.principal_id not in {value, "*"}:
                continue
            if grant.knowledge_type == "global":
                matching.append(grant)
            elif grant.knowledge_type == "node" and node_id and grant.knowledge_id == node_id:
                matching.append(grant)
            elif grant.knowledge_type == "claim" and claim_id and grant.knowledge_id == claim_id:
                matching.append(grant)
        return matching

    def can_read(
        self,
        *,
        sensitivity: str | None,
        access_level: str | None,
        node_type: str | None = None,
        category: str | None = None,
        node_id: str | None = None,
        claim_id: str | None = None,
    ) -> bool:
        sensitivity = sensitivity or Sensitivity.ORDINARY.value
        access_level = access_level or AccessLevel.SHARED.value

        grants = self.explicit_grants(node_id=node_id, claim_id=claim_id, category=category)
        grant_level = max_sensitivity(*(g.access_level for g in grants))
        grant_ok = bool(grants) and SENSITIVITY_ORDER.get(sensitivity, 0) <= SENSITIVITY_ORDER.get(
            grant_level, -1
        )
        if access_level == AccessLevel.PRIVATE_WORKSPACE.value:
            grant_ok = grant_ok and access_level in {g.access_level for g in grants}
        if grant_ok:
            # An explicit, unexpired grant is authoritative for the item it
            # names, including items outside the principal's default scope.
            return True

        if self.policy.allowed_node_types is not None and node_type not in self.policy.allowed_node_types:
            return False
        if self.policy.allowed_categories is not None and category not in self.policy.allowed_categories:
            return False

        return (
            SENSITIVITY_ORDER.get(sensitivity, 0)
            <= SENSITIVITY_ORDER.get(self.policy.max_sensitivity, 0)
            and access_level in self.policy.allowed_access_levels
        )

    def can_write(self, node_id: str | None = None, claim_id: str | None = None) -> bool:
        if self.policy.can_write:
            return True
        return any(
            g.can_write
            for g in self.explicit_grants(node_id=node_id, claim_id=claim_id)
        )

    def filter_nodes(self, nodes: list[KnowledgeNode]) -> list[KnowledgeNode]:
        return [
            node
            for node in nodes
            if self.can_read(
                sensitivity=node.sensitivity,
                access_level=node.access_level,
                node_type=node.node_type,
                node_id=node.id,
            )
        ]


def build_permission_context(
    db: Session, user_id: int, principal: str = DEFAULT_PRINCIPAL
) -> PermissionContext:
    grants = (
        db.query(KnowledgePermission)
        .filter(KnowledgePermission.user_id == user_id, KnowledgePermission.can_read.is_(True))
        .all()
    )
    return PermissionContext(
        user_id=user_id,
        principal=principal or DEFAULT_PRINCIPAL,
        policy=resolve_policy(principal or DEFAULT_PRINCIPAL),
        grants=grants,
    )


def record_denial(principal: str, reason: str) -> None:
    """Observable denial without content or credentials in the log line."""
    try:
        from app.knowledge.observability import knowledge_metrics

        knowledge_metrics.increment("permission_denials")
    except Exception:  # pragma: no cover - metrics must never break retrieval
        pass
    logger.info("knowledge_access_denied principal=%s reason=%s", principal, reason)
