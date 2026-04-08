"""Feedback weights loader — reads feedback_weights.json with 60s TTL cache.

Used by SignalClassifier and ArbiterAgent at the start of each run
to apply human-driven confidence adjustments without re-reading the
file for every single signal.
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

_WEIGHTS_PATH = os.path.join("data", "feedback_weights.json")
_CACHE_TTL_SECONDS = 60

_cached_weights: Optional[dict] = None
_cache_timestamp: float = 0.0

_DEFAULT_WEIGHTS = {
    "category_confidence_multipliers": {
        "CYBER": 1.0,
        "NEWS": 1.0,
        "FINANCIAL": 1.0,
        "UNKNOWN": 1.0,
    },
    "source_priority_weights": {
        "NVD": 1.0,
        "NEWSAPI": 1.0,
        "SEC_EDGAR": 1.0,
        "UNKNOWN": 1.0,
    },
    "overall_acted_on_rate": 0.0,
}


def load_weights() -> dict:
    """Load feedback_weights.json with 60s TTL in-process cache.

    Returns default weights (all 1.0) if file does not exist.
    Never raises — always returns a usable dict.
    """
    global _cached_weights, _cache_timestamp

    now = time.monotonic()
    if _cached_weights is not None and (now - _cache_timestamp) < _CACHE_TTL_SECONDS:
        return _cached_weights

    try:
        with open(_WEIGHTS_PATH, encoding="utf-8") as f:
            weights = json.load(f)
        _cached_weights = weights
        _cache_timestamp = now
        logger.debug("feedback_weights.loaded", path=_WEIGHTS_PATH)
        return weights
    except FileNotFoundError:
        logger.debug("feedback_weights.not_found", path=_WEIGHTS_PATH, using="defaults")
        return dict(_DEFAULT_WEIGHTS)
    except json.JSONDecodeError as exc:
        logger.warning("feedback_weights.parse_error", error=str(exc), using="defaults")
        return dict(_DEFAULT_WEIGHTS)


def get_confidence_multiplier(signal_source: str) -> float:
    """Return the confidence multiplier for a given signal source category.

    Args:
        signal_source: "CYBER", "NEWS", "FINANCIAL", or "UNKNOWN"

    Returns:
        Float multiplier in [0.5, 1.5], default 1.0
    """
    weights = load_weights()
    multipliers: dict = weights.get("category_confidence_multipliers", {})
    return float(multipliers.get(signal_source.upper(), 1.0))


def get_priority_weight(signal_source: str) -> float:
    """Return the priority weight for a given signal source category.

    Maps: CYBER→NVD, NEWS→NEWSAPI, FINANCIAL→SEC_EDGAR, else→UNKNOWN

    Returns:
        Float weight in [0.5, 1.5], default 1.0
    """
    _source_map = {
        "CYBER": "NVD",
        "NEWS": "NEWSAPI",
        "FINANCIAL": "SEC_EDGAR",
    }
    weights = load_weights()
    priority_weights: dict = weights.get("source_priority_weights", {})
    key = _source_map.get(signal_source.upper(), "UNKNOWN")
    return float(priority_weights.get(key, 1.0))


def invalidate_cache() -> None:
    """Force next call to load_weights() to re-read from disk."""
    global _cached_weights, _cache_timestamp
    _cached_weights = None
    _cache_timestamp = 0.0
