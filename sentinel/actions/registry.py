"""ActionRegistry — per-tenant action configuration (Level 8).

Each tenant has an action_registry.json that defines which action types
are enabled and whether they can auto-execute.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from pydantic import BaseModel, Field

from sentinel.config import get_settings
from sentinel.models.action_entry import ActionType

logger = structlog.get_logger()

# Default registry used when tenant file is missing
DEFAULT_REGISTRY: List[Dict[str, Any]] = [
    {
        "action_type": "PAGERDUTY_ALERT",
        "enabled": True,
        "auto_execute": True,
        "config": {"severity": "critical", "component": "sentinel"},
    },
    {
        "action_type": "SLACK_MESSAGE",
        "enabled": True,
        "auto_execute": True,
        "config": {"channel": "#security-alerts"},
    },
    {
        "action_type": "JIRA_TICKET",
        "enabled": True,
        "auto_execute": False,
        "config": {"issue_type": "Bug", "priority": "High"},
    },
    {
        "action_type": "EMAIL_DRAFT",
        "enabled": True,
        "auto_execute": False,
        "config": {"template": "incident_notification"},
    },
    {
        "action_type": "WEBHOOK",
        "enabled": False,
        "auto_execute": False,
        "config": {},
    },
]


class ActionConfig(BaseModel):
    """Configuration for a single action type within a tenant."""

    action_type: ActionType = Field(..., description="Which action type this configures")
    enabled: bool = Field(default=True, description="Whether this action type is enabled")
    auto_execute: bool = Field(
        default=False,
        description="Whether this action type can auto-execute (subject to confidence gate)",
    )
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Integration-specific configuration",
    )


def _registry_path(tenant_id: str) -> Path:
    """Return the path to the tenant's action_registry.json."""
    settings = get_settings()
    return Path(settings.TENANTS_DIR) / tenant_id / "action_registry.json"


async def load_registry(tenant_id: str) -> List[ActionConfig]:
    """Load the action registry for a tenant. Falls back to default if missing."""
    path = _registry_path(tenant_id)
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            return [ActionConfig(**item) for item in raw]
    except Exception:
        logger.warning("action.registry.load_failed", tenant_id=tenant_id, path=str(path))

    logger.info("action.registry.using_default", tenant_id=tenant_id)
    return [ActionConfig(**item) for item in DEFAULT_REGISTRY]


async def save_registry(tenant_id: str, configs: List[ActionConfig]) -> None:
    """Save the action registry for a tenant."""
    path = _registry_path(tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "action_type": c.action_type.value,
            "enabled": c.enabled,
            "auto_execute": c.auto_execute,
            "config": c.config,
        }
        for c in configs
    ]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("action.registry.saved", tenant_id=tenant_id, count=len(configs))


async def get_enabled_actions(tenant_id: str) -> List[ActionConfig]:
    """Return only the enabled action configs for a tenant."""
    registry = await load_registry(tenant_id)
    return [c for c in registry if c.enabled]
