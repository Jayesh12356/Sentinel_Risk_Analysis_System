"""PromptVersion — versioned prompt storage for SENTINEL Level 4.

Each agent's prompt is stored as a PromptVersion in Qdrant.
The PromptOptimiser creates new versions when brief quality drops.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PromptVersion(BaseModel):
    """A single versioned prompt for one agent."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str = Field(..., description="Agent this prompt belongs to, e.g. 'BriefWriter'")
    version: int = Field(default=1, ge=1, description="Version number, increments on each optimisation")
    prompt_text: str = Field(..., description="Full prompt template text")
    quality_score: Optional[float] = Field(
        default=None,
        description="Quality score that triggered this version (None for initial seed)",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True, description="Only one active version per agent")

    def to_payload(self) -> dict:
        """Convert to Qdrant payload dict."""
        return {
            "id": self.id,
            "agent_name": self.agent_name,
            "version": self.version,
            "prompt_text": self.prompt_text,
            "quality_score": self.quality_score,
            "created_at": self.created_at.isoformat(),
            "is_active": self.is_active,
        }

    @classmethod
    def from_payload(cls, payload: dict) -> PromptVersion:
        """Reconstruct from a Qdrant payload dict."""
        data = dict(payload)
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)
