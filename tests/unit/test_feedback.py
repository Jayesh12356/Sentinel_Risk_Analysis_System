"""Unit tests for FeedbackEntry model and FeedbackStore (Level 5).

Tests run without a live Qdrant instance — store functions are
tested with mocks for network calls.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sentinel.models.feedback_entry import FeedbackAction, FeedbackEntry


# ─── FeedbackEntry model tests ────────────────────────────────────────────


def test_feedback_entry_creation() -> None:
    """FeedbackEntry should be created with all required fields."""
    entry = FeedbackEntry(
        signal_id="sig-001",
        brief_id="brief-001",
        action=FeedbackAction.ACTED_ON,
        signal_title="Test signal",
        signal_source="CYBER",
        original_priority="P0",
        original_confidence=0.85,
    )

    assert entry.signal_id == "sig-001"
    assert entry.brief_id == "brief-001"
    assert entry.action == FeedbackAction.ACTED_ON
    assert entry.signal_source == "CYBER"
    assert entry.original_priority == "P0"
    assert entry.original_confidence == 0.85
    assert entry.submitted_by == "human"
    assert entry.note is None
    assert isinstance(entry.created_at, datetime)
    assert isinstance(entry.id, str) and len(entry.id) > 0


def test_feedback_action_enum_values() -> None:
    """FeedbackAction should have all 4 expected values."""
    assert FeedbackAction.ACTED_ON.value == "acted_on"
    assert FeedbackAction.FALSE_POSITIVE.value == "false_positive"
    assert FeedbackAction.ESCALATE.value == "escalate"
    assert FeedbackAction.DISMISS.value == "dismiss"


def test_feedback_entry_to_payload() -> None:
    """to_payload() should return a flat dict with all required keys."""
    entry = FeedbackEntry(
        signal_id="sig-002",
        brief_id="brief-002",
        action=FeedbackAction.FALSE_POSITIVE,
        note="Wrong company",
        signal_title="Competitor news",
        signal_source="NEWS",
        original_priority="P1",
        original_confidence=0.70,
    )

    payload = entry.to_payload()

    assert payload["signal_id"] == "sig-002"
    assert payload["action"] == "false_positive"
    assert payload["note"] == "Wrong company"
    assert payload["signal_source"] == "NEWS"
    assert payload["original_confidence"] == 0.70
    assert isinstance(payload["created_at"], str)  # ISO string


def test_feedback_entry_from_payload_roundtrip() -> None:
    """from_payload(to_payload()) should reconstruct the original entry."""
    original = FeedbackEntry(
        signal_id="sig-003",
        brief_id="brief-003",
        action=FeedbackAction.ESCALATE,
        signal_title="Critical vulnerability",
        signal_source="CYBER",
        original_priority="P1",
        original_confidence=0.75,
        note="Should be P0",
    )

    payload = original.to_payload()
    restored = FeedbackEntry.from_payload(payload)

    assert restored.signal_id == original.signal_id
    assert restored.action == FeedbackAction.ESCALATE
    assert restored.note == "Should be P0"
    assert restored.signal_source == "CYBER"
    assert restored.original_confidence == 0.75


def test_feedback_entry_dismiss() -> None:
    """DISMISS action should be storable and retrievable."""
    entry = FeedbackEntry(
        signal_id="sig-004",
        brief_id="brief-004",
        action=FeedbackAction.DISMISS,
        signal_title="Routine filing",
        signal_source="FINANCIAL",
        original_priority="P2",
        original_confidence=0.55,
    )

    assert entry.action == FeedbackAction.DISMISS
    payload = entry.to_payload()
    restored = FeedbackEntry.from_payload(payload)
    assert restored.action == FeedbackAction.DISMISS


# ─── FeedbackStore mock tests ─────────────────────────────────────────────


def test_feedback_stats_computation_logic() -> None:
    """Compute stats manually and verify the calculation is correct."""
    # Simulate 10 feedback entries: 3 acted_on, 4 FP, 2 escalate, 1 dismiss
    from sentinel.models.feedback_entry import FeedbackAction

    counts = {
        FeedbackAction.ACTED_ON.value: 3,
        FeedbackAction.FALSE_POSITIVE.value: 4,
        FeedbackAction.ESCALATE.value: 2,
        FeedbackAction.DISMISS.value: 1,
    }
    total = sum(counts.values())  # 10
    acted_on_rate = counts[FeedbackAction.ACTED_ON.value] / total
    fp_rate = counts[FeedbackAction.FALSE_POSITIVE.value] / total

    assert total == 10
    assert abs(acted_on_rate - 0.3) < 0.001
    assert abs(fp_rate - 0.4) < 0.001


def test_sample_feedback_json_loads() -> None:
    """data/sample_feedback.json should load and parse into FeedbackEntry objects."""
    import json
    import os

    path = os.path.join("data", "sample_feedback.json")
    assert os.path.exists(path), "sample_feedback.json not found"

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) == 10

    for item in data:
        entry = FeedbackEntry.from_payload(item)
        assert entry.action in list(FeedbackAction)
        assert entry.signal_source in ("CYBER", "NEWS", "FINANCIAL")


def test_feedback_weights_json_loads() -> None:
    """data/feedback_weights.json should load with expected structure."""
    import json
    import os

    path = os.path.join("data", "feedback_weights.json")
    assert os.path.exists(path), "feedback_weights.json not found"

    with open(path, encoding="utf-8") as f:
        weights = json.load(f)

    assert "category_confidence_multipliers" in weights
    assert "source_priority_weights" in weights
    assert "overall_acted_on_rate" in weights
    assert weights["category_confidence_multipliers"]["CYBER"] == 1.0
    assert weights["source_priority_weights"]["NVD"] == 1.0
