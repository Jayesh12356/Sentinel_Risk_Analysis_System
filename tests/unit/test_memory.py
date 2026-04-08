"""Unit tests for SENTINEL Level 3 memory infrastructure."""

from __future__ import annotations

import pytest
from datetime import datetime

from sentinel.models.memory_entry import MemoryEntry


class TestMemoryEntry:
    """Tests for MemoryEntry Pydantic model."""

    def test_create_minimal(self):
        """MemoryEntry can be created with just signal_id and title."""
        entry = MemoryEntry(signal_id="sig-001", title="Test Signal")
        assert entry.signal_id == "sig-001"
        assert entry.title == "Test Signal"
        assert entry.priority == "P3"
        assert entry.risk_score == 0.0
        assert entry.route_path == "FULL"
        assert entry.entities == []
        assert entry.company_matches == []
        assert entry.id  # Should auto-generate UUID

    def test_create_full(self):
        """MemoryEntry can be created with all fields."""
        entry = MemoryEntry(
            signal_id="sig-002",
            title="Apache CVE Critical",
            summary="Critical vulnerability in Apache HTTP Server",
            entities=["Apache", "CVE-2025-0001"],
            priority="P0",
            risk_score=8.5,
            route_path="FULL",
            company_matches=["tech_stack:Apache"],
            relevance_score=0.85,
            source="cyber_threat",
            outcome="Patch Apache immediately",
        )
        assert entry.priority == "P0"
        assert entry.risk_score == 8.5
        assert len(entry.entities) == 2
        assert entry.company_matches == ["tech_stack:Apache"]

    def test_to_payload(self):
        """to_payload() returns a dict suitable for Qdrant."""
        entry = MemoryEntry(
            signal_id="sig-003",
            title="Test Payload",
            entities=["Entity1"],
            priority="P1",
        )
        payload = entry.to_payload()
        assert isinstance(payload, dict)
        assert payload["signal_id"] == "sig-003"
        assert payload["title"] == "Test Payload"
        assert payload["entities"] == ["Entity1"]
        assert payload["priority"] == "P1"
        assert "created_at" in payload
        assert "embedding_text" not in payload  # excluded

    def test_from_payload(self):
        """from_payload() reconstructs a MemoryEntry from a Qdrant payload."""
        payload = {
            "id": "mem-001",
            "signal_id": "sig-004",
            "title": "From Payload",
            "summary": "Test summary",
            "entities": ["Apache"],
            "priority": "P0",
            "risk_score": 7.5,
            "route_path": "FAST",
            "company_matches": ["tech_stack:Apache"],
            "relevance_score": 0.9,
            "source": "cyber_threat",
            "outcome": "Patch now",
            "created_at": "2026-03-25T10:00:00",
        }
        entry = MemoryEntry.from_payload(payload)
        assert entry.id == "mem-001"
        assert entry.signal_id == "sig-004"
        assert entry.title == "From Payload"
        assert entry.priority == "P0"
        assert isinstance(entry.created_at, datetime)

    def test_roundtrip(self):
        """to_payload() → from_payload() preserves all data."""
        original = MemoryEntry(
            signal_id="sig-005",
            title="Roundtrip Test",
            entities=["TSMC", "Semiconductor"],
            priority="P1",
            risk_score=6.0,
            company_matches=["supplier:TSMC"],
            relevance_score=0.7,
        )
        payload = original.to_payload()
        restored = MemoryEntry.from_payload(payload)
        assert restored.signal_id == original.signal_id
        assert restored.title == original.title
        assert restored.entities == original.entities
        assert restored.priority == original.priority
        assert restored.risk_score == original.risk_score
        assert restored.company_matches == original.company_matches

    def test_id_auto_generated(self):
        """Each MemoryEntry gets a unique auto-generated id."""
        e1 = MemoryEntry(signal_id="s1", title="First")
        e2 = MemoryEntry(signal_id="s2", title="Second")
        assert e1.id != e2.id

    def test_created_at_default(self):
        """created_at defaults to approximately now."""
        entry = MemoryEntry(signal_id="s1", title="Time Test")
        assert isinstance(entry.created_at, datetime)
        diff = (datetime.utcnow() - entry.created_at).total_seconds()
        assert diff < 5  # Within 5 seconds
