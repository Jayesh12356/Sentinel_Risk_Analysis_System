"""
tests/unit/test_forecast.py — Level 7 Predictive Risk Intelligence
Unit tests for ForecastEntry model and ForecastStore operations.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sentinel.models.forecast_entry import (
    ForecastEntry,
    ForecastHorizon,
    ForecastOutcome,
)


# ── ForecastEntry creation and serialisation ─────────────────────────────────

class TestForecastEntry:
    def test_create_defaults(self):
        entry = ForecastEntry(
            tenant_id="techcorp",
            signal_id="sig-123",
            signal_title="Critical CVE in OpenSSL",
            current_priority="P2",
            predicted_priority="P0",
            probability=0.85,
            reasoning="Historical pattern matches previous Log4Shell escalation.",
        )
        assert entry.tenant_id == "techcorp"
        assert entry.outcome == ForecastOutcome.PENDING
        assert entry.horizon == ForecastHorizon.H72
        assert entry.evidence == []
        assert entry.resolved_at is None
        assert entry.id  # UUID assigned

    def test_create_with_all_fields(self):
        entry = ForecastEntry(
            tenant_id="retailco",
            signal_id="sig-456",
            signal_title="Supply chain disruption",
            signal_category="FINANCIAL",
            current_priority="P3",
            predicted_priority="P1",
            probability=0.60,
            horizon=ForecastHorizon.H24,
            reasoning="3PL partner breach detected in shared patterns.",
            evidence=["pattern_1", "pattern_2"],
        )
        assert entry.horizon == ForecastHorizon.H24
        assert entry.signal_category == "FINANCIAL"
        assert len(entry.evidence) == 2

    def test_horizon_hours(self):
        assert ForecastHorizon.H24.hours() == 24
        assert ForecastHorizon.H48.hours() == 48
        assert ForecastHorizon.H72.hours() == 72
        assert ForecastHorizon.H7D.hours() == 168

    def test_to_payload_roundtrip(self):
        entry = ForecastEntry(
            tenant_id="techcorp",
            signal_id="sig-789",
            signal_title="Zero-day exploit",
            current_priority="P2",
            predicted_priority="P0",
            probability=0.90,
            reasoning="Rapid CVE reference growth detected.",
            evidence=["hist-1", "hist-2"],
        )
        payload = entry.to_payload()
        restored = ForecastEntry.from_payload(payload)

        assert restored.id == entry.id
        assert restored.tenant_id == entry.tenant_id
        assert restored.signal_id == entry.signal_id
        assert restored.probability == entry.probability
        assert restored.horizon == entry.horizon
        assert restored.outcome == ForecastOutcome.PENDING
        assert restored.evidence == entry.evidence
        assert restored.resolved_at is None

    def test_to_payload_with_resolved(self):
        now = datetime.now(timezone.utc)
        entry = ForecastEntry(
            tenant_id="techcorp",
            signal_id="sig-resolved",
            signal_title="Resolved signal",
            current_priority="P2",
            predicted_priority="P0",
            probability=0.75,
            reasoning="Test.",
            outcome=ForecastOutcome.CORRECT,
            resolved_at=now,
        )
        payload = entry.to_payload()
        assert payload["outcome"] == "CORRECT"
        assert payload["resolved_at"] is not None

        restored = ForecastEntry.from_payload(payload)
        assert restored.outcome == ForecastOutcome.CORRECT
        assert restored.resolved_at is not None

    def test_embed_text(self):
        entry = ForecastEntry(
            tenant_id="techcorp",
            signal_id="sig-embed",
            signal_title="Log4Shell escalation",
            current_priority="P2",
            predicted_priority="P0",
            probability=0.88,
            reasoning="Matches known exploit pattern.",
        )
        text = entry.embed_text()
        assert "Log4Shell escalation" in text
        assert "Matches known exploit pattern" in text


# ── ForecastStore — mocked Qdrant operations ─────────────────────────────────

class TestForecastStore:
    def _make_entry(self, probability: float = 0.75, outcome: ForecastOutcome = ForecastOutcome.PENDING) -> ForecastEntry:
        return ForecastEntry(
            tenant_id="techcorp",
            signal_id="sig-store",
            signal_title="Store test signal",
            current_priority="P2",
            predicted_priority="P0",
            probability=probability,
            reasoning="Store test reasoning.",
            outcome=outcome,
        )

    @pytest.mark.asyncio
    async def test_save_forecast(self):
        entry = self._make_entry()
        with patch("sentinel.forecast.store.db.store_signal", new_callable=AsyncMock) as mock_store:
            from sentinel.forecast.store import save_forecast
            result = await save_forecast(entry)
            assert result.id == entry.id
            mock_store.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_accuracy_zero_resolved(self):
        """get_accuracy must not raise ZeroDivisionError with no resolved forecasts."""
        from sentinel.forecast.store import get_accuracy

        with patch("sentinel.forecast.store.get_forecasts", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [self._make_entry(outcome=ForecastOutcome.PENDING)]
            result = await get_accuracy("techcorp")

        assert result["rate"] == 0.0
        assert result["total"] == 1
        assert result["correct"] == 0
        assert result["incorrect"] == 0

    @pytest.mark.asyncio
    async def test_get_accuracy_with_resolved(self):
        """get_accuracy computes rate = correct / (correct + incorrect)."""
        from sentinel.forecast.store import get_accuracy

        entries = [
            self._make_entry(outcome=ForecastOutcome.CORRECT),
            self._make_entry(outcome=ForecastOutcome.CORRECT),
            self._make_entry(outcome=ForecastOutcome.INCORRECT),
        ]

        with patch("sentinel.forecast.store.get_forecasts", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = entries
            result = await get_accuracy("techcorp")

        assert result["correct"] == 2
        assert result["incorrect"] == 1
        assert abs(result["rate"] - 0.667) < 0.001

    @pytest.mark.asyncio
    async def test_update_outcome_changes_status(self):
        """update_outcome retrieves, mutates, and re-upserts the entry."""
        entry = self._make_entry()
        mock_point = MagicMock()
        mock_point.payload = entry.to_payload()

        now = datetime.now(timezone.utc)

        with (
            patch("sentinel.forecast.store.db._get_client") as mock_client_factory,
            patch("sentinel.forecast.store.db.upsert", new_callable=AsyncMock) as mock_upsert,
        ):
            mock_client = AsyncMock()
            mock_client.retrieve = AsyncMock(return_value=[mock_point])
            mock_client_factory.return_value = mock_client

            from sentinel.forecast.store import update_outcome
            updated = await update_outcome(
                forecast_id=entry.id,
                tenant_id="techcorp",
                outcome=ForecastOutcome.CORRECT,
                resolved_at=now,
            )

        assert updated is not None
        assert updated.outcome == ForecastOutcome.CORRECT
        assert updated.resolved_at is not None
        mock_upsert.assert_called_once()
