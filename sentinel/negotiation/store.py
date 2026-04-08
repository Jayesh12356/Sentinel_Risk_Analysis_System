"""NegotiationSession store — Qdrant-backed persistence for Level 9.

Uses {tenant_id}_negotiations collection.
Falls back to in-memory store when Qdrant is unavailable.
"""

from __future__ import annotations

from typing import Optional

import structlog

from sentinel.models.negotiation import NegotiationSession, NegotiationStatus

logger = structlog.get_logger(__name__)

# In-memory fallback store (used when Qdrant is unavailable / demo mode)
_sessions: dict[str, NegotiationSession] = {}


async def save_session(session: NegotiationSession) -> NegotiationSession:
    """Save a NegotiationSession to Qdrant (or in-memory fallback)."""
    collection = f"{session.tenant_id}_negotiations"
    try:
        from sentinel.llm.client import embed
        from sentinel.db.qdrant_client import _get_client, ensure_collection
        from qdrant_client.models import PointStruct

        embed_text = session.embed_text()
        vector = await embed(embed_text)

        await ensure_collection(collection)
        client = _get_client()
        point = PointStruct(
            id=session.id,
            vector=vector,
            payload=session.to_payload(),
        )
        await client.upsert(collection_name=collection, points=[point])
        logger.info("negotiation_store.saved", session_id=session.id, collection=collection)
    except Exception as exc:
        logger.warning("negotiation_store.qdrant_fallback", error=str(exc))
        # In-memory fallback
        _sessions[session.id] = session

    return session


async def get_sessions(
    tenant_id: str = "default",
    active_only: bool = False,
    limit: int = 50,
) -> list[NegotiationSession]:
    """Retrieve negotiation sessions for a tenant."""
    try:
        from sentinel.db.qdrant_client import _get_client

        client = _get_client()
        collection = f"{tenant_id}_negotiations"

        result = await client.scroll(
            collection_name=collection,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        sessions = []
        for point in result[0]:
            session = NegotiationSession.from_payload(point.payload)
            if active_only and session.status in (
                NegotiationStatus.COMPLETE,
                NegotiationStatus.FAILED,
            ):
                continue
            sessions.append(session)
        return sessions
    except Exception as exc:
        logger.warning("negotiation_store.get_sessions_fallback", error=str(exc))
        # In-memory fallback
        return [
            s for s in _sessions.values()
            if s.tenant_id == tenant_id
            and (not active_only or s.status not in (NegotiationStatus.COMPLETE, NegotiationStatus.FAILED))
        ]


async def get_session(session_id: str) -> Optional[NegotiationSession]:
    """Retrieve a single negotiation session by ID."""
    # Try in-memory first (faster)
    if session_id in _sessions:
        return _sessions[session_id]

    try:
        from sentinel.db.qdrant_client import _get_client

        client = _get_client()
        # Try all tenant collections
        tenants = ["default", "techcorp", "retailco", "financeinc", "healthco"]
        for tid in tenants:
            collection = f"{tid}_negotiations"
            try:
                points = await client.retrieve(
                    collection_name=collection,
                    ids=[session_id],
                    with_payload=True,
                )
                if points:
                    return NegotiationSession.from_payload(points[0].payload)
            except Exception:
                continue
    except Exception as exc:
        logger.warning("negotiation_store.get_session_fallback", error=str(exc))

    return None


async def update_session(
    session_id: str,
    updates: dict,
) -> Optional[NegotiationSession]:
    """Update a negotiation session with partial data."""
    session = await get_session(session_id)
    if not session:
        logger.warning("negotiation_store.update_not_found", session_id=session_id)
        return None

    # Apply updates
    for key, value in updates.items():
        if hasattr(session, key):
            setattr(session, key, value)

    # Re-save
    return await save_session(session)
