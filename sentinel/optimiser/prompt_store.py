"""PromptStore — versioned prompt storage and retrieval for SENTINEL Level 4.

All agent prompts are stored in the Qdrant sentinel_prompts collection.
Prompts are loaded at runtime via get_active_prompt() and new versions
are saved by the PromptOptimiser via save_prompt_version().
"""

from __future__ import annotations

import uuid
from typing import Optional

import structlog

from sentinel.config import get_settings
from sentinel.db.qdrant_client import _get_client, ensure_collection
from sentinel.llm import client as llm
from sentinel.models.prompt_version import PromptVersion
from qdrant_client import models

logger = structlog.get_logger(__name__)

# Per-run cache so we don't hit Qdrant repeatedly for the same prompt
_prompt_cache: dict[str, str] = {}


def clear_prompt_cache() -> None:
    """Clear the per-run prompt cache (call at start of each pipeline run)."""
    _prompt_cache.clear()


async def _ensure_prompts_collection() -> str:
    """Ensure the sentinel_prompts collection exists, return its name."""
    settings = get_settings()
    collection = settings.QDRANT_PROMPTS_COLLECTION
    await ensure_collection(collection)
    return collection


async def get_active_prompt(agent_name: str, default: str = "") -> str:
    """Load the active prompt for an agent from PromptStore.

    Args:
        agent_name: Agent identifier, e.g. "BriefWriter".
        default:    Fallback prompt if store is empty.

    Returns:
        The active prompt text, or default if none found.
    """
    # Check cache first
    if agent_name in _prompt_cache:
        return _prompt_cache[agent_name]

    collection = await _ensure_prompts_collection()
    client = _get_client()

    try:
        # Scroll for active prompt matching agent_name
        result = await client.scroll(
            collection_name=collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="agent_name",
                        match=models.MatchValue(value=agent_name),
                    ),
                    models.FieldCondition(
                        key="is_active",
                        match=models.MatchValue(value=True),
                    ),
                ]
            ),
            limit=1,
            with_payload=True,
            with_vectors=False,
        )

        points, _ = result
        if points and points[0].payload:
            prompt_text = points[0].payload.get("prompt_text", default)
            _prompt_cache[agent_name] = prompt_text
            logger.info(
                "prompt_store.loaded",
                agent=agent_name,
                version=points[0].payload.get("version", "?"),
            )
            return prompt_text

    except Exception:
        logger.warning("prompt_store.load_failed", agent=agent_name, exc_info=True)

    # Fallback to default
    logger.info("prompt_store.fallback", agent=agent_name)
    _prompt_cache[agent_name] = default
    return default


async def save_prompt_version(
    agent_name: str,
    prompt_text: str,
    quality_score: Optional[float] = None,
) -> PromptVersion:
    """Save a new prompt version, deactivating all previous versions.

    Args:
        agent_name:    Agent identifier.
        prompt_text:   New prompt template text.
        quality_score: Score that triggered this optimisation (None for seed).

    Returns:
        The newly created PromptVersion.
    """
    collection = await _ensure_prompts_collection()
    client = _get_client()

    # Find current max version for this agent
    current_version = 0
    try:
        result = await client.scroll(
            collection_name=collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="agent_name",
                        match=models.MatchValue(value=agent_name),
                    ),
                ]
            ),
            limit=100,
            with_payload=True,
            with_vectors=False,
        )
        points, _ = result

        # Deactivate all existing versions
        for point in points:
            if point.payload and point.payload.get("is_active"):
                v = point.payload.get("version", 0)
                if v > current_version:
                    current_version = v
                await client.set_payload(
                    collection_name=collection,
                    payload={"is_active": False},
                    points=[point.id],
                )

    except Exception:
        logger.warning("prompt_store.deactivate_failed", agent=agent_name, exc_info=True)

    # Create new version
    new_version = current_version + 1
    pv = PromptVersion(
        agent_name=agent_name,
        version=new_version,
        prompt_text=prompt_text,
        quality_score=quality_score,
        is_active=True,
    )

    # Embed agent_name + first 500 chars of prompt for similarity search
    embed_text = f"{agent_name}: {prompt_text[:500]}"
    vector = await llm.embed(embed_text)

    await client.upsert(
        collection_name=collection,
        points=[
            models.PointStruct(
                id=pv.id,
                vector=vector,
                payload=pv.to_payload(),
            )
        ],
    )

    # Clear cache for this agent
    _prompt_cache.pop(agent_name, None)

    logger.info(
        "prompt_store.saved",
        agent=agent_name,
        version=new_version,
        score=quality_score,
    )
    return pv


async def get_prompt_history(agent_name: str) -> list[PromptVersion]:
    """Get all prompt versions for an agent, sorted by version descending.

    Args:
        agent_name: Agent identifier.

    Returns:
        List of PromptVersion objects, newest first.
    """
    collection = await _ensure_prompts_collection()
    client = _get_client()

    try:
        result = await client.scroll(
            collection_name=collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="agent_name",
                        match=models.MatchValue(value=agent_name),
                    ),
                ]
            ),
            limit=100,
            with_payload=True,
            with_vectors=False,
        )
        points, _ = result

        versions = []
        for point in points:
            if point.payload:
                versions.append(PromptVersion.from_payload(point.payload))

        # Sort by version descending
        versions.sort(key=lambda v: v.version, reverse=True)
        return versions

    except Exception:
        logger.warning("prompt_store.history_failed", agent=agent_name, exc_info=True)
        return []


async def rollback_prompt(agent_name: str, target_version: int) -> Optional[PromptVersion]:
    """Rollback to a specific prompt version.

    Deactivates all versions, then activates the target version.

    Args:
        agent_name:     Agent identifier.
        target_version: Version number to rollback to.

    Returns:
        The activated PromptVersion, or None if not found.
    """
    collection = await _ensure_prompts_collection()
    client = _get_client()

    try:
        result = await client.scroll(
            collection_name=collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="agent_name",
                        match=models.MatchValue(value=agent_name),
                    ),
                ]
            ),
            limit=100,
            with_payload=True,
            with_vectors=False,
        )
        points, _ = result

        target_point = None
        for point in points:
            # Deactivate all
            await client.set_payload(
                collection_name=collection,
                payload={"is_active": False},
                points=[point.id],
            )
            if point.payload and point.payload.get("version") == target_version:
                target_point = point

        if target_point is None:
            logger.warning("prompt_store.rollback_not_found", agent=agent_name, version=target_version)
            return None

        # Activate target
        await client.set_payload(
            collection_name=collection,
            payload={"is_active": True},
            points=[target_point.id],
        )

        # Clear cache
        _prompt_cache.pop(agent_name, None)

        pv = PromptVersion.from_payload(target_point.payload)
        pv.is_active = True
        logger.info("prompt_store.rollback", agent=agent_name, version=target_version)
        return pv

    except Exception:
        logger.exception("prompt_store.rollback_failed", agent=agent_name)
        return None
