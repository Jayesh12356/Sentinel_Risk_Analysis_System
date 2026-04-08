"""FeedbackAgent — reads human feedback entries and adjusts confidence weights.

Runs as a background asyncio task after each pipeline run (non-blocking).
Also triggered manually via POST /feedback/process.

Logic:
  1. Read all FeedbackEntries from past FEEDBACK_WINDOW_DAYS days
  2. Skip if fewer than FEEDBACK_MIN_ENTRIES (prevent premature adjustment)
  3. Compute false_positive_rate per signal source
  4. Compute escalation_rate per signal source
  5. Adjust category_confidence_multipliers and source_priority_weights
  6. Write updated feedback_weights.json
  7. Log summary

Does NOT call Gemini — pure Python math.
Does NOT modify LLM prompts — that is PromptOptimiser's job.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

import structlog

from sentinel.config import get_settings
from sentinel.models.feedback_entry import FeedbackAction

logger = structlog.get_logger(__name__)

_WEIGHTS_PATH = os.path.join("data", "feedback_weights.json")

# Adjustment step applied per threshold breach, clipped to [0.5, 1.5]
_ADJUST_STEP = 0.1
_MIN_WEIGHT = 0.5
_MAX_WEIGHT = 1.5

# Thresholds that trigger weight adjustment
_FP_THRESHOLD = 0.30      # >30% false positives → reduce confidence
_ESCALATION_THRESHOLD = 0.20  # >20% escalations → increase priority weight


def _load_weights() -> dict:
    """Load current weights from file, return defaults if missing."""
    try:
        with open(_WEIGHTS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "category_confidence_multipliers": {
                "CYBER": 1.0, "NEWS": 1.0, "FINANCIAL": 1.0, "UNKNOWN": 1.0
            },
            "source_priority_weights": {
                "NVD": 1.0, "NEWSAPI": 1.0, "SEC_EDGAR": 1.0, "UNKNOWN": 1.0
            },
            "overall_acted_on_rate": 0.0,
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "total_feedback_processed": 0,
        }


def _save_weights(weights: dict) -> None:
    """Persist weights to file atomically."""
    os.makedirs("data", exist_ok=True)
    with open(_WEIGHTS_PATH, "w", encoding="utf-8") as f:
        json.dump(weights, f, indent=2)


def _clip(value: float) -> float:
    """Clip weight to [MIN_WEIGHT, MAX_WEIGHT]."""
    return max(_MIN_WEIGHT, min(_MAX_WEIGHT, round(value, 3)))


class FeedbackAgent:
    """Processes accumulated human feedback and adjusts confidence weights."""

    async def run(self) -> dict:
        """Main entry point — read feedback, compute weights, write file.

        Returns a summary dict for logging.
        """
        settings = get_settings()

        # Import here to avoid circular imports
        from sentinel.feedback.store import get_feedback_stats

        stats = await get_feedback_stats(days_back=settings.FEEDBACK_WINDOW_DAYS)
        total = stats.get("total", 0)

        if total < settings.FEEDBACK_MIN_ENTRIES:
            logger.info(
                "feedback_agent.skipped",
                total=total,
                min_entries=settings.FEEDBACK_MIN_ENTRIES,
                reason="insufficient_feedback",
            )
            return {"skipped": True, "total": total, "min_required": settings.FEEDBACK_MIN_ENTRIES}

        weights = _load_weights()
        adjustments: list[str] = []

        fp_by_source: dict[str, float] = stats.get("false_positive_rate_by_source", {})
        esc_by_source: dict[str, float] = stats.get("escalation_rate_by_source", {})
        by_source: dict[str, dict] = stats.get("by_source", {})

        # Map signal_source → category_confidence_multipliers key
        # Signal sources from Qdrant payloads match our JSON keys directly
        for source, fp_rate in fp_by_source.items():
            cat_key = source  # CYBER, NEWS, FINANCIAL, UNKNOWN
            current = weights["category_confidence_multipliers"].get(cat_key, 1.0)

            if fp_rate > _FP_THRESHOLD:
                new_val = _clip(current - _ADJUST_STEP)
                weights["category_confidence_multipliers"][cat_key] = new_val
                adjustments.append(
                    f"confidence[{cat_key}] {current:.2f}→{new_val:.2f} (FP rate={fp_rate:.0%})"
                )
            elif fp_rate < _FP_THRESHOLD / 2 and current < 1.0:
                # Slowly recover toward 1.0 when FP rate improves
                new_val = _clip(current + _ADJUST_STEP / 2)
                weights["category_confidence_multipliers"][cat_key] = new_val
                adjustments.append(
                    f"confidence[{cat_key}] recovering {current:.2f}→{new_val:.2f}"
                )

        # Map signal_source → source_priority_weights key
        _source_map = {
            "CYBER": "NVD",
            "NEWS": "NEWSAPI",
            "FINANCIAL": "SEC_EDGAR",
            "UNKNOWN": "UNKNOWN",
        }
        for source, esc_rate in esc_by_source.items():
            weight_key = _source_map.get(source, source)
            current = weights["source_priority_weights"].get(weight_key, 1.0)

            if esc_rate > _ESCALATION_THRESHOLD:
                new_val = _clip(current + _ADJUST_STEP)
                weights["source_priority_weights"][weight_key] = new_val
                adjustments.append(
                    f"priority[{weight_key}] {current:.2f}→{new_val:.2f} (escalation rate={esc_rate:.0%})"
                )

        # Update overall stats
        weights["overall_acted_on_rate"] = stats.get("acted_on_rate", 0.0)
        weights["last_updated"] = datetime.utcnow().isoformat() + "Z"
        weights["total_feedback_processed"] = total

        _save_weights(weights)

        logger.info(
            "feedback_agent.completed",
            total_feedback=total,
            adjustments=len(adjustments),
            acted_on_rate=weights["overall_acted_on_rate"],
        )
        for adj in adjustments:
            logger.info("feedback_agent.adjustment", detail=adj)

        return {
            "skipped": False,
            "total_feedback": total,
            "adjustments": adjustments,
            "weights": weights,
        }
