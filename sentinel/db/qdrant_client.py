"""Qdrant vector store client — ALL vector operations go through here.

Replaces LlamaIndex with direct qdrant-client calls per CONTEXT.md.
Uses sentinel/llm/client.py embed() for embedding generation.
"""

from __future__ import annotations

from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient, models
from tenacity import retry, stop_after_attempt, wait_exponential

from sentinel.config import settings
from sentinel.llm import client as llm

logger = structlog.get_logger(__name__)

_client: AsyncQdrantClient | None = None


def _get_client() -> AsyncQdrantClient:
    """Return (and lazily create) the shared async Qdrant client."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = AsyncQdrantClient(url=settings.QDRANT_URL)
    return _client


async def ensure_collection(
    collection_name: str | None = None,
    vector_size: int = 3072,
) -> None:
    """Create the collection if it does not already exist.

    Args:
        collection_name: Defaults to settings.QDRANT_COLLECTION.
        vector_size:     Dimensionality of embedding vectors.
    """
    name = collection_name or settings.QDRANT_COLLECTION
    client = _get_client()

    collections = await client.get_collections()
    existing = {c.name for c in collections.collections}

    if name not in existing:
        await client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
        )
        logger.info("qdrant.collection.created", name=name, vector_size=vector_size)
    else:
        logger.debug("qdrant.collection.exists", name=name)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=60))
async def upsert(
    point_id: str,
    vector: list[float],
    payload: dict[str, Any],
    collection_name: str | None = None,
) -> None:
    """Upsert a single point into Qdrant.

    Args:
        point_id:        Unique identifier (typically signal.id).
        vector:          Embedding vector.
        payload:         Metadata dict stored alongside the vector.
        collection_name: Defaults to settings.QDRANT_COLLECTION.
    """
    name = collection_name or settings.QDRANT_COLLECTION
    client = _get_client()

    logger.info("qdrant.upsert.start", point_id=point_id, collection=name)

    try:
        await client.upsert(
            collection_name=name,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                ),
            ],
        )
        logger.info("qdrant.upsert.ok", point_id=point_id)
    except Exception:
        logger.exception("qdrant.upsert.error", point_id=point_id)
        raise


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=60))
async def search(
    query_text: str,
    limit: int = 5,
    collection_name: str | None = None,
    score_threshold: float | None = None,
) -> list[models.ScoredPoint]:
    """Semantic search: embed the query text, then search Qdrant.

    Args:
        query_text:      Natural-language query to embed and search.
        limit:           Max number of results.
        collection_name: Defaults to settings.QDRANT_COLLECTION.
        score_threshold: Optional minimum similarity score.

    Returns:
        List of ScoredPoint results.
    """
    name = collection_name or settings.QDRANT_COLLECTION
    client = _get_client()

    logger.info("qdrant.search.start", collection=name, limit=limit)

    try:
        query_vector = await llm.embed(query_text)

        results = await client.search(
            collection_name=name,
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
        )
        logger.info("qdrant.search.ok", hits=len(results))
        return results
    except Exception:
        logger.exception("qdrant.search.error")
        raise


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=60))
async def search_by_vector(
    vector: list[float],
    limit: int = 5,
    collection_name: str | None = None,
    score_threshold: float | None = None,
) -> list[models.ScoredPoint]:
    """Search Qdrant with a pre-computed vector (skips embedding step).

    Args:
        vector:          Pre-computed embedding vector.
        limit:           Max number of results.
        collection_name: Defaults to settings.QDRANT_COLLECTION.
        score_threshold: Optional minimum similarity score.

    Returns:
        List of ScoredPoint results.
    """
    name = collection_name or settings.QDRANT_COLLECTION
    client = _get_client()

    logger.info("qdrant.search_by_vector.start", collection=name, limit=limit)

    try:
        results = await client.search(
            collection_name=name,
            query_vector=vector,
            limit=limit,
            score_threshold=score_threshold,
        )
        logger.info("qdrant.search_by_vector.ok", hits=len(results))
        return results
    except Exception:
        logger.exception("qdrant.search_by_vector.error")
        raise


async def store_signal(
    signal_id: str,
    text: str,
    payload: dict[str, Any],
    collection_name: str | None = None,
) -> list[float]:
    """Embed text via LLM client, then upsert into Qdrant.

    Convenience function combining embed() + upsert() in one call.

    Args:
        signal_id:       Unique ID for the point.
        text:            Raw text to embed.
        payload:         Metadata to store alongside the vector.
        collection_name: Defaults to settings.QDRANT_COLLECTION.

    Returns:
        The embedding vector that was stored.
    """
    logger.info("qdrant.store_signal.start", signal_id=signal_id)

    vector = await llm.embed(text)
    await upsert(
        point_id=signal_id,
        vector=vector,
        payload=payload,
        collection_name=collection_name,
    )

    logger.info("qdrant.store_signal.ok", signal_id=signal_id, dims=len(vector))
    return vector
