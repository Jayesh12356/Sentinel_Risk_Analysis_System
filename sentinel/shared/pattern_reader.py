"""SharedPatternReader — query cross-tenant patterns before CausalChainBuilder.

Runs before CausalChainBuilder.
Returns List[SharedPattern] injected into the pipeline state.
CausalChainBuilder uses these patterns to warn companies
about threats seen by other organisations.
"""

from __future__ import annotations

from typing import List, Optional

import structlog

from sentinel.config import get_settings
from sentinel.db.qdrant_client import search
from sentinel.models.shared_pattern import SharedPattern

logger = structlog.get_logger(__name__)

_DEFAULT_LIMIT = 3  # Number of similar patterns to retrieve per signal


async def get_relevant_patterns(
    query_text: str,
    limit: int = _DEFAULT_LIMIT,
    collection: Optional[str] = None,
) -> List[SharedPattern]:
    """Search sentinel_shared_patterns for patterns similar to a signal.

    Args:
        query_text:  Text to embed and search (e.g. signal title + entities).
        limit:       Maximum patterns to return.
        collection:  Qdrant collection (default: settings.QDRANT_SHARED_COLLECTION).

    Returns:
        List of SharedPattern objects sorted by similarity score.
    """
    settings = get_settings()
    coll = collection or settings.QDRANT_SHARED_COLLECTION

    try:
        results = await search(
            query_text=query_text,
            collection_name=coll,
            limit=limit,
        )
    except Exception as exc:
        logger.warning("shared_pattern.reader.search_failed", error=str(exc))
        return []

    patterns = []
    for hit in results:
        payload = hit.payload or {}
        try:
            pattern = SharedPattern.from_payload(payload)
            patterns.append(pattern)
        except Exception as exc:
            logger.warning("shared_pattern.reader.parse_error", error=str(exc), payload=str(payload)[:80])

    logger.info(
        "shared_pattern.reader.done",
        query_text=query_text[:60],
        patterns_found=len(patterns),
    )
    return patterns


async def get_patterns_for_signals(
    signals: list,
    limit_per_signal: int = _DEFAULT_LIMIT,
    collection: Optional[str] = None,
) -> List[SharedPattern]:
    """Retrieve relevant shared patterns for all signals in a pipeline run.

    Deduplicates by pattern.id so each pattern appears at most once
    even if multiple signals match it.
    """
    seen_ids = set()
    all_patterns = []

    for signal in signals:
        query_text = signal.title if hasattr(signal, "title") else str(signal)
        patterns = await get_relevant_patterns(query_text, limit=limit_per_signal, collection=collection)
        for p in patterns:
            if p.id not in seen_ids:
                seen_ids.add(p.id)
                all_patterns.append(p)

    logger.info(
        "shared_pattern.reader.signals_done",
        signals=len(signals),
        unique_patterns=len(all_patterns),
    )
    return all_patterns


def format_patterns_for_prompt(patterns: List[SharedPattern]) -> str:
    """Format shared patterns as a human-readable context block for LLM prompts.

    Used by CausalChainBuilder to inject cross-company intelligence.
    Returns empty string if no patterns.
    """
    if not patterns:
        return ""

    lines = [
        f"Cross-company intelligence: {len(patterns)} similar threat pattern(s) observed across other organisations:",
        "",
    ]
    for i, p in enumerate(patterns, 1):
        lines.append(
            f"  {i}. [{p.pattern_type}] Seen by {p.tenant_count} organisation(s), "
            f"{p.occurrence_count} times. Risk: {p.risk_score:.2f}. "
            f"Entities: {', '.join(p.entities[:5]) or 'none'}."
        )

    return "\n".join(lines)
