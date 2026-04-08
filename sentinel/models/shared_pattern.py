"""SharedPattern model — anonymised cross-tenant threat patterns.

SharedPatterns are written to sentinel_shared_patterns after each pipeline run.
Company identifiers are NEVER stored — only generic technical entities.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List

from pydantic import BaseModel, Field

from sentinel.models.signal import SignalPriority, SignalSource


class SharedPattern(BaseModel):
    """An anonymised threat pattern contributed by one or more tenants.

    No tenant identifiers are stored — only generic technical entities
    such as CVE IDs, software names, and attack technique labels.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pattern_type: str = Field(
        ...,
        description="Category of threat: 'CVE_EXPLOIT', 'SUPPLY_CHAIN', 'REGULATORY', 'DATA_BREACH', 'FINANCIAL_FRAUD', 'GENERIC'",
    )
    entities: List[str] = Field(
        default_factory=list,
        description="Anonymised technical entities (CVE IDs, software names, attack techniques)",
    )
    source_type: SignalSource = Field(..., description="Origin signal type")
    priority: SignalPriority = Field(..., description="Highest priority seen for this pattern")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Average risk score across contributors")
    occurrence_count: int = Field(default=1, description="Number of pipeline runs where this pattern appeared")
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    tenant_count: int = Field(
        default=1,
        description="Number of distinct tenants that contributed (no names stored)",
    )

    def to_payload(self) -> dict:
        """Serialise to Qdrant payload dict."""
        return {
            "id": self.id,
            "pattern_type": self.pattern_type,
            "entities": self.entities,
            "source_type": self.source_type.value,
            "priority": self.priority.value,
            "risk_score": self.risk_score,
            "occurrence_count": self.occurrence_count,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "tenant_count": self.tenant_count,
        }

    @classmethod
    def from_payload(cls, payload: dict) -> "SharedPattern":
        """Reconstruct from Qdrant payload dict."""
        data = dict(payload)
        if "source_type" in data and isinstance(data["source_type"], str):
            data["source_type"] = SignalSource(data["source_type"])
        if "priority" in data and isinstance(data["priority"], str):
            data["priority"] = SignalPriority(data["priority"])
        for ts_field in ("first_seen", "last_seen"):
            if ts_field in data and isinstance(data[ts_field], str):
                data[ts_field] = datetime.fromisoformat(data[ts_field])
        return cls(**data)

    def embedding_text(self) -> str:
        """Text used when embedding this pattern for similarity search."""
        return f"{self.pattern_type} {' '.join(self.entities)}"
