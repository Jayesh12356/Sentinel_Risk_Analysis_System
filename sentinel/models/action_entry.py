"""ActionEntry model — autonomous action tracking for Level 8.

Actions are created by ActionPlanner and executed by ActionEngine.
Confidence-gated autonomy determines whether actions auto-execute,
require human approval, or are report-only.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Types of actions SENTINEL can take."""

    JIRA_TICKET = "JIRA_TICKET"
    PAGERDUTY_ALERT = "PAGERDUTY_ALERT"
    EMAIL_DRAFT = "EMAIL_DRAFT"
    WEBHOOK = "WEBHOOK"
    SLACK_MESSAGE = "SLACK_MESSAGE"
    INITIATE_NEGOTIATION = "INITIATE_NEGOTIATION"  # Level 9


class ActionStatus(str, Enum):
    """Lifecycle status of an action."""

    AUTO_EXECUTED = "AUTO_EXECUTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    REPORT_ONLY = "REPORT_ONLY"


class ActionEntry(BaseModel):
    """A single autonomous action created by ActionPlanner."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = Field(..., description="Tenant that owns this action")
    signal_id: str = Field(..., description="Signal that triggered this action")
    brief_id: str = Field(default="", description="Associated brief ID")
    action_type: ActionType = Field(..., description="Type of action")
    status: ActionStatus = Field(
        default=ActionStatus.PENDING_APPROVAL,
        description="Current lifecycle status",
    )
    title: str = Field(..., description="Human-readable action title")
    description: str = Field(default="", description="Detailed action description")
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Integration-specific payload (e.g. Jira fields, webhook body)",
    )
    reasoning: str = Field(
        default="",
        description="Why ActionPlanner decided this action is needed",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="ActionPlanner confidence in this action (0.0–1.0)",
    )
    executed_at: Optional[datetime] = Field(
        default=None, description="When the action was executed"
    )
    approved_by: Optional[str] = Field(
        default=None, description="Who approved the action (None if auto)"
    )
    result: Optional[Dict[str, Any]] = Field(
        default=None, description="Execution result from the integration"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_payload(self) -> dict:
        """Serialise to Qdrant payload dict."""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "signal_id": self.signal_id,
            "brief_id": self.brief_id,
            "action_type": self.action_type.value,
            "status": self.status.value,
            "title": self.title,
            "description": self.description,
            "payload": self.payload,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "approved_by": self.approved_by,
            "result": self.result,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: dict) -> "ActionEntry":
        """Reconstruct from Qdrant payload dict."""
        data = dict(payload)
        if "action_type" in data and isinstance(data["action_type"], str):
            data["action_type"] = ActionType(data["action_type"])
        if "status" in data and isinstance(data["status"], str):
            data["status"] = ActionStatus(data["status"])
        for ts_field in ("executed_at", "created_at"):
            if ts_field in data and isinstance(data[ts_field], str):
                data[ts_field] = datetime.fromisoformat(data[ts_field])
        return cls(**data)

    def embed_text(self) -> str:
        """Text used when embedding this action for similarity search."""
        return f"{self.action_type.value} {self.title} {self.description} {self.reasoning}"
