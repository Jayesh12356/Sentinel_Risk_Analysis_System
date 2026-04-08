"""NegotiationPipeline — separate LangGraph StateGraph for supplier negotiation (Level 9).

Flow: SEARCH -> DRAFT -> SEND -> MONITOR -> SUMMARISE -> COMPLETE -> END

Triggered by ActionEngine when INITIATE_NEGOTIATION action is executed.
Runs independently from the main pipeline as asyncio.create_task().
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

import structlog
from langgraph.graph import StateGraph, END

from sentinel.config import get_settings
from sentinel.models.negotiation import (
    NegotiationSession,
    NegotiationStatus,
    OutreachEmail,
)
from sentinel.negotiation.store import save_session, update_session

logger = structlog.get_logger(__name__)


class NegotiationState(TypedDict):
    """State that flows through the negotiation pipeline."""
    session: NegotiationSession
    company_profile: Any
    error: str


# ── Node Functions ────────────────────────────────────────────────────────

async def search_node(state: NegotiationState) -> NegotiationState:
    """SEARCH: Find alternative suppliers."""
    session = state["session"]
    company_profile = state.get("company_profile")
    settings = get_settings()

    try:
        from sentinel.negotiation.web_search import WebSearchAgent

        agent = WebSearchAgent(demo_mode=settings.DEMO_MODE)
        industry = getattr(company_profile, "industry", "") if company_profile else ""

        alternatives = await agent.search(
            original_supplier=session.original_supplier,
            industry=industry,
            company_profile=company_profile,
            max_results=settings.NEGOTIATION_MAX_ALTERNATIVES,
        )

        session.alternatives_found = alternatives
        session.status = NegotiationStatus.DRAFTING
        await save_session(session)

        logger.info(
            "negotiation.search_done",
            session_id=session.id,
            alternatives=len(alternatives),
        )
    except Exception as exc:
        logger.error("negotiation.search_failed", error=str(exc))
        state["error"] = str(exc)

    return state


async def draft_node(state: NegotiationState) -> NegotiationState:
    """DRAFT: Write outreach emails for each alternative."""
    session = state["session"]
    company_profile = state.get("company_profile")

    if not session.alternatives_found:
        logger.warning("negotiation.no_alternatives_to_draft", session_id=session.id)
        return state

    try:
        from sentinel.negotiation.outreach_drafter import OutreachDrafter

        drafter = OutreachDrafter(demo_mode=get_settings().DEMO_MODE)
        company_name = getattr(company_profile, "name", "Our Company") if company_profile else "Our Company"

        emails = await drafter.draft_batch(
            suppliers=session.alternatives_found,
            company_name=company_name,
            company_profile=company_profile,
            risk_reason=session.risk_reason,
            original_supplier=session.original_supplier,
        )

        session.outreach_emails = emails
        session.status = NegotiationStatus.DRAFTING
        await save_session(session)

        logger.info("negotiation.drafts_done", session_id=session.id, emails=len(emails))
    except Exception as exc:
        logger.error("negotiation.draft_failed", error=str(exc))
        state["error"] = str(exc)

    return state


async def send_node(state: NegotiationState) -> NegotiationState:
    """SEND: Mark emails as sent (demo mode: just log)."""
    session = state["session"]
    settings = get_settings()

    for email in session.outreach_emails:
        if settings.DEMO_MODE or not settings.NEGOTIATION_AUTO_SEND:
            # In demo mode or when auto-send disabled, just mark as "sent"
            email.sent_at = datetime.utcnow()
            logger.info("negotiation.email_sent_demo", supplier=email.supplier.name)
        else:
            # Production: send via SMTP
            try:
                from sentinel.alerts.email_sender import send_email

                await send_email(
                    to=email.supplier.website,  # Would need actual email
                    subject=email.subject,
                    body=email.body,
                )
                email.sent_at = datetime.utcnow()
                logger.info("negotiation.email_sent", supplier=email.supplier.name)
            except Exception as exc:
                logger.error("negotiation.email_send_failed", supplier=email.supplier.name, error=str(exc))

    session.status = NegotiationStatus.AWAITING_REPLY
    await save_session(session)
    return state


async def monitor_node(state: NegotiationState) -> NegotiationState:
    """MONITOR: Poll for replies (with timeout)."""
    session = state["session"]
    settings = get_settings()

    try:
        from sentinel.negotiation.reply_monitor import ReplyMonitor

        monitor = ReplyMonitor(demo_mode=settings.DEMO_MODE)
        timeout = settings.NEGOTIATION_TIMEOUT_HOURS * 3600 if not settings.DEMO_MODE else 10

        updated_emails = await monitor.poll(session, timeout_seconds=timeout)
        session.outreach_emails = updated_emails
        session.status = NegotiationStatus.SUMMARISING
        await save_session(session)

        replied = sum(1 for e in updated_emails if e.reply_received)
        logger.info(
            "negotiation.monitor_done",
            session_id=session.id,
            replied=replied,
            total=len(updated_emails),
        )
    except Exception as exc:
        logger.error("negotiation.monitor_failed", error=str(exc))
        state["error"] = str(exc)

    return state


async def summarise_node(state: NegotiationState) -> NegotiationState:
    """SUMMARISE: Analyse replies and generate recommendation."""
    session = state["session"]
    company_profile = state.get("company_profile")

    try:
        from sentinel.negotiation.summary import NegotiationSummary

        summariser = NegotiationSummary(demo_mode=get_settings().DEMO_MODE)
        session = await summariser.summarise(session, company_profile=company_profile)
        await save_session(session)

        logger.info(
            "negotiation.summarised",
            session_id=session.id,
            recommended=session.recommendation,
        )
    except Exception as exc:
        logger.error("negotiation.summarise_failed", error=str(exc))
        state["error"] = str(exc)

    state["session"] = session
    return state


async def complete_node(state: NegotiationState) -> NegotiationState:
    """COMPLETE: Finalise the negotiation session."""
    session = state["session"]

    if session.status != NegotiationStatus.COMPLETE:
        session.status = NegotiationStatus.COMPLETE
        session.completed_at = datetime.utcnow()

    await save_session(session)

    logger.info(
        "negotiation.complete",
        session_id=session.id,
        recommendation=session.recommendation,
        status=session.status.value,
    )
    return state


# ── Graph Builder ─────────────────────────────────────────────────────────

def build_negotiation_graph() -> StateGraph:
    """Build the NegotiationPipeline StateGraph.

    Flow: SEARCH -> DRAFT -> SEND -> MONITOR -> SUMMARISE -> COMPLETE -> END
    """
    graph = StateGraph(NegotiationState)

    # Add nodes
    graph.add_node("SEARCH", search_node)
    graph.add_node("DRAFT", draft_node)
    graph.add_node("SEND", send_node)
    graph.add_node("MONITOR", monitor_node)
    graph.add_node("SUMMARISE", summarise_node)
    graph.add_node("COMPLETE", complete_node)

    # Linear flow
    graph.set_entry_point("SEARCH")
    graph.add_edge("SEARCH", "DRAFT")
    graph.add_edge("DRAFT", "SEND")
    graph.add_edge("SEND", "MONITOR")
    graph.add_edge("MONITOR", "SUMMARISE")
    graph.add_edge("SUMMARISE", "COMPLETE")
    graph.add_edge("COMPLETE", END)

    return graph


# ── Runner ────────────────────────────────────────────────────────────────

async def run_negotiation(
    session: NegotiationSession,
    company_profile: Any = None,
) -> NegotiationSession:
    """Run the full negotiation pipeline for a session.

    This is the entry point called by ActionEngine via asyncio.create_task().
    """
    try:
        graph = build_negotiation_graph()
        compiled = graph.compile()

        initial_state: NegotiationState = {
            "session": session,
            "company_profile": company_profile,
            "error": "",
        }

        result = await compiled.ainvoke(initial_state)
        return result["session"]

    except Exception as exc:
        logger.error("negotiation.pipeline_failed", session_id=session.id, error=str(exc))
        session.status = NegotiationStatus.FAILED
        session.completed_at = datetime.utcnow()
        await save_session(session)
        return session
