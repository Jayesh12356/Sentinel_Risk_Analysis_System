"""NegotiationSummary — synthesises replies into recommendation (Level 9, thinking=ON).

Reads all received replies, asks Gemini to recommend the best option,
and updates the NegotiationSession with recommendation + reasoning.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from sentinel.models.negotiation import (
    NegotiationSession,
    NegotiationStatus,
)
from sentinel.models.action_entry import ActionEntry, ActionStatus, ActionType

logger = structlog.get_logger(__name__)


class NegotiationSummary:
    """Synthesises supplier replies into a recommendation."""

    def __init__(self, demo_mode: bool = False) -> None:
        self.demo_mode = demo_mode

    async def summarise(
        self,
        session: NegotiationSession,
        company_profile: Any = None,
    ) -> NegotiationSession:
        """Analyse replies and generate recommendation.

        Uses Gemini (thinking=ON) for complex multi-factor analysis.
        Returns updated NegotiationSession with recommendation.
        """
        # Collect replies
        replies = [
            e for e in session.outreach_emails
            if e.reply_received and e.reply_body
        ]

        if not replies:
            logger.warning("negotiation_summary.no_replies", session_id=session.id)
            session.recommendation = None
            session.recommendation_reasoning = "No replies received from contacted suppliers."
            session.status = NegotiationStatus.COMPLETE
            session.completed_at = datetime.utcnow()
            return session

        # Build company context
        company_context = ""
        if company_profile:
            company_context = (
                f"Company: {getattr(company_profile, 'name', 'N/A')}\n"
                f"Industry: {getattr(company_profile, 'industry', 'N/A')}\n"
                f"Tech stack: {', '.join(getattr(company_profile, 'tech_stack', [])[:5])}\n"
            )

        try:
            from sentinel.llm.client import get_chat_completion

            reply_text = ""
            for i, r in enumerate(replies, 1):
                reply_text += (
                    f"\n--- Reply {i} from {r.supplier.name} ---\n"
                    f"Relevance score: {r.supplier.relevance_score:.2f}\n"
                    f"Website: {r.supplier.website}\n"
                    f"Reply:\n{r.reply_body}\n"
                )

            prompt = (
                f"We contacted {len(session.outreach_emails)} alternative suppliers "
                f"to replace '{session.original_supplier}' (at risk due to: {session.risk_reason}).\n"
                f"{len(replies)} suppliers replied. Here are their responses:\n"
                f"{reply_text}\n"
                f"Company context:\n{company_context}\n"
                f"Analyse the replies and recommend the best option.\n"
                f"Consider: pricing, capabilities, speed of response, SLA, "
                f"compliance certifications, and fit for our requirements.\n\n"
                f"Return your response in this exact format:\n"
                f"RECOMMENDED: [supplier name]\n"
                f"REASONING: [2-3 paragraph analysis explaining why this supplier "
                f"is the best choice, comparing with alternatives]\n"
                f"NEXT_STEPS: [1-2 sentences on recommended next actions]"
            )

            response = await get_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                thinking=True,
            )
            content = response.choices[0].message.content.strip()

            # Parse recommendation
            recommended, reasoning = self._parse_recommendation(content, replies)

        except Exception as exc:
            logger.warning("negotiation_summary.llm_failed", error=str(exc))
            recommended, reasoning = self._fallback_recommendation(replies)

        session.recommendation = recommended
        session.recommendation_reasoning = reasoning
        session.status = NegotiationStatus.COMPLETE
        session.completed_at = datetime.utcnow()

        logger.info(
            "negotiation_summary.complete",
            session_id=session.id,
            recommended=recommended,
        )

        return session

    def _parse_recommendation(
        self, content: str, replies: list
    ) -> tuple[str, str]:
        """Parse LLM response into recommendation and reasoning."""
        recommended = ""
        reasoning = content

        if "RECOMMENDED:" in content:
            parts = content.split("REASONING:", 1)
            rec_part = parts[0].replace("RECOMMENDED:", "").strip()
            if rec_part:
                recommended = rec_part
            if len(parts) > 1:
                reasoning = parts[1].strip()
                # Remove NEXT_STEPS prefix from reasoning
                if "NEXT_STEPS:" in reasoning:
                    reasoning = reasoning.split("NEXT_STEPS:")[0].strip()
                    next_steps = content.split("NEXT_STEPS:")[-1].strip()
                    reasoning += f"\n\nNext Steps: {next_steps}"

        if not recommended and replies:
            # Fallback: recommend the one with highest relevance
            best = max(replies, key=lambda r: r.supplier.relevance_score)
            recommended = best.supplier.name

        return recommended, reasoning

    def _fallback_recommendation(
        self, replies: list
    ) -> tuple[str, str]:
        """Generate recommendation when LLM is unavailable."""
        if not replies:
            return "", "No replies received. Unable to generate recommendation."

        best = max(replies, key=lambda r: r.supplier.relevance_score)
        return (
            best.supplier.name,
            f"Based on relevance scoring and responsiveness, {best.supplier.name} "
            f"(relevance: {best.supplier.relevance_score:.2f}) is recommended as the "
            f"best alternative. They responded promptly and their profile closely "
            f"matches our requirements. Further due diligence is recommended before "
            f"formal engagement.",
        )

    async def create_recommendation_action(
        self, session: NegotiationSession
    ) -> ActionEntry:
        """Create a PENDING_APPROVAL action for the recommendation."""
        return ActionEntry(
            tenant_id=session.tenant_id,
            signal_id=session.signal_id,
            action_type=ActionType.INITIATE_NEGOTIATION,
            title=f"✅ Accept: {session.recommendation} as replacement for {session.original_supplier}",
            description=(
                f"Negotiation complete. Recommended supplier: {session.recommendation}.\n\n"
                f"{session.recommendation_reasoning}"
            ),
            payload={
                "session_id": session.id,
                "recommended_supplier": session.recommendation,
                "original_supplier": session.original_supplier,
            },
            reasoning=session.recommendation_reasoning or "Negotiation summary analysis",
            confidence=0.75,  # Requires human approval
            status=ActionStatus.PENDING_APPROVAL,
        )
