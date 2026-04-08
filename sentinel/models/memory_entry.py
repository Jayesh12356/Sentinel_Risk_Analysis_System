"""MemoryEntry — persistent memory for the SENTINEL pipeline (Level 3).

Each processed signal creates one MemoryEntry stored in Qdrant.
This enables agents to recall past events, detect recurring threats,
and provide context-aware recommendations.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    """A single memory entry representing a processed signal."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str = Field(..., description="Original signal UUID")
    title: str = Field(..., description="Signal title")
    summary: str = Field(default="", description="Brief summary of the event")
    entities: list[str] = Field(default_factory=list, description="Entity names extracted")
    priority: str = Field(default="P3", description="Signal priority at processing time")
    risk_score: float = Field(default=0.0, ge=0.0, le=10.0, description="Risk score from RiskAssessor")
    route_path: str = Field(default="FULL", description="Pipeline path taken: FULL/FAST/LOG_ONLY")
    company_matches: list[str] = Field(default_factory=list, description="Profile fields that matched")
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Company relevance score")
    source: str = Field(default="", description="Signal source (news, cyber, financial)")
    outcome: str = Field(default="", description="What action was recommended")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    embedding_text: Optional[str] = Field(
        default=None,
        description="Text that was embedded for vector search (not stored in Qdrant payload)",
    )

    def to_payload(self) -> dict:
        """Convert to Qdrant payload dict (excludes embedding_text)."""
        return {
            "id": self.id,
            "signal_id": self.signal_id,
            "title": self.title,
            "summary": self.summary,
            "entities": self.entities,
            "priority": self.priority,
            "risk_score": self.risk_score,
            "route_path": self.route_path,
            "company_matches": self.company_matches,
            "relevance_score": self.relevance_score,
            "source": self.source,
            "outcome": self.outcome,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: dict) -> MemoryEntry:
        """Reconstruct from a Qdrant payload dict."""
        data = dict(payload)
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)
