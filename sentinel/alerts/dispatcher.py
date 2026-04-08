"""AlertDispatcher — fire notifications for high-priority alerts (Level 3).

Supports three channels:
  1. Email via smtplib (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD)
  2. Slack via httpx POST to SLACK_WEBHOOK_URL
  3. Demo mode (ALERT_DEMO_MODE=true) — structlog only, no external calls

Usage:
    from sentinel.alerts.dispatcher import fire_alert
    await fire_alert(title="Critical CVE", priority="P0", summary="...")

Called by ArbiterAgent as asyncio.create_task() when red_team_wins
or when priority >= P1.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.mime.text import MIMEText
from typing import Any

import structlog

from sentinel.config import settings

logger = structlog.get_logger(__name__)


async def fire_alert(
    title: str,
    priority: str,
    summary: str,
    signal_id: str = "",
    report_id: str = "",
    recommended_action: str = "",
) -> dict[str, Any]:
    """Dispatch an alert to configured channels.

    Args:
        title:              Alert headline.
        priority:           P0/P1/P2/P3.
        summary:            Brief description.
        signal_id:          Originating signal ID.
        report_id:          Associated risk report ID.
        recommended_action: What to do about it.

    Returns:
        Dict with dispatch results per channel.
    """
    alert_data = {
        "title": title,
        "priority": priority,
        "summary": summary,
        "signal_id": signal_id,
        "report_id": report_id,
        "recommended_action": recommended_action,
    }

    results: dict[str, Any] = {"channels": []}

    demo_mode = getattr(settings, "ALERT_DEMO_MODE", True)

    if demo_mode:
        logger.info(
            "alert.dispatch.demo",
            **alert_data,
        )
        results["channels"].append("demo_log")
        results["status"] = "demo"
        return results

    # Email dispatch
    try:
        email_sent = await _send_email(alert_data)
        if email_sent:
            results["channels"].append("email")
    except Exception:
        logger.exception("alert.dispatch.email_error")

    # Slack dispatch
    try:
        slack_sent = await _send_slack(alert_data)
        if slack_sent:
            results["channels"].append("slack")
    except Exception:
        logger.exception("alert.dispatch.slack_error")

    results["status"] = "sent" if results["channels"] else "failed"

    logger.info(
        "alert.dispatch.done",
        channels=results["channels"],
        status=results["status"],
    )
    return results


async def _send_email(alert_data: dict[str, Any]) -> bool:
    """Send alert email via SMTP."""
    smtp_host = getattr(settings, "SMTP_HOST", "")
    smtp_port = int(getattr(settings, "SMTP_PORT", 587))
    smtp_user = getattr(settings, "SMTP_USER", "")
    smtp_password = getattr(settings, "SMTP_PASSWORD", "")
    alert_email_to = getattr(settings, "ALERT_EMAIL_TO", "")

    if not all([smtp_host, smtp_user, smtp_password, alert_email_to]):
        logger.debug("alert.email.skipped", reason="missing_config")
        return False

    subject = f"[SENTINEL {alert_data['priority']}] {alert_data['title']}"
    body = (
        f"Priority: {alert_data['priority']}\n"
        f"Title: {alert_data['title']}\n"
        f"Summary: {alert_data['summary']}\n"
        f"Signal ID: {alert_data['signal_id']}\n"
        f"Recommended Action: {alert_data['recommended_action']}\n"
    )

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = alert_email_to

    # Run blocking SMTP in thread pool
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None, _smtp_send, smtp_host, smtp_port, smtp_user, smtp_password, msg,
    )

    logger.info("alert.email.sent", to=alert_email_to)
    return True


def _smtp_send(
    host: str, port: int, user: str, password: str, msg: MIMEText,
) -> None:
    """Blocking SMTP send (run in executor)."""
    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)


async def _send_slack(alert_data: dict[str, Any]) -> bool:
    """Send alert to Slack webhook."""
    webhook_url = getattr(settings, "SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        logger.debug("alert.slack.skipped", reason="no_webhook_url")
        return False

    try:
        import httpx
    except ImportError:
        logger.warning("alert.slack.skipped", reason="httpx_not_installed")
        return False

    emoji = {"P0": "🔴", "P1": "🟠", "P2": "🟡", "P3": "⚪"}.get(
        alert_data["priority"], "⚪"
    )

    payload = {
        "text": (
            f"{emoji} *[SENTINEL {alert_data['priority']}]* {alert_data['title']}\n"
            f">{alert_data['summary']}\n"
            f"*Action:* {alert_data['recommended_action']}"
        ),
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(webhook_url, json=payload, timeout=10.0)
        resp.raise_for_status()

    logger.info("alert.slack.sent")
    return True
