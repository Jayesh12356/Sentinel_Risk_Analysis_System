"""GovernanceLog — immutable append-only audit trail (Level 10).

Stores GovernanceEntry records in the sentinel_meta Qdrant collection.
Entries are write-once — never updated, never deleted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog

from sentinel.config import get_settings
from sentinel.models.governance_entry import GovernanceEntry

logger = structlog.get_logger(__name__)

# In-memory fallback store
_governance_log: list[GovernanceEntry] = []

COLLECTION_NAME = "sentinel_meta"


async def log_event(
    event_type: str,
    agent_name: str = "",
    tenant_id: str = "default",
    description: str = "",
    reasoning: str = "",
    confidence: Optional[float] = None,
    human_involved: bool = False,
    override: bool = False,
) -> GovernanceEntry:
    """Log an autonomous decision event (write-once, immutable).

    Returns the created GovernanceEntry.
    """
    entry = GovernanceEntry(
        event_type=event_type,
        agent_name=agent_name,
        tenant_id=tenant_id,
        description=description,
        reasoning=reasoning,
        confidence=confidence,
        human_involved=human_involved,
        override=override,
    )

    settings = get_settings()
    if not settings.GOVERNANCE_ENABLED:
        logger.debug("governance.disabled", event_type=event_type)
        _governance_log.append(entry)
        return entry

    try:
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.models import PointStruct
        import uuid as uuid_mod

        client = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )

        # Use a dummy vector (governance entries are not searched by similarity)
        dummy_vector = [0.0] * 768

        point = PointStruct(
            id=str(uuid_mod.uuid4()),
            vector=dummy_vector,
            payload=entry.to_payload(),
        )

        await client.upsert(
            collection_name=COLLECTION_NAME,
            points=[point],
        )
        await client.close()

        logger.info(
            "governance.logged",
            event_type=event_type,
            agent=agent_name,
            entry_id=entry.id,
        )
    except Exception as exc:
        logger.warning("governance.qdrant_failed", error=str(exc))
        # Always store in memory as fallback
        _governance_log.append(entry)

    return entry


async def get_log(
    limit: int = 100,
    event_type: Optional[str] = None,
) -> list[GovernanceEntry]:
    """Retrieve governance log entries, newest first.

    Optionally filter by event_type.
    """
    settings = get_settings()

    try:
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )

        # Build filter
        conditions = [
            FieldCondition(key="type", match=MatchValue(value="governance_entry"))
        ]
        if event_type:
            conditions.append(
                FieldCondition(key="event_type", match=MatchValue(value=event_type))
            )

        results = await client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(must=conditions),
            limit=limit,
            with_payload=True,
        )
        await client.close()

        entries = [GovernanceEntry.from_payload(p.payload) for p in results[0]]
        # Sort newest first
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries[:limit]

    except Exception as exc:
        logger.warning("governance.get_log_failed", error=str(exc))
        # Fallback to in-memory
        filtered = _governance_log
        if event_type:
            filtered = [e for e in filtered if e.event_type == event_type]
        filtered.sort(key=lambda e: e.created_at, reverse=True)
        return filtered[:limit]
