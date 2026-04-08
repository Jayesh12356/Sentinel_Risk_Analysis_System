"""Unit tests for Level 8 — ActionEntry model + ActionRegistry."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from sentinel.models.action_entry import ActionEntry, ActionStatus, ActionType
from sentinel.actions.registry import (
    ActionConfig,
    DEFAULT_REGISTRY,
    load_registry,
    save_registry,
    get_enabled_actions,
)


# ── ActionEntry tests ──────────────────────────────────────────────────────

class TestActionEntry:
    """Tests for ActionEntry Pydantic model."""

    def test_create_action_entry(self):
        entry = ActionEntry(
            tenant_id="techcorp",
            signal_id="sig-001",
            action_type=ActionType.JIRA_TICKET,
            title="Create Jira ticket for CVE-2026-1234",
            confidence=0.90,
        )
        assert entry.tenant_id == "techcorp"
        assert entry.action_type == ActionType.JIRA_TICKET
        assert entry.status == ActionStatus.PENDING_APPROVAL  # default
        assert entry.confidence == 0.90
        assert entry.id  # auto-generated UUID

    def test_action_status_defaults(self):
        entry = ActionEntry(
            tenant_id="default",
            signal_id="sig-002",
            action_type=ActionType.PAGERDUTY_ALERT,
            title="Page on-call",
            confidence=0.95,
        )
        assert entry.status == ActionStatus.PENDING_APPROVAL
        assert entry.executed_at is None
        assert entry.approved_by is None
        assert entry.result is None

    def test_to_payload_roundtrip(self):
        entry = ActionEntry(
            tenant_id="retailco",
            signal_id="sig-003",
            action_type=ActionType.WEBHOOK,
            status=ActionStatus.AUTO_EXECUTED,
            title="Trigger failover webhook",
            description="Cloud failover triggered",
            payload={"url": "https://example.com/hook", "method": "POST"},
            reasoning="P0 signal with high confidence requires immediate failover",
            confidence=0.92,
        )
        payload = entry.to_payload()
        assert payload["action_type"] == "WEBHOOK"
        assert payload["status"] == "AUTO_EXECUTED"
        assert payload["confidence"] == 0.92

        restored = ActionEntry.from_payload(payload)
        assert restored.action_type == ActionType.WEBHOOK
        assert restored.status == ActionStatus.AUTO_EXECUTED
        assert restored.title == entry.title
        assert restored.confidence == entry.confidence

    def test_from_payload_string_enums(self):
        payload = {
            "id": "test-id",
            "tenant_id": "default",
            "signal_id": "sig-004",
            "action_type": "EMAIL_DRAFT",
            "status": "REPORT_ONLY",
            "title": "Draft email",
            "confidence": 0.45,
            "created_at": "2026-03-27T12:00:00",
        }
        entry = ActionEntry.from_payload(payload)
        assert entry.action_type == ActionType.EMAIL_DRAFT
        assert entry.status == ActionStatus.REPORT_ONLY

    def test_embed_text(self):
        entry = ActionEntry(
            tenant_id="default",
            signal_id="sig-005",
            action_type=ActionType.SLACK_MESSAGE,
            title="Alert security channel",
            description="Send alert to #security",
            reasoning="Critical CVE detected",
            confidence=0.88,
        )
        text = entry.embed_text()
        assert "SLACK_MESSAGE" in text
        assert "Alert security channel" in text

    def test_all_action_types_exist(self):
        expected = {"JIRA_TICKET", "PAGERDUTY_ALERT", "EMAIL_DRAFT", "WEBHOOK", "SLACK_MESSAGE", "INITIATE_NEGOTIATION"}
        actual = {t.value for t in ActionType}
        assert actual == expected

    def test_all_action_statuses_exist(self):
        expected = {
            "AUTO_EXECUTED", "PENDING_APPROVAL", "APPROVED",
            "REJECTED", "FAILED", "REPORT_ONLY",
        }
        actual = {s.value for s in ActionStatus}
        assert actual == expected


# ── ActionRegistry tests ───────────────────────────────────────────────────

class TestActionRegistry:
    """Tests for ActionRegistry load/save/filter."""

    @pytest.mark.asyncio
    async def test_load_registry_default_fallback(self):
        """When tenant file is missing, should return default registry."""
        with patch("sentinel.actions.registry.get_settings") as mock_settings:
            mock_settings.return_value.TENANTS_DIR = str(
                Path(tempfile.gettempdir()) / "nonexistent_tenants"
            )
            result = await load_registry("missing_tenant")
            assert len(result) == len(DEFAULT_REGISTRY)
            assert all(isinstance(c, ActionConfig) for c in result)

    @pytest.mark.asyncio
    async def test_load_registry_from_file(self):
        """When tenant file exists, should load from it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tenant_dir = Path(tmpdir) / "test_tenant"
            tenant_dir.mkdir()
            registry_data = [
                {"action_type": "JIRA_TICKET", "enabled": True, "auto_execute": True, "config": {}},
                {"action_type": "WEBHOOK", "enabled": False, "auto_execute": False, "config": {}},
            ]
            (tenant_dir / "action_registry.json").write_text(
                json.dumps(registry_data), encoding="utf-8"
            )
            with patch("sentinel.actions.registry.get_settings") as mock_settings:
                mock_settings.return_value.TENANTS_DIR = tmpdir
                result = await load_registry("test_tenant")
                assert len(result) == 2
                assert result[0].action_type == ActionType.JIRA_TICKET
                assert result[0].auto_execute is True

    @pytest.mark.asyncio
    async def test_save_registry(self):
        """Should write registry to JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sentinel.actions.registry.get_settings") as mock_settings:
                mock_settings.return_value.TENANTS_DIR = tmpdir
                configs = [
                    ActionConfig(
                        action_type=ActionType.PAGERDUTY_ALERT,
                        enabled=True,
                        auto_execute=True,
                        config={"severity": "critical"},
                    ),
                ]
                await save_registry("save_test", configs)
                saved_path = Path(tmpdir) / "save_test" / "action_registry.json"
                assert saved_path.exists()
                data = json.loads(saved_path.read_text(encoding="utf-8"))
                assert len(data) == 1
                assert data[0]["action_type"] == "PAGERDUTY_ALERT"

    @pytest.mark.asyncio
    async def test_get_enabled_actions(self):
        """Should filter out disabled actions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tenant_dir = Path(tmpdir) / "filter_test"
            tenant_dir.mkdir()
            registry_data = [
                {"action_type": "JIRA_TICKET", "enabled": True, "auto_execute": False, "config": {}},
                {"action_type": "WEBHOOK", "enabled": False, "auto_execute": False, "config": {}},
                {"action_type": "SLACK_MESSAGE", "enabled": True, "auto_execute": True, "config": {}},
            ]
            (tenant_dir / "action_registry.json").write_text(
                json.dumps(registry_data), encoding="utf-8"
            )
            with patch("sentinel.actions.registry.get_settings") as mock_settings:
                mock_settings.return_value.TENANTS_DIR = tmpdir
                enabled = await get_enabled_actions("filter_test")
                assert len(enabled) == 2
                types = {c.action_type for c in enabled}
                assert ActionType.JIRA_TICKET in types
                assert ActionType.SLACK_MESSAGE in types
                assert ActionType.WEBHOOK not in types
