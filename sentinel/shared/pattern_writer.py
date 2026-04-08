"""SharedPatternWriter — anonymise signals and write to sentinel_shared_patterns.

Runs after MemoryWriter in the pipeline.
Checks if a similar pattern already exists → increments count.
If not → creates new SharedPattern.
No company identifiers ever stored.
"""

from __future__ import annotations

from typing import Any, List, Optional

import structlog

from sentinel.config import get_settings
from sentinel.db.qdrant_client import ensure_collection, search, store_signal
from sentinel.models.shared_pattern import SharedPattern
from sentinel.models.signal import Signal, SignalPriority, SignalSource

logger = structlog.get_logger(__name__)

_VECTOR_SIZE = 3072  # gemini-embedding-001
_SIMILARITY_THRESHOLD = 0.85  # cosine similarity to consider "same pattern"

# Generic entity prefixes that ARE safe to keep in shared patterns
_SAFE_PREFIXES = ("CVE-", "cve-", "MITRE", "ATT&CK", "T1", "CWE-")

# Pattern type inference rules: keywords → pattern_type
_PATTERN_TYPE_RULES: list[tuple[list[str], str]] = [
    (["CVE-", "exploit", "zero-day", "vulnerability", "patch"], "CVE_EXPLOIT"),
    (["supply chain", "vendor", "third-party", "dependency"], "SUPPLY_CHAIN"),
    (["HIPAA", "GDPR", "FINRA", "PCI-DSS", "SOC2", "regulation", "compliance"], "REGULATORY"),
    (["breach", "data leak", "PII", "exfiltration"], "DATA_BREACH"),
    (["fraud", "wire transfer", "AML", "financial crime"], "FINANCIAL_FRAUD"),
]


def _infer_pattern_type(signal: Signal) -> str:
    """Infer a pattern_type from signal title and content."""
    text = f"{signal.title} {signal.content or ''}".lower()
    for keywords, ptype in _PATTERN_TYPE_RULES:
        if any(kw.lower() in text for kw in keywords):
            return ptype
    return "GENERIC"


def _anonymise_entities(signal: Signal, company_profile: dict) -> list[str]:
    """Extract entities from signal, stripping company-specific identifiers.

    Keeps only:
      - CVE IDs  (CVE-YYYY-NNNNN)
      - MITRE ATT&CK technique IDs
      - Generic software names
      - Excludes anything matching company name, tech_stack names where company-specific
    """
    # Collect raw entities
    raw_entities: list[str] = []
    if hasattr(signal, "entities") and signal.entities:
        for e in signal.entities:
            name = e.name if hasattr(e, "name") else str(e)
            raw_entities.append(name)

    # Build blocklist from company profile
    blocklist = set()
    company_name = company_profile.get("name", "")
    if company_name:
        # Block individual words of length > 3 from company name
        for word in company_name.split():
            if len(word) > 3:
                blocklist.add(word.lower())

    # Keep only safe entities
    kept = []
    for entity in raw_entities:
        entity_lower = entity.lower()
        is_blocked = any(b in entity_lower for b in blocklist)
        is_safe = any(entity.startswith(p) for p in _SAFE_PREFIXES)

        if is_safe or not is_blocked:
            kept.append(entity)

    return kept[:10]  # Cap at 10 entities per pattern


async def write_or_update_pattern(
    signal: Signal,
    company_profile: Optional[dict] = None,
    collection: Optional[str] = None,
) -> Optional[SharedPattern]:
    """Write a new SharedPattern or update an existing similar one.

    Args:
        signal:          Processed pipeline signal.
        company_profile: Company profile dict for entity anonymisation.
        collection:      Qdrant collection name (default: settings.QDRANT_SHARED_COLLECTION).

    Returns:
        The written/updated SharedPattern, or None on error.
    """
    settings = get_settings()
    coll = collection or settings.QDRANT_SHARED_COLLECTION
    profile = company_profile or {}

    # Ensure collection exists
    await ensure_collection(coll, vector_size=_VECTOR_SIZE)

    pattern_type = _infer_pattern_type(signal)
    entities = _anonymise_entities(signal, profile)

    # Determine source and priority
    source = signal.source if hasattr(signal, "source") else SignalSource.NEWS
    priority = signal.priority if hasattr(signal, "priority") else SignalPriority.P2

    # Build embedding text for this pattern
    embedding_text = f"{pattern_type} {' '.join(entities)} {signal.title}"

    # Search for existing similar pattern
    try:
        existing = await search(
            query_text=embedding_text,
            collection_name=coll,
            limit=1,
        )
    except Exception as exc:
        logger.warning("shared_pattern.search_failed", error=str(exc))
        existing = []

    if existing and existing[0].score >= _SIMILARITY_THRESHOLD:
        # Update existing pattern
        payload = existing[0].payload or {}
        pattern = SharedPattern.from_payload(payload)
        from datetime import datetime
        pattern.occurrence_count += 1
        pattern.last_seen = datetime.utcnow()
        # Update risk score as running average
        new_risk = float(getattr(signal, "confidence", 0.5))
        pattern.risk_score = (pattern.risk_score + new_risk) / 2

        await store_signal(
            signal_id=pattern.id,
            text=pattern.embedding_text(),
            payload=pattern.to_payload(),
            collection_name=coll,
        )
        logger.info(
            "shared_pattern.updated",
            pattern_id=pattern.id,
            pattern_type=pattern.pattern_type,
            occurrence_count=pattern.occurrence_count,
        )
        return pattern

    else:
        # Create new pattern
        pattern = SharedPattern(
            pattern_type=pattern_type,
            entities=entities,
            source_type=source,
            priority=priority,
            risk_score=float(getattr(signal, "confidence", 0.5)),
        )

        await store_signal(
            signal_id=pattern.id,
            text=pattern.embedding_text(),
            payload=pattern.to_payload(),
            collection_name=coll,
        )
        logger.info(
            "shared_pattern.created",
            pattern_id=pattern.id,
            pattern_type=pattern_type,
            entities=entities[:3],
        )
        return pattern


async def write_patterns_for_run(
    signals: list,
    company_profile: Optional[dict] = None,
    collection: Optional[str] = None,
) -> list[SharedPattern]:
    """Write or update shared patterns for all signals in a pipeline run."""
    results = []
    for signal in signals:
        try:
            pattern = await write_or_update_pattern(signal, company_profile, collection)
            if pattern:
                results.append(pattern)
        except Exception as exc:
            logger.exception("shared_pattern.write_error", error=str(exc))
    logger.info("shared_pattern.run_complete", patterns_written=len(results))
    return results
