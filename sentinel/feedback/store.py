"""FeedbackStore — Qdrant-backed storage for human feedback entries.

Provides:
  save_feedback()       → persist a new FeedbackEntry
  get_feedback()        → retrieve entries from the last N days
  get_feedback_stats()  → compute rates per signal category
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

import structlog

from sentinel.config import get_settings
from sentinel.db.qdrant_client import _get_client, ensure_collection
from sentinel.models.feedback_entry import FeedbackAction, FeedbackEntry

logger = structlog.get_logger(__name__)

_VECTOR_SIZE = 3072  # matches ensure_collection default — stored by payload filter, not similarity


async def _ensure_feedback_collection() -> None:
    """Ensure the sentinel_feedback collection exists."""
    settings = get_settings()
    await ensure_collection(settings.QDRANT_FEEDBACK_COLLECTION)


async def save_feedback(
    signal_id: str,
    brief_id: str,
    action: FeedbackAction,
    signal_title: str = "",
    signal_source: str = "",
    original_priority: str = "",
    original_confidence: float = 0.0,
    note: Optional[str] = None,
    submitted_by: str = "human",
) -> FeedbackEntry:
    """Persist a new FeedbackEntry to Qdrant.

    Returns the created FeedbackEntry.
    """
    settings = get_settings()
    await _ensure_feedback_collection()

    entry = FeedbackEntry(
        signal_id=signal_id,
        brief_id=brief_id,
        action=action,
        note=note,
        signal_title=signal_title,
        signal_source=signal_source,
        original_priority=original_priority,
        original_confidence=original_confidence,
        submitted_by=submitted_by,
    )

    client = _get_client()
    from qdrant_client.models import PointStruct

    # Use a zero vector — we query by payload filter, not similarity
    dummy_vector = [0.0] * _VECTOR_SIZE

    point = PointStruct(
        id=str(uuid.uuid4()),
        vector=dummy_vector,
        payload=entry.to_payload(),
    )

    await client.upsert(
        collection_name=settings.QDRANT_FEEDBACK_COLLECTION,
        points=[point],
    )

    logger.info(
        "feedback.saved",
        signal_id=signal_id,
        action=action.value,
        source=signal_source,
    )
    return entry


async def get_feedback(days_back: int = 30) -> list[FeedbackEntry]:
    """Retrieve all FeedbackEntries from the last `days_back` days.

    Scans the entire collection and filters by created_at in Python
    (Qdrant range filter on string dates would require additional index).
    """
    settings = get_settings()
    await _ensure_feedback_collection()

    client = _get_client()
    cutoff = datetime.utcnow() - timedelta(days=days_back)

    # Scroll all points
    all_entries: list[FeedbackEntry] = []
    offset = None

    while True:
        results, next_offset = await client.scroll(
            collection_name=settings.QDRANT_FEEDBACK_COLLECTION,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        for point in results:
            payload = point.payload or {}
            try:
                entry = FeedbackEntry.from_payload(payload)
                if entry.created_at >= cutoff:
                    all_entries.append(entry)
            except Exception:
                logger.warning("feedback.parse_error", payload=payload)

        if next_offset is None:
            break
        offset = next_offset

    logger.info("feedback.retrieved", count=len(all_entries), days_back=days_back)
    return all_entries


async def get_feedback_stats(days_back: int = 30) -> dict:
    """Compute feedback statistics by action and signal source.

    Returns a dict with:
      total:              int
      by_action:          dict[str, int]
      by_source:          dict[str, dict[str, int]]
      false_positive_rate_by_source: dict[str, float]
      escalation_rate_by_source:     dict[str, float]
      acted_on_rate:      float
    """
    entries = await get_feedback(days_back=days_back)

    total = len(entries)
    by_action: dict[str, int] = {}
    by_source: dict[str, dict[str, int]] = {}

    for entry in entries:
        action_val = entry.action.value
        by_action[action_val] = by_action.get(action_val, 0) + 1

        source = entry.signal_source or "UNKNOWN"
        if source not in by_source:
            by_source[source] = {}
        by_source[source][action_val] = by_source[source].get(action_val, 0) + 1

    # Compute rates per source
    false_positive_rate: dict[str, float] = {}
    escalation_rate: dict[str, float] = {}
    for source, counts in by_source.items():
        src_total = sum(counts.values())
        if src_total > 0:
            false_positive_rate[source] = round(
                counts.get(FeedbackAction.FALSE_POSITIVE.value, 0) / src_total, 3
            )
            escalation_rate[source] = round(
                counts.get(FeedbackAction.ESCALATE.value, 0) / src_total, 3
            )
        else:
            false_positive_rate[source] = 0.0
            escalation_rate[source] = 0.0

    acted_on_rate = round(
        by_action.get(FeedbackAction.ACTED_ON.value, 0) / total, 3
    ) if total > 0 else 0.0

    return {
        "total": total,
        "by_action": by_action,
        "by_source": by_source,
        "false_positive_rate_by_source": false_positive_rate,
        "escalation_rate_by_source": escalation_rate,
        "acted_on_rate": acted_on_rate,
        "window_days": days_back,
    }


async def clear_feedback() -> int:
    """Delete all feedback entries. Returns count deleted. Testing only."""
    settings = get_settings()
    client = _get_client()
    from qdrant_client.models import Filter

    # Get all IDs first
    all_ids = []
    offset = None
    while True:
        results, next_offset = await client.scroll(
            collection_name=settings.QDRANT_FEEDBACK_COLLECTION,
            limit=100,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        all_ids.extend([str(p.id) for p in results])
        if next_offset is None:
            break
        offset = next_offset

    if all_ids:
        await client.delete(
            collection_name=settings.QDRANT_FEEDBACK_COLLECTION,
            points_selector=all_ids,
        )

    logger.info("feedback.cleared", count=len(all_ids))
    return len(all_ids)
