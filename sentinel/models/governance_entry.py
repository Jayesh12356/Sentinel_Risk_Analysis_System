"""GovernanceEntry — immutable audit log entry (Level 10).

Every autonomous decision is logged as a GovernanceEntry.
Write-once, never updated or deleted.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class GovernanceEntry(BaseModel):
    """A single entry in the immutable governance audit log."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str  # ACTION_EXECUTED, PROMPT_CHANGED, WEIGHT_ADJUSTED,
                     # NEGOTIATION_STARTED, OVERRIDE_APPLIED, AB_TEST_RESULT,
                     # META_REPORT_GENERATED
    agent_name: str = ""
    tenant_id: str = "default"
    description: str = ""
    reasoning: str = ""
    confidence: Optional[float] = None
    human_involved: bool = False
    override: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_payload(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return {
            "id": self.id,
            "event_type": self.event_type,
            "agent_name": self.agent_name,
            "tenant_id": self.tenant_id,
            "description": self.description,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "human_involved": self.human_involved,
            "override": self.override,
            "created_at": self.created_at.isoformat(),
            "type": "governance_entry",
        }

    @classmethod
    def from_payload(cls, data: dict) -> GovernanceEntry:
        """Deserialize from dict."""
        data = dict(data)
        data.pop("type", None)
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)

    def embed_text(self) -> str:
        """Text for vector embedding."""
        return (
            f"[{self.event_type}] {self.agent_name} | "
            f"{self.description} | {self.reasoning}"
        )
