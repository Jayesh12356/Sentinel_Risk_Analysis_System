"""RedTeamAgent — Layer 3 deliberation agent for adversarial challenge.

Uses Gemini via sentinel/llm/client.py with **thinking=ON** to
devil's-advocate each risk assessment: finding weaknesses, blind spots,
and reasons why the risk may be understated.

Per CONTEXT.md:
- Thinking ON (budget_tokens=8000) — deep adversarial reasoning
- Sets deliberation.red_team_argument on each RiskReport
- Sequential LangGraph node (not AutoGen)
- Level 3: queries memory for past false positives to calibrate challenges
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from sentinel.agents.base import BaseAgent
from sentinel.memory.retriever import get_relevant_memories
from sentinel.models.memory_entry import MemoryEntry
from sentinel.models.risk_report import RiskReport
from sentinel.models.signal import Signal
from sentinel.optimiser.prompt_store import get_active_prompt

logger = structlog.get_logger(__name__)

RED_TEAM_PROMPT_TEMPLATE = """You are an adversarial Red Team analyst for enterprise risk intelligence.

Your role is to CHALLENGE the risk assessment and argue that the risk is WORSE than currently assessed. Find weaknesses in the analysis, identify blind spots, and argue for a higher severity.

Be specific, cite evidence from the signal, and provide a compelling adversarial argument.

Return a JSON object with:
- argument: a 3–5 sentence adversarial argument explaining why this risk is more severe than assessed
- missed_factors: a JSON array of 2–4 strings — factors the assessment may have overlooked
- suggested_priority_escalation: boolean — true if you believe the priority should be escalated
- confidence: float 0.0–1.0 — how confident you are in your adversarial challenge

Return ONLY a JSON object. No explanation, no markdown fencing.

SIGNAL TITLE: {title}
SIGNAL SOURCE: {source}
SIGNAL CATEGORY: {category}
CURRENT PRIORITY: {priority}

SIGNAL CONTENT:
{content}

RISK ASSESSMENT:
- Impact: {impact} | Probability: {probability} | Exposure: {exposure}
- Overall Score: {overall}
- Evidence: {evidence}
- Summary: {summary}

CAUSAL CHAIN:
Root Cause: {root_cause}
Chain: {causal_chain}

PAST SIMILAR EVENTS (from memory — check if similar risks were previously dismissed or escalated):
{memory_context}
"""


class RedTeamAgent(BaseAgent):
    """Adversarial challenger — argues that risks are more severe than assessed.

    For each RiskReport, generates a counter-argument challenging
    the assessment and identifying potential blind spots.
    """

    agent_name: str = "RedTeamAgent"

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute adversarial challenge — LangGraph node entry point."""
        reports: list[RiskReport] = state.get("risk_reports", [])
        signals: list[Signal] = state.get("signals", [])
        signal_map: dict[str, Signal] = {s.id: s for s in signals}

        self.log.info("red_team.start", report_count=len(reports))

        updated_reports: list[RiskReport] = []
        for report in reports:
            signal = signal_map.get(report.signal_id)
            if not signal:
                self.log.warning("red_team.no_signal", report_id=report.id)
                updated_reports.append(report)
                continue

            try:
                # Level 3: query memory for past similar events
                memories = await get_relevant_memories(
                    query_text=signal.title,
                    limit=3,
                    days_back=90,
                )
                self.log.info(
                    "red_team.memory",
                    signal_id=str(signal.id),
                    memories_found=len(memories),
                )
                result = await self._challenge(signal, report, memories)
                report.deliberation.red_team_argument = result["argument"]

                self.log.info(
                    "red_team.report.done",
                    report_id=report.id,
                    escalation=result["suggested_priority_escalation"],
                    confidence=result["confidence"],
                )
            except Exception:
                self.log.exception("red_team.report.error", report_id=report.id)

            updated_reports.append(report)

        self.log.info("red_team.done", total_reports=len(updated_reports))
        return {"risk_reports": updated_reports}

    async def _challenge(
        self, signal: Signal, report: RiskReport, memories: list[MemoryEntry] | None = None,
    ) -> dict[str, Any]:
        """Generate adversarial challenge for a single report."""
        # Build memory context string
        if memories:
            memory_lines = []
            for m in memories:
                memory_lines.append(
                    f"- [{m.priority}] {m.title} (risk={m.risk_score:.1f}, "
                    f"outcome={m.outcome[:60] if m.outcome else 'N/A'})"
                )
            memory_context = "\n".join(memory_lines)
        else:
            memory_context = "No past events found."
        # Format causal chain for prompt
        chain_str = "None"
        if report.causal_chain:
            chain_str = " → ".join(
                f"{link.cause} → {link.effect} ({link.confidence:.2f})"
                for link in report.causal_chain
            )

        template = await get_active_prompt("RedTeamAgent", default=RED_TEAM_PROMPT_TEMPLATE)
        prompt = template.format(
            title=signal.title,
            source=signal.source.value,
            category=signal.category,
            priority=signal.priority.value,
            content=signal.content,
            impact=report.risk_score.impact,
            probability=report.risk_score.probability,
            exposure=report.risk_score.exposure,
            overall=report.risk_score.overall,
            evidence=", ".join(report.evidence),
            summary=report.summary,
            root_cause=report.root_cause,
            causal_chain=chain_str,
            memory_context=memory_context,
        )

        # Thinking ON for RedTeamAgent (deep adversarial reasoning)
        raw_response = await self.llm_complete(prompt, thinking=True)

        return self._parse_challenge(raw_response)

    def _parse_challenge(self, raw: str) -> dict[str, Any]:
        """Parse LLM JSON response into challenge dict."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            self.log.warning("red_team.parse.invalid_json", raw=cleaned[:200])
            return {
                "argument": "Unable to generate adversarial challenge.",
                "missed_factors": [],
                "suggested_priority_escalation": False,
                "confidence": 0.0,
            }

        return {
            "argument": str(data.get("argument", "")),
            "missed_factors": [
                str(f) for f in data.get("missed_factors", [])
                if isinstance(data.get("missed_factors", []), list)
            ],
            "suggested_priority_escalation": bool(
                data.get("suggested_priority_escalation", False)
            ),
            "confidence": max(
                0.0, min(1.0, float(data.get("confidence", 0.0)))
            ),
        }
