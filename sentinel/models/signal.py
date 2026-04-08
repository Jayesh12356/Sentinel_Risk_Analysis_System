"""Signal — the core data unit flowing through the SENTINEL pipeline.

Every sensor agent (Layer 0) emits Signal objects.  They are enriched by
Layer 1 (EntityExtractor, SignalClassifier) and consumed by downstream
reasoning / deliberation agents.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SignalPriority(str, enum.Enum):
    """Priority classification assigned by SignalClassifier."""

    P0 = "P0"  # Critical — instant alert
    P1 = "P1"  # High     — daily digest
    P2 = "P2"  # Medium   — weekly report
    P3 = "P3"  # Low      — logged only


class SignalSource(str, enum.Enum):
    """Originating sensor agent."""

    NEWS = "news"          # NewsScanner
    CYBER = "cyber"        # CyberThreatAgent
    FINANCIAL = "financial"  # FinancialSignalAgent


class Entity(BaseModel):
    """Named entity extracted by EntityExtractor."""

    name: str = Field(..., description="Entity display name")
    entity_type: str = Field(
        ..., description="Entity type, e.g. ORG, PERSON, CVE, PRODUCT"
    )
    relevance: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Relevance score 0–1"
    )


class Signal(BaseModel):
    """Core intelligence signal flowing through the pipeline.

    Created by Layer 0 sensors, enriched by Layer 1, scored by Layer 2+.
    """

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="Unique signal identifier",
    )
    source: SignalSource = Field(..., description="Originating sensor agent")
    title: str = Field(..., description="Short headline / summary")
    content: str = Field(..., description="Full raw text of the signal")
    url: str = Field(default="", description="Source URL if available")
    published_at: datetime | None = Field(
        default=None, description="Original publication timestamp"
    )
    ingested_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when SENTINEL ingested this signal",
    )

    # --- Enrichment (set by Layer 1) ---
    entities: list[Entity] = Field(
        default_factory=list, description="Entities extracted by EntityExtractor"
    )
    priority: SignalPriority = Field(
        default=SignalPriority.P3,
        description="Priority assigned by SignalClassifier",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Classification confidence (triggers Loop 1 if < 0.5)",
    )
    category: str = Field(
        default="", description="Risk category, e.g. cyber, financial, geopolitical"
    )

    # --- Vector embedding (set after Qdrant storage) ---
    embedding: list[float] | None = Field(
        default=None, description="Embedding vector for semantic search"
    )

    # --- Metadata ---
    demo: bool = Field(
        default=False, description="True if loaded from sample data (demo mode)"
    )
