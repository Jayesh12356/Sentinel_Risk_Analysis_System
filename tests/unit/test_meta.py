"""Unit tests for Level 10 — MetaReport, GovernanceEntry, GovernanceLog."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

import pytest

from sentinel.models.meta_report import (
    AgentHealthScore,
    DebateBalance,
    ActionEffectiveness,
    MetaReport,
)
from sentinel.models.governance_entry import GovernanceEntry


# ── MetaReport tests ──────────────────────────────────────────────────────

class TestMetaReport:
    """Tests for MetaReport Pydantic model."""

    def test_agent_health_score_creation(self):
        ahs = AgentHealthScore(
            agent_name="RiskAssessor",
            run_count=50,
            avg_quality_score=0.85,
            error_rate=0.02,
            avg_latency_ms=150.0,
            trend="IMPROVING",
            issues=["Occasional timeout on large signals"],
        )
        assert ahs.agent_name == "RiskAssessor"
        assert ahs.trend == "IMPROVING"
        assert len(ahs.issues) == 1

    def test_debate_balance_defaults(self):
        db = DebateBalance()
        assert db.red_team_win_rate == 0.5
        assert db.balance_status == "BALANCED"

    def test_action_effectiveness_defaults(self):
        ae = ActionEffectiveness()
        assert ae.total_actions == 0
        assert ae.effectiveness_score == 0.0

    def test_meta_report_creation(self):
        report = MetaReport(
            runs_analysed=25,
            overall_health=0.87,
            critical_issues=["Debate balance RED_DOMINANT"],
            recommendations=["Rewrite BlueTeam prompt"],
        )
        assert report.id  # auto-generated
        assert report.runs_analysed == 25
        assert report.overall_health == 0.87
        assert len(report.critical_issues) == 1

    def test_meta_report_with_agent_health(self):
        report = MetaReport(
            runs_analysed=10,
            agent_health=[
                AgentHealthScore(agent_name="RedTeam", run_count=10, avg_quality_score=0.9),
                AgentHealthScore(agent_name="BlueTeam", run_count=10, avg_quality_score=0.7),
            ],
            debate_balance=DebateBalance(
                red_team_win_rate=0.7,
                blue_team_win_rate=0.3,
                balance_status="RED_DOMINANT",
            ),
        )
        assert len(report.agent_health) == 2
        assert report.debate_balance.balance_status == "RED_DOMINANT"

    def test_meta_report_to_payload_roundtrip(self):
        report = MetaReport(
            runs_analysed=15,
            overall_health=0.92,
            agent_health=[
                AgentHealthScore(agent_name="QualityAgent", run_count=15, avg_quality_score=0.88),
            ],
            debate_balance=DebateBalance(red_team_win_rate=0.55, blue_team_win_rate=0.45, balance_status="BALANCED"),
            action_effectiveness=ActionEffectiveness(total_actions=30, approval_rate=0.8),
            critical_issues=[],
            recommendations=["Continue current configuration"],
        )
        payload = report.to_payload()
        assert payload["type"] == "meta_report"
        assert payload["runs_analysed"] == 15

        restored = MetaReport.from_payload(payload)
        assert restored.runs_analysed == 15
        assert restored.overall_health == 0.92
        assert len(restored.agent_health) == 1
        assert restored.agent_health[0].agent_name == "QualityAgent"
        assert restored.debate_balance.balance_status == "BALANCED"


# ── GovernanceEntry tests ──────────────────────────────────────────────────

class TestGovernanceEntry:
    """Tests for GovernanceEntry Pydantic model."""

    def test_governance_entry_creation(self):
        entry = GovernanceEntry(
            event_type="ACTION_EXECUTED",
            agent_name="ActionPlanner",
            tenant_id="techcorp",
            description="Auto-executed JIRA_TICKET for CVE-2026-1234",
            reasoning="P0 signal with confidence 0.95 exceeds threshold",
            confidence=0.95,
        )
        assert entry.event_type == "ACTION_EXECUTED"
        assert entry.confidence == 0.95
        assert entry.human_involved is False
        assert entry.override is False

    def test_governance_entry_to_payload_roundtrip(self):
        entry = GovernanceEntry(
            event_type="PROMPT_CHANGED",
            agent_name="PromptOptimiser",
            tenant_id="default",
            description="Updated RiskAssessor prompt v3 -> v4",
            reasoning="Quality score improved from 0.82 to 0.90",
        )
        payload = entry.to_payload()
        assert payload["type"] == "governance_entry"
        assert payload["event_type"] == "PROMPT_CHANGED"

        restored = GovernanceEntry.from_payload(payload)
        assert restored.event_type == "PROMPT_CHANGED"
        assert restored.agent_name == "PromptOptimiser"
        assert restored.description == entry.description

    def test_governance_entry_embed_text(self):
        entry = GovernanceEntry(
            event_type="OVERRIDE_APPLIED",
            agent_name="ActionPlanner",
            description="Global override halted all autonomous actions",
            reasoning="Manual safety pause",
        )
        text = entry.embed_text()
        assert "OVERRIDE_APPLIED" in text
        assert "ActionPlanner" in text

    def test_all_event_types(self):
        """Verify all expected event types can be used."""
        event_types = [
            "ACTION_EXECUTED", "PROMPT_CHANGED", "WEIGHT_ADJUSTED",
            "NEGOTIATION_STARTED", "OVERRIDE_APPLIED", "AB_TEST_RESULT",
            "META_REPORT_GENERATED",
        ]
        for et in event_types:
            entry = GovernanceEntry(event_type=et)
            assert entry.event_type == et


# ── GovernanceLog tests ───────────────────────────────────────────────────

class TestGovernanceLog:
    """Tests for GovernanceLog store functions."""

    @pytest.mark.asyncio
    async def test_log_event_fallback(self):
        """Log event falls back to in-memory when Qdrant unavailable."""
        from sentinel.meta import governance

        # Clear in-memory log
        governance._governance_log.clear()

        with patch("sentinel.meta.governance.get_settings") as mock_settings:
            mock_settings.return_value.GOVERNANCE_ENABLED = True
            mock_settings.return_value.QDRANT_HOST = "nonexistent-host"
            mock_settings.return_value.QDRANT_PORT = 6333

            entry = await governance.log_event(
                event_type="ACTION_EXECUTED",
                agent_name="TestAgent",
                description="Test log entry",
            )
            assert entry.event_type == "ACTION_EXECUTED"
            assert len(governance._governance_log) >= 1

    @pytest.mark.asyncio
    async def test_get_log_fallback(self):
        """Get log falls back to in-memory when Qdrant unavailable."""
        from sentinel.meta import governance

        governance._governance_log.clear()

        # Add test entries
        governance._governance_log.append(
            GovernanceEntry(event_type="A", description="first")
        )
        governance._governance_log.append(
            GovernanceEntry(event_type="B", description="second")
        )
        governance._governance_log.append(
            GovernanceEntry(event_type="A", description="third")
        )

        with patch("sentinel.meta.governance.get_settings") as mock_settings:
            mock_settings.return_value.GOVERNANCE_ENABLED = True
            mock_settings.return_value.QDRANT_HOST = "nonexistent-host"
            mock_settings.return_value.QDRANT_PORT = 6333

            # Get all
            entries = await governance.get_log(limit=10)
            assert len(entries) == 3

            # Filter by type
            a_entries = await governance.get_log(limit=10, event_type="A")
            assert len(a_entries) == 2
            assert all(e.event_type == "A" for e in a_entries)

    @pytest.mark.asyncio
    async def test_log_event_disabled(self):
        """When governance disabled, entry still stored in memory."""
        from sentinel.meta import governance

        governance._governance_log.clear()

        with patch("sentinel.meta.governance.get_settings") as mock_settings:
            mock_settings.return_value.GOVERNANCE_ENABLED = False

            entry = await governance.log_event(
                event_type="WEIGHT_ADJUSTED",
                description="Should still be in memory",
            )
            assert entry.event_type == "WEIGHT_ADJUSTED"
            assert len(governance._governance_log) == 1
