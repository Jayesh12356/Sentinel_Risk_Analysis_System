"""FeedbackEntry — human-in-the-loop feedback model for SENTINEL Level 5.

Humans submit feedback on processed signals via one-click links in
alert emails and Slack messages. Feedback is stored in Qdrant and
read by FeedbackAgent to adjust confidence weights.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FeedbackAction(str, Enum):
    """The four feedback actions a human can submit."""

    ACTED_ON = "acted_on"           # Signal was real and important — human took action
    FALSE_POSITIVE = "false_positive"  # Signal was wrong or irrelevant
    ESCALATE = "escalate"           # Human wants higher priority than SENTINEL assigned
    DISMISS = "dismiss"             # Acknowledged but no action needed


class FeedbackEntry(BaseModel):
    """A single piece of human feedback on a processed signal."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str = Field(..., description="UUID of the signal being rated")
    brief_id: str = Field(..., description="UUID of the brief that contained this signal")
    action: FeedbackAction = Field(..., description="Human feedback action")
    note: Optional[str] = Field(default=None, description="Optional human comment")

    # Snapshot of signal metadata at feedback time
    signal_title: str = Field(default="", description="Title of the original signal")
    signal_source: str = Field(default="", description="Source category: CYBER, NEWS, FINANCIAL")
    original_priority: str = Field(default="", description="P0/P1/P2/P3 as assigned by pipeline")
    original_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    submitted_by: str = Field(default="human", description="Who submitted feedback")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_payload(self) -> dict:
        """Serialize to Qdrant payload dict."""
        return {
            "id": self.id,
            "signal_id": self.signal_id,
            "brief_id": self.brief_id,
            "action": self.action.value,
            "note": self.note,
            "signal_title": self.signal_title,
            "signal_source": self.signal_source,
            "original_priority": self.original_priority,
            "original_confidence": self.original_confidence,
            "submitted_by": self.submitted_by,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: dict) -> FeedbackEntry:
        """Reconstruct from Qdrant payload dict."""
        data = dict(payload)
        if "action" in data and isinstance(data["action"], str):
            data["action"] = FeedbackAction(data["action"])
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)
