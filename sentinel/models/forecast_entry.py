"""
sentinel/models/forecast_entry.py — Level 7 Predictive Risk Intelligence
ForecastEntry Pydantic model with serialization for Qdrant storage.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ForecastHorizon(str, Enum):
    H24 = "H24"   # predicted within 24 hours
    H48 = "H48"   # predicted within 48 hours
    H72 = "H72"   # predicted within 72 hours
    H7D = "H7D"   # predicted within 7 days

    def hours(self) -> int:
        """Return the horizon in hours for resolution comparison."""
        return {"H24": 24, "H48": 48, "H72": 72, "H7D": 168}[self.value]


class ForecastOutcome(str, Enum):
    PENDING = "PENDING"
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    EXPIRED = "EXPIRED"


class ForecastEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    signal_id: str
    signal_title: str
    signal_category: str = "UNKNOWN"
    current_priority: str   # P2 or P3
    predicted_priority: str  # P0 or P1
    probability: float       # 0.0–1.0
    horizon: ForecastHorizon = ForecastHorizon.H72
    reasoning: str
    evidence: list[str] = Field(default_factory=list)
    outcome: ForecastOutcome = ForecastOutcome.PENDING
    resolved_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_payload(self) -> dict[str, Any]:
        """Convert to flat dict for Qdrant payload storage."""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "signal_id": self.signal_id,
            "signal_title": self.signal_title,
            "signal_category": self.signal_category,
            "current_priority": self.current_priority,
            "predicted_priority": self.predicted_priority,
            "probability": self.probability,
            "horizon": self.horizon.value,
            "reasoning": self.reasoning,
            "evidence": self.evidence,
            "outcome": self.outcome.value,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ForecastEntry":
        """Reconstruct from Qdrant payload."""
        return cls(
            id=payload["id"],
            tenant_id=payload["tenant_id"],
            signal_id=payload["signal_id"],
            signal_title=payload["signal_title"],
            signal_category=payload.get("signal_category", "UNKNOWN"),
            current_priority=payload["current_priority"],
            predicted_priority=payload["predicted_priority"],
            probability=payload["probability"],
            horizon=ForecastHorizon(payload["horizon"]),
            reasoning=payload["reasoning"],
            evidence=payload.get("evidence", []),
            outcome=ForecastOutcome(payload["outcome"]),
            resolved_at=datetime.fromisoformat(payload["resolved_at"])
            if payload.get("resolved_at")
            else None,
            created_at=datetime.fromisoformat(payload["created_at"]),
        )

    def embed_text(self) -> str:
        """Text to embed for similarity search."""
        return f"{self.signal_title} {self.reasoning}"
