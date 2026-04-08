"""
sentinel/forecast/store.py — Level 7 Predictive Risk Intelligence
Qdrant-backed storage for ForecastEntry records.

All public functions are async. Uses {tenant_id}_forecasts collection.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from qdrant_client import models as qdrant_models

from sentinel.db import qdrant_client as db
from sentinel.models.forecast_entry import ForecastEntry, ForecastOutcome

logger = structlog.get_logger(__name__)


def _collection(tenant_id: str) -> str:
    return f"{tenant_id}_forecasts"


async def save_forecast(entry: ForecastEntry) -> ForecastEntry:
    """Embed and upsert a ForecastEntry into the tenant forecast collection.

    Returns the entry unchanged (convenience for chaining).
    """
    collection = _collection(entry.tenant_id)
    embed_text = entry.embed_text()

    try:
        await db.store_signal(
            signal_id=entry.id,
            text=embed_text,
            payload=entry.to_payload(),
            collection_name=collection,
        )
        logger.info(
            "forecast.save.ok",
            forecast_id=entry.id,
            tenant=entry.tenant_id,
            probability=entry.probability,
        )
    except Exception:
        logger.exception("forecast.save.error", forecast_id=entry.id)
        raise

    return entry


async def get_forecasts(
    tenant_id: str,
    pending_only: bool = False,
    limit: int = 50,
) -> list[ForecastEntry]:
    """Retrieve forecasts for a tenant.

    Args:
        tenant_id:    Tenant whose forecasts to retrieve.
        pending_only: If True, only return PENDING forecasts.
        limit:        Maximum number to return.

    Returns:
        List of ForecastEntry objects sorted by probability descending.
    """
    collection = _collection(tenant_id)
    client = db._get_client()

    try:
        scroll_filter: qdrant_models.Filter | None = None
        if pending_only:
            scroll_filter = qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="outcome",
                        match=qdrant_models.MatchValue(value="PENDING"),
                    )
                ]
            )

        results, _ = await client.scroll(
            collection_name=collection,
            scroll_filter=scroll_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        entries = [ForecastEntry.from_payload(r.payload) for r in results if r.payload]
        # Sort by probability descending
        entries.sort(key=lambda e: e.probability, reverse=True)
        logger.info("forecast.get.ok", tenant=tenant_id, count=len(entries))
        return entries

    except Exception:
        logger.exception("forecast.get.error", tenant=tenant_id)
        return []


async def get_accuracy(tenant_id: str) -> dict[str, Any]:
    """Return accuracy metrics for a tenant's resolved forecasts.

    Returns:
        dict with keys: total, correct, incorrect, expired, pending, rate
        rate is 0.0 if no resolved forecasts (zero-division-safe).
    """
    all_forecasts = await get_forecasts(tenant_id, pending_only=False, limit=1000)

    total = len(all_forecasts)
    correct = sum(1 for f in all_forecasts if f.outcome == ForecastOutcome.CORRECT)
    incorrect = sum(1 for f in all_forecasts if f.outcome == ForecastOutcome.INCORRECT)
    expired = sum(1 for f in all_forecasts if f.outcome == ForecastOutcome.EXPIRED)
    pending = sum(1 for f in all_forecasts if f.outcome == ForecastOutcome.PENDING)

    resolved = correct + incorrect
    rate = round(correct / resolved, 3) if resolved > 0 else 0.0

    # Per-category accuracy
    by_category: dict[str, dict[str, int]] = {}
    for f in all_forecasts:
        cat = f.signal_category
        if cat not in by_category:
            by_category[cat] = {"correct": 0, "incorrect": 0}
        if f.outcome == ForecastOutcome.CORRECT:
            by_category[cat]["correct"] += 1
        elif f.outcome == ForecastOutcome.INCORRECT:
            by_category[cat]["incorrect"] += 1

    category_rates = {}
    for cat, counts in by_category.items():
        res = counts["correct"] + counts["incorrect"]
        category_rates[cat] = round(counts["correct"] / res, 3) if res > 0 else 0.0

    return {
        "tenant_id": tenant_id,
        "total": total,
        "correct": correct,
        "incorrect": incorrect,
        "expired": expired,
        "pending": pending,
        "rate": rate,
        "by_category": category_rates,
    }


async def update_outcome(
    forecast_id: str,
    tenant_id: str,
    outcome: ForecastOutcome,
    resolved_at: datetime | None = None,
) -> ForecastEntry | None:
    """Update the outcome of a specific forecast.

    Fetches the existing entry, mutates outcome + resolved_at,
    then re-upserts into Qdrant.

    Returns the updated ForecastEntry, or None if not found.
    """
    collection = _collection(tenant_id)
    client = db._get_client()

    try:
        results = await client.retrieve(
            collection_name=collection,
            ids=[forecast_id],
            with_payload=True,
            with_vectors=False,
        )
        if not results:
            logger.warning("forecast.update.not_found", forecast_id=forecast_id)
            return None

        entry = ForecastEntry.from_payload(results[0].payload)
        entry.outcome = outcome
        entry.resolved_at = resolved_at or datetime.now(timezone.utc)

        await db.upsert(
            point_id=entry.id,
            vector=[0.0],  # dummy — vector unchanged, payload-only update
            payload=entry.to_payload(),
            collection_name=collection,
        )

        logger.info(
            "forecast.update.ok",
            forecast_id=forecast_id,
            outcome=outcome.value,
        )
        return entry

    except Exception:
        logger.exception("forecast.update.error", forecast_id=forecast_id)
        return None


async def get_forecast_by_signal(
    tenant_id: str,
    signal_id: str,
) -> ForecastEntry | None:
    """Return the most recent forecast for a given signal_id."""
    collection = _collection(tenant_id)
    client = db._get_client()

    try:
        results, _ = await client.scroll(
            collection_name=collection,
            scroll_filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="signal_id",
                        match=qdrant_models.MatchValue(value=signal_id),
                    )
                ]
            ),
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        if results and results[0].payload:
            return ForecastEntry.from_payload(results[0].payload)
        return None
    except Exception:
        logger.exception("forecast.get_by_signal.error", signal_id=signal_id)
        return None
