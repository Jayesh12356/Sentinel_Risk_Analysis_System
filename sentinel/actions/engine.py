"""ActionEngine — executes autonomous actions via integrations (Level 8).

Dispatches ActionEntry objects to the correct integration backend.
When ACTION_DEMO_MODE=true, all integrations log via structlog only.
"""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any, Dict

import structlog

from sentinel.config import get_settings
from sentinel.models.action_entry import ActionEntry, ActionStatus, ActionType

logger = structlog.get_logger()


class ActionEngine:
    """Executes actions by dispatching to the correct integration."""

    _DISPATCH = {
        ActionType.JIRA_TICKET: "_execute_jira",
        ActionType.PAGERDUTY_ALERT: "_execute_pagerduty",
        ActionType.EMAIL_DRAFT: "_execute_email_draft",
        ActionType.WEBHOOK: "_execute_webhook",
        ActionType.SLACK_MESSAGE: "_execute_slack",
        ActionType.INITIATE_NEGOTIATION: "_execute_negotiation",  # Level 9
    }

    async def execute(self, action: ActionEntry) -> ActionEntry:
        """Execute an action and update its status/result.

        Returns the updated ActionEntry with execution result.
        """
        settings = get_settings()

        # Level 10: Check for override before executing
        try:
            from sentinel.meta.override import check_override
            if await check_override("ACTION_TYPE", action.action_type.value):
                logger.info("action.engine.override_blocked", action_type=action.action_type.value)
                action.status = ActionStatus.FAILED
                action.result = {"error": "Blocked by override rule"}
                return action
        except Exception:
            pass  # Override system unavailable — proceed normally

        handler_name = self._DISPATCH.get(action.action_type)
        if not handler_name:
            logger.error("action.engine.unknown_type", action_type=action.action_type.value)
            action.status = ActionStatus.FAILED
            action.result = {"error": f"Unknown action type: {action.action_type.value}"}
            return action

        handler = getattr(self, handler_name)

        try:
            if settings.ACTION_DEMO_MODE:
                result = await self._demo_execute(action)
            else:
                result = await handler(action)

            action.result = result
            action.executed_at = datetime.utcnow()

            if action.status == ActionStatus.PENDING_APPROVAL:
                action.status = ActionStatus.APPROVED
            elif action.status != ActionStatus.APPROVED:
                action.status = ActionStatus.AUTO_EXECUTED

            logger.info(
                "action.engine.executed",
                action_id=action.id,
                action_type=action.action_type.value,
                status=action.status.value,
                demo_mode=settings.ACTION_DEMO_MODE,
            )

            # Level 10: Log to governance
            try:
                from sentinel.meta.governance import log_event
                await log_event(
                    event_type="ACTION_EXECUTED",
                    agent_name="ActionEngine",
                    tenant_id=action.tenant_id,
                    description=f"Executed {action.action_type.value}: {action.title}",
                    reasoning=action.reasoning or "",
                    confidence=action.confidence,
                )
            except Exception:
                pass

        except Exception as exc:
            logger.error(
                "action.engine.failed",
                action_id=action.id,
                action_type=action.action_type.value,
                error=str(exc),
            )
            action.status = ActionStatus.FAILED
            action.result = {"error": str(exc)}

        return action

    async def _demo_execute(self, action: ActionEntry) -> Dict[str, Any]:
        """Demo mode: log the action without calling any external service."""
        logger.info(
            "action.engine.demo",
            action_type=action.action_type.value,
            title=action.title,
            signal_id=action.signal_id,
            confidence=action.confidence,
            payload_keys=list(action.payload.keys()),
        )
        return {
            "demo": True,
            "message": f"[DEMO] {action.action_type.value} would be executed: {action.title}",
            "action_type": action.action_type.value,
        }

    # ── Integration handlers ──────────────────────────────────────────────

    async def _execute_jira(self, action: ActionEntry) -> Dict[str, Any]:
        """Create a Jira incident ticket via REST API v3."""
        import httpx

        settings = get_settings()
        url = f"{settings.JIRA_BASE_URL}/rest/api/3/issue"
        auth_str = f"{settings.JIRA_EMAIL}:{settings.JIRA_API_TOKEN}"
        auth_b64 = base64.b64encode(auth_str.encode()).decode()

        payload = {
            "fields": {
                "project": {"key": settings.JIRA_PROJECT_KEY},
                "summary": action.title,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": action.description or action.reasoning}
                            ],
                        }
                    ],
                },
                "issuetype": {"name": action.payload.get("issue_type", "Bug")},
                "priority": {"name": action.payload.get("priority", "High")},
            }
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Basic {auth_b64}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        logger.info("action.jira.created", key=data.get("key"), id=data.get("id"))
        return {"jira_key": data.get("key"), "jira_id": data.get("id"), "url": f"{settings.JIRA_BASE_URL}/browse/{data.get('key')}"}

    async def _execute_pagerduty(self, action: ActionEntry) -> Dict[str, Any]:
        """Page on-call engineer via PagerDuty Events API v2."""
        import httpx

        settings = get_settings()
        url = "https://events.pagerduty.com/v2/enqueue"

        payload = {
            "routing_key": settings.PAGERDUTY_INTEGRATION_KEY,
            "event_action": "trigger",
            "payload": {
                "summary": action.title,
                "severity": action.payload.get("severity", "critical"),
                "source": "SENTINEL",
                "component": action.payload.get("component", "sentinel"),
                "custom_details": {
                    "signal_id": action.signal_id,
                    "description": action.description,
                    "reasoning": action.reasoning,
                    "confidence": action.confidence,
                },
            },
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        logger.info("action.pagerduty.triggered", dedup_key=data.get("dedup_key"))
        return {"dedup_key": data.get("dedup_key"), "status": data.get("status"), "message": data.get("message")}

    async def _execute_email_draft(self, action: ActionEntry) -> Dict[str, Any]:
        """Store an email draft — does NOT send. Human must review and send."""
        logger.info(
            "action.email.drafted",
            title=action.title,
            signal_id=action.signal_id,
        )
        return {
            "drafted": True,
            "subject": action.title,
            "body": action.description or action.reasoning,
            "template": action.payload.get("template", "incident_notification"),
            "message": "Email draft created. Human must review and send.",
        }

    async def _execute_webhook(self, action: ActionEntry) -> Dict[str, Any]:
        """POST to a configured webhook URL."""
        import httpx

        settings = get_settings()
        url = action.payload.get("url") or settings.ACTION_WEBHOOK_URL
        if not url:
            raise ValueError("No webhook URL configured in action payload or ACTION_WEBHOOK_URL")

        body = {
            "action_id": action.id,
            "action_type": action.action_type.value,
            "title": action.title,
            "description": action.description,
            "signal_id": action.signal_id,
            "confidence": action.confidence,
            "reasoning": action.reasoning,
            **action.payload.get("body", {}),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()

        logger.info("action.webhook.posted", url=url, status=resp.status_code)
        return {"url": url, "status_code": resp.status_code, "response": resp.text[:500]}

    async def _execute_slack(self, action: ActionEntry) -> Dict[str, Any]:
        """Send a Slack message via webhook."""
        import httpx

        settings = get_settings()
        url = settings.SLACK_WEBHOOK_URL
        if not url:
            raise ValueError("SLACK_WEBHOOK_URL not configured")

        payload = {
            "text": f"🚨 *SENTINEL Action*\n*{action.title}*\n{action.description or action.reasoning}\n\nConfidence: {action.confidence:.0%} | Signal: {action.signal_id}",
            "channel": action.payload.get("channel", "#security-alerts"),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()

        logger.info("action.slack.sent", channel=payload["channel"])
        return {"channel": payload["channel"], "status": "sent"}

    async def _execute_negotiation(self, action: ActionEntry) -> Dict[str, Any]:
        """Initiate a supplier negotiation workflow (Level 9).

        Creates a NegotiationSession and fires the NegotiationPipeline
        as an asyncio background task.
        """
        import asyncio
        from sentinel.models.negotiation import NegotiationSession, NegotiationStatus
        from sentinel.negotiation.store import save_session

        session = NegotiationSession(
            tenant_id=action.tenant_id,
            signal_id=action.signal_id,
            action_id=action.id,
            original_supplier=action.payload.get("supplier_name", "Unknown"),
            risk_reason=action.reasoning,
            status=NegotiationStatus.SEARCHING,
        )
        await save_session(session)

        logger.info(
            "action.negotiation.initiated",
            session_id=session.id,
            supplier=session.original_supplier,
            tenant_id=session.tenant_id,
        )

        # Fire NegotiationPipeline as background task
        try:
            from sentinel.negotiation.pipeline import run_negotiation
            asyncio.create_task(run_negotiation(session))
        except Exception as exc:
            logger.warning("action.negotiation.pipeline_start_failed", error=str(exc))

        return {
            "session_id": session.id,
            "supplier": session.original_supplier,
            "status": session.status.value,
            "message": f"Negotiation initiated for {session.original_supplier}",
        }
