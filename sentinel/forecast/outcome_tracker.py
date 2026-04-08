"""
sentinel/forecast/outcome_tracker.py — Level 7 Predictive Risk Intelligence
Background task that resolves pending forecasts by checking if they came true.
"""
from __future__ import annotations

from datetime import datetime, timezone

import structlog

from sentinel.db import qdrant_client as db
from sentinel.forecast.store import get_forecasts, update_outcome
from sentinel.models.forecast_entry import ForecastEntry, ForecastOutcome

logger = structlog.get_logger(__name__)

# Priority ordering for "escalation" detection (lower index = higher severity)
PRIORITY_ORDER = ["P0", "P1", "P2", "P3"]


def _is_escalation(current: str, found: str) -> bool:
    """Return True if found_priority is strictly higher (more critical) than current."""
    try:
        return PRIORITY_ORDER.index(found) < PRIORITY_ORDER.index(current)
    except ValueError:
        return False


async def run(tenant_id: str) -> dict[str, int]:
    """Resolve all pending forecasts for a tenant.

    For each PENDING forecast past its horizon:
      1. Search {tenant_id}_signals for signals similar to the forecast
         that arrived AFTER forecast.created_at.
      2. If found with higher priority → CORRECT.
      3. If horizon expired without match:
           probability >= 0.6 → INCORRECT
           probability <  0.6 → EXPIRED

    Returns:
        dict with keys: resolved, correct, incorrect, expired
    """
    signals_collection = f"{tenant_id}_signals"
    now = datetime.now(timezone.utc)

    pending = await get_forecasts(tenant_id, pending_only=True, limit=500)
    resolved_count = 0
    correct_count = 0
    incorrect_count = 0
    expired_count = 0

    for forecast in pending:
        horizon_hours = forecast.horizon.hours()
        age_hours = (now - forecast.created_at).total_seconds() / 3600

        # Only attempt resolution if horizon has passed
        if age_hours < horizon_hours:
            continue

        outcome = await _resolve_forecast(
            forecast=forecast,
            signals_collection=signals_collection,
            now=now,
        )

        await update_outcome(
            forecast_id=forecast.id,
            tenant_id=tenant_id,
            outcome=outcome,
            resolved_at=now,
        )

        resolved_count += 1
        if outcome == ForecastOutcome.CORRECT:
            correct_count += 1
        elif outcome == ForecastOutcome.INCORRECT:
            incorrect_count += 1
        else:
            expired_count += 1

    logger.info(
        "forecast.outcome_tracker.done",
        tenant=tenant_id,
        resolved=resolved_count,
        correct=correct_count,
        incorrect=incorrect_count,
        expired=expired_count,
    )

    return {
        "resolved": resolved_count,
        "correct": correct_count,
        "incorrect": incorrect_count,
        "expired": expired_count,
    }


async def _resolve_forecast(
    forecast: ForecastEntry,
    signals_collection: str,
    now: datetime,
) -> ForecastOutcome:
    """Determine the outcome of a single forecast via Qdrant similarity search.

    Searches for signals similar to the forecast's embed_text that arrived
    AFTER the forecast was created and have a higher priority.
    """
    try:
        # Search signals similar to this forecast's reasoning
        embed_query = forecast.embed_text()
        hits = await db.search(
            query_text=embed_query,
            limit=10,
            collection_name=signals_collection,
            score_threshold=0.65,
        )

        for hit in hits:
            if not hit.payload:
                continue

            # Check that this signal arrived AFTER the forecast
            signal_ts_str = hit.payload.get("created_at") or hit.payload.get("timestamp")
            if not signal_ts_str:
                continue

            try:
                signal_ts = datetime.fromisoformat(signal_ts_str)
                # Normalise to UTC
                if signal_ts.tzinfo is None:
                    signal_ts = signal_ts.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            if signal_ts <= forecast.created_at:
                continue  # older signal — not relevant

            # Check priority escalation
            signal_priority = hit.payload.get("priority", "P3")
            if _is_escalation(
                current=forecast.current_priority,
                found=signal_priority,
            ):
                logger.info(
                    "forecast.resolved.correct",
                    forecast_id=forecast.id,
                    signal_id=hit.id,
                    signal_priority=signal_priority,
                )
                return ForecastOutcome.CORRECT

        # Horizon passed — no escalating signal found
        if forecast.probability >= 0.6:
            return ForecastOutcome.INCORRECT
        else:
            return ForecastOutcome.EXPIRED

    except Exception:
        logger.exception("forecast.resolve.error", forecast_id=forecast.id)
        # Default to expired on error to avoid blocking tracker
        return ForecastOutcome.EXPIRED
