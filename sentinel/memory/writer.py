"""Memory writer — persist processed signals to Qdrant (Level 3).

After BriefWriter completes, the MemoryWriter node calls
write_memory_entry() for each signal to build the long-term memory store.
"""

from __future__ import annotations

from typing import Any

import structlog

from sentinel.config import settings
from sentinel.db.qdrant_client import ensure_collection, store_signal
from sentinel.models.memory_entry import MemoryEntry

logger = structlog.get_logger(__name__)


async def write_memory_entry(
    signal: Any,
    report: Any | None = None,
    route_decision: Any | None = None,
    collection_name: str | None = None,
) -> MemoryEntry:
    """Create and persist a MemoryEntry from pipeline outputs.

    Args:
        signal:          The processed Signal object.
        report:          Optional RiskReport from RiskAssessor.
        route_decision:  Optional RouteDecision from RouterAgent.
        collection_name: Qdrant collection to write to.
                         Defaults to settings.QDRANT_MEMORY_COLLECTION.
                         Level 6: pass tenant_context.memory_collection.

    Returns:
        The created MemoryEntry.
    """
    collection = collection_name or settings.QDRANT_MEMORY_COLLECTION

    # Build the memory entry from available data
    entities = []
    if hasattr(signal, "entities") and signal.entities:
        entities = [e.name for e in signal.entities]

    priority = "P3"
    if hasattr(signal, "priority"):
        priority = signal.priority.value if hasattr(signal.priority, "value") else str(signal.priority)

    source = ""
    if hasattr(signal, "source"):
        source = signal.source.value if hasattr(signal.source, "value") else str(signal.source)

    risk_score = 0.0
    company_matches: list[str] = []
    relevance_score = 0.0
    summary = ""
    outcome = ""

    if report:
        if hasattr(report, "risk_score") and report.risk_score:
            risk_score = getattr(report.risk_score, "overall", 0.0)
        if hasattr(report, "company_matches"):
            company_matches = report.company_matches or []
        if hasattr(report, "relevance_score"):
            relevance_score = report.relevance_score
        if hasattr(report, "summary"):
            summary = report.summary or ""
        if hasattr(report, "recommended_action"):
            outcome = report.recommended_action or ""

    route_path = "FULL"
    if route_decision:
        if hasattr(route_decision, "path"):
            route_path = route_decision.path.value if hasattr(route_decision.path, "value") else str(route_decision.path)
        if hasattr(route_decision, "company_matches") and not company_matches:
            company_matches = route_decision.company_matches or []
        if hasattr(route_decision, "relevance_score") and relevance_score == 0.0:
            relevance_score = route_decision.relevance_score

    entry = MemoryEntry(
        signal_id=str(signal.id),
        title=signal.title,
        summary=summary,
        entities=entities,
        priority=priority,
        risk_score=risk_score,
        route_path=route_path,
        company_matches=company_matches,
        relevance_score=relevance_score,
        source=source,
        outcome=outcome,
    )

    # Build embedding text from signal title + entities
    embedding_text = f"{signal.title} {' '.join(entities)} {signal.content or ''}"
    entry.embedding_text = embedding_text

    logger.info(
        "memory.write.start",
        signal_id=entry.signal_id,
        title=entry.title[:60],
        priority=entry.priority,
    )

    try:
        # Ensure collection exists
        await ensure_collection(collection)

        # Store in Qdrant
        await store_signal(
            signal_id=entry.id,
            text=embedding_text,
            payload=entry.to_payload(),
            collection_name=collection,
        )

        logger.info(
            "memory.write.ok",
            memory_id=entry.id,
            signal_id=entry.signal_id,
        )
    except Exception:
        logger.exception(
            "memory.write.error",
            signal_id=entry.signal_id,
        )

    return entry
