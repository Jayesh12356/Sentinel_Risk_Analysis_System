"""AgentHealthEvent — emitted by every agent after each run (Level 10).

Collected in PipelineState as health_events: List[AgentHealthEvent].
Written to sentinel_meta after pipeline completes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class AgentHealthEvent(BaseModel):
    """Health telemetry emitted by each agent after a run."""
    agent_name: str
    tenant_id: str = "default"
    run_id: str = ""
    success: bool = True
    latency_ms: float = 0.0
    quality_score: Optional[float] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_payload(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "tenant_id": self.tenant_id,
            "run_id": self.run_id,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "quality_score": self.quality_score,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "type": "health_event",
        }


async def write_health_events(events: list[AgentHealthEvent]) -> None:
    """Persist health events to Qdrant sentinel_meta collection."""
    if not events:
        return

    from sentinel.config import get_settings

    settings = get_settings()
    if not settings.META_ENABLED:
        return

    try:
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.models import PointStruct
        import uuid

        client = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )

        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=[0.0] * 768,  # dummy — not searched by similarity
                payload=event.to_payload(),
            )
            for event in events
        ]

        await client.upsert(
            collection_name="sentinel_meta",
            points=points,
        )
        await client.close()

        logger.info("health_events.written", count=len(events))
    except Exception as exc:
        logger.warning("health_events.write_failed", error=str(exc))
