"""ReplyMonitor — polls inbox for supplier replies (Level 9, thinking=OFF).

In demo mode, loads mock replies from data/demo_replies.json after a delay.
In production, polls IMAP inbox for replies matching outreach email subjects.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from sentinel.config import get_settings
from sentinel.models.negotiation import NegotiationSession, OutreachEmail

logger = structlog.get_logger(__name__)


class ReplyMonitor:
    """Monitors for supplier replies to outreach emails."""

    def __init__(self, demo_mode: bool = False) -> None:
        self.demo_mode = demo_mode

    async def poll(
        self,
        session: NegotiationSession,
        timeout_seconds: int = 60,
    ) -> list[OutreachEmail]:
        """Poll for replies to outreach emails.

        In demo mode: loads mock replies after a short delay.
        In production: polls IMAP inbox for matching subjects.

        Returns updated OutreachEmail list with replies populated.
        """
        settings = get_settings()

        if self.demo_mode or settings.DEMO_MODE:
            return await self._demo_poll(session)

        try:
            return await self._imap_poll(session, timeout_seconds)
        except Exception as exc:
            logger.warning("reply_monitor.imap_failed", error=str(exc))
            return await self._demo_poll(session)

    async def _demo_poll(
        self, session: NegotiationSession
    ) -> list[OutreachEmail]:
        """Load mock replies from data/demo_replies.json after a brief delay."""
        # Short delay to simulate waiting (2 seconds in demo)
        await asyncio.sleep(2)

        demo_path = Path("data") / "demo_replies.json"
        if not demo_path.exists():
            project_root = Path(__file__).parent.parent.parent
            demo_path = project_root / "data" / "demo_replies.json"

        try:
            with open(demo_path, encoding="utf-8") as f:
                mock_replies = json.load(f)
        except Exception as exc:
            logger.error("reply_monitor.demo_load_failed", error=str(exc))
            return session.outreach_emails

        # Match mock replies to outreach emails by supplier name
        updated_emails = []
        for email in session.outreach_emails:
            matched_reply = None
            for reply in mock_replies:
                if (
                    reply["supplier_name"].lower()
                    == email.supplier.name.lower()
                ):
                    matched_reply = reply
                    break

            if matched_reply:
                email.reply_received = True
                email.reply_body = matched_reply["body"]
                email.reply_at = datetime.fromisoformat(
                    matched_reply.get("received_at", datetime.utcnow().isoformat())
                )
                logger.info(
                    "reply_monitor.demo_reply",
                    supplier=email.supplier.name,
                )

            updated_emails.append(email)

        replied_count = sum(1 for e in updated_emails if e.reply_received)
        logger.info(
            "reply_monitor.demo_complete",
            total=len(updated_emails),
            replied=replied_count,
        )
        return updated_emails

    async def _imap_poll(
        self,
        session: NegotiationSession,
        timeout_seconds: int,
    ) -> list[OutreachEmail]:
        """Poll IMAP inbox for replies (production mode).

        Uses SMTP settings from config as IMAP settings.
        Falls back to demo mode if IMAP fails.
        """
        import imaplib
        import email as email_lib

        settings = get_settings()
        imap_host = settings.SMTP_HOST.replace("smtp.", "imap.")
        imap_user = settings.SMTP_USER
        imap_pass = settings.SMTP_PASSWORD

        if not all([imap_host, imap_user, imap_pass]):
            logger.warning("reply_monitor.no_imap_config")
            return session.outreach_emails

        try:
            mail = imaplib.IMAP4_SSL(imap_host)
            mail.login(imap_user, imap_pass)
            mail.select("inbox")

            updated_emails = []
            for oe in session.outreach_emails:
                if oe.reply_received:
                    updated_emails.append(oe)
                    continue

                # Search for replies by subject
                search_subject = f'Re: {oe.subject}'
                _, data = mail.search(None, f'(SUBJECT "{search_subject}")')

                if data[0]:
                    msg_ids = data[0].split()
                    if msg_ids:
                        _, msg_data = mail.fetch(msg_ids[-1], "(RFC822)")
                        msg = email_lib.message_from_bytes(msg_data[0][1])
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    body = part.get_payload(decode=True).decode()
                                    break
                        else:
                            body = msg.get_payload(decode=True).decode()

                        oe.reply_received = True
                        oe.reply_body = body
                        oe.reply_at = datetime.utcnow()
                        logger.info("reply_monitor.reply_found", supplier=oe.supplier.name)

                updated_emails.append(oe)

            mail.logout()
            return updated_emails

        except Exception as exc:
            logger.error("reply_monitor.imap_error", error=str(exc))
            return session.outreach_emails
