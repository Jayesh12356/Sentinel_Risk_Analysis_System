"""HumanOverrideSystem — allows halting autonomous behaviour (Level 10).

Override rules stored in data/override_rules.json (flat file).
Checked at runtime before agent/action execution.
"""

from __future__ import annotations

import json
import uuid as uuid_mod
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog
from pydantic import BaseModel, Field

from sentinel.config import get_settings

logger = structlog.get_logger(__name__)


class OverrideRule(BaseModel):
    """A rule that halts a class of autonomous behaviour."""
    id: str = Field(default_factory=lambda: str(uuid_mod.uuid4()))
    scope: str  # AGENT / ACTION_TYPE / TENANT / GLOBAL
    target: str  # e.g. "ActionPlanner", "JIRA_TICKET", "techcorp", "*"
    reason: str = ""
    applied_by: str = "system"
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None

    def to_payload(self) -> dict:
        return {
            "id": self.id,
            "scope": self.scope,
            "target": self.target,
            "reason": self.reason,
            "applied_by": self.applied_by,
            "active": self.active,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_payload(cls, data: dict) -> OverrideRule:
        data = dict(data)
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("expires_at"), str) and data["expires_at"]:
            data["expires_at"] = datetime.fromisoformat(data["expires_at"])
        return cls(**data)


def _load_rules() -> list[OverrideRule]:
    """Load override rules from JSON file."""
    settings = get_settings()
    path = Path(settings.OVERRIDE_RULES_PATH)
    if not path.exists():
        # Try project root
        project_root = Path(__file__).parent.parent.parent
        path = project_root / settings.OVERRIDE_RULES_PATH
    if not path.exists():
        return []

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return [OverrideRule.from_payload(d) for d in data]
    except Exception as exc:
        logger.warning("override.load_failed", error=str(exc))
        return []


def _save_rules(rules: list[OverrideRule]) -> None:
    """Save override rules to JSON file."""
    settings = get_settings()
    path = Path(settings.OVERRIDE_RULES_PATH)
    if not path.exists():
        project_root = Path(__file__).parent.parent.parent
        path = project_root / settings.OVERRIDE_RULES_PATH

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump([r.to_payload() for r in rules], f, indent=2)
    except Exception as exc:
        logger.error("override.save_failed", error=str(exc))


async def check_override(scope: str, target: str) -> bool:
    """Check if an override is active for the given scope/target.

    Returns True if an active override blocks execution.
    """
    rules = _load_rules()
    now = datetime.utcnow()

    for rule in rules:
        if not rule.active:
            continue
        # Check expiry
        if rule.expires_at and rule.expires_at < now:
            continue

        # GLOBAL overrides block everything
        if rule.scope == "GLOBAL":
            logger.info("override.global_active", reason=rule.reason)
            return True

        # Scope-specific check
        if rule.scope == scope and rule.target.lower() == target.lower():
            logger.info("override.matched", scope=scope, target=target, reason=rule.reason)
            return True

    return False


async def create_override(
    scope: str,
    target: str,
    reason: str = "",
    applied_by: str = "system",
    expires_at: Optional[datetime] = None,
) -> OverrideRule:
    """Create and persist a new override rule."""
    rule = OverrideRule(
        scope=scope,
        target=target,
        reason=reason,
        applied_by=applied_by,
        expires_at=expires_at,
    )

    rules = _load_rules()
    rules.append(rule)
    _save_rules(rules)

    # Log to governance
    try:
        from sentinel.meta.governance import log_event
        await log_event(
            event_type="OVERRIDE_APPLIED",
            agent_name=target,
            description=f"Override created: {scope}/{target} — {reason}",
            reasoning=reason,
            human_involved=True,
            override=True,
        )
    except Exception:
        pass

    logger.info("override.created", scope=scope, target=target, rule_id=rule.id)
    return rule


async def deactivate_override(override_id: str) -> Optional[OverrideRule]:
    """Deactivate an override by ID."""
    rules = _load_rules()
    for rule in rules:
        if rule.id == override_id:
            rule.active = False
            _save_rules(rules)
            logger.info("override.deactivated", rule_id=override_id)
            return rule
    return None


async def list_overrides(active_only: bool = True) -> list[OverrideRule]:
    """List override rules, optionally only active ones."""
    rules = _load_rules()
    now = datetime.utcnow()

    if active_only:
        rules = [
            r for r in rules
            if r.active and (not r.expires_at or r.expires_at > now)
        ]
    return rules
