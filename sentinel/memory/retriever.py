"""Memory retriever — semantic search over past events (Level 3).

Uses Qdrant to find similar past signals/events so agents
can provide context-aware analysis and detect recurring threats.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog
from qdrant_client import models as qmodels

from sentinel.config import settings
from sentinel.db.qdrant_client import _get_client, search
from sentinel.models.memory_entry import MemoryEntry

logger = structlog.get_logger(__name__)


async def get_relevant_memories(
    query_text: str,
    limit: int = 5,
    days_back: int = 90,
) -> list[MemoryEntry]:
    """Find past events semantically similar to query_text.

    Args:
        query_text: Natural-language query to search for.
        limit:      Max results to return.
        days_back:  Only return memories from the last N days.

    Returns:
        List of MemoryEntry objects, sorted by relevance.
    """
    collection = f"{settings.ACTIVE_TENANT}_memory"

    logger.info(
        "memory.retrieve.start",
        query=query_text[:80],
        limit=limit,
        days_back=days_back,
    )

    try:
        # Check if collection exists first
        client = _get_client()
        collections = await client.get_collections()
        existing = {c.name for c in collections.collections}
        if collection not in existing:
            logger.debug("memory.retrieve.no_collection", collection=collection)
            return []

        results = await search(
            query_text=query_text,
            limit=limit,
            collection_name=collection,
            score_threshold=0.3,
        )

        # Filter by date if needed
        cutoff = datetime.utcnow() - timedelta(days=days_back)
        entries: list[MemoryEntry] = []
        for point in results:
            payload = point.payload or {}
            created_str = payload.get("created_at", "")
            if created_str:
                try:
                    created = datetime.fromisoformat(created_str)
                    if created < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass  # Include if date can't be parsed

            entries.append(MemoryEntry.from_payload(payload))

        logger.info(
            "memory.retrieve.ok",
            total_hits=len(results),
            after_filter=len(entries),
        )
        return entries

    except Exception:
        logger.exception("memory.retrieve.error")
        return []


async def count_similar_events(
    entity_name: str,
    days_back: int = 90,
    limit: int = 20,
) -> int:
    """Count how many past events mention a specific entity.

    Used for recurring threat detection.
    """
    memories = await get_relevant_memories(
        query_text=entity_name,
        limit=limit,
        days_back=days_back,
    )
    # Filter to only those that actually mention the entity
    count = 0
    entity_lower = entity_name.lower()
    for m in memories:
        text = f"{m.title} {' '.join(m.entities)}".lower()
        if entity_lower in text:
            count += 1
    return count
