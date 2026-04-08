"""BlueTeamAgent — Layer 3 deliberation agent for optimistic defence.

Uses Gemini via sentinel/llm/client.py with **thinking=ON** to
counter Red Team arguments, defend the current assessment, and argue
that the risk is manageable or mitigatable.

Per CONTEXT.md:
- Thinking ON (budget_tokens=8000) — deep defensive reasoning
- Sets deliberation.blue_team_argument on each RiskReport
- Sequential LangGraph node (not AutoGen)
- Level 3: queries memory for past mitigations to strengthen defence
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

BLUE_TEAM_PROMPT_TEMPLATE = """You are an optimistic Blue Team defence analyst for enterprise risk intelligence.

Your role is to COUNTER the Red Team's adversarial argument and defend the current risk assessment. Argue that the risk is MANAGEABLE, identify mitigating factors, and explain why the situation may not be as severe as the Red Team claims.

Be specific, cite evidence from the signal and assessment, and provide a balanced but optimistic counter-argument.

Return a JSON object with:
- argument: a 3–5 sentence defence explaining why this risk is manageable or why the Red Team overstates the threat
- mitigating_factors: a JSON array of 2–4 strings — factors that reduce the actual risk
- supports_current_priority: boolean — true if you believe the current priority is appropriate (no escalation needed)
- confidence: float 0.0–1.0 — how confident you are in your defence

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

RED TEAM ARGUMENT:
{red_team_argument}

PAST MITIGATIONS & OUTCOMES (from memory — use to argue risk is manageable):
{memory_context}
"""


class BlueTeamAgent(BaseAgent):
    """Optimistic defender — argues that risks are manageable.

    For each RiskReport, generates a counter-argument defending
    the current assessment against Red Team challenges.
    """

    agent_name: str = "BlueTeamAgent"

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute optimistic defence — LangGraph node entry point."""
        reports: list[RiskReport] = state.get("risk_reports", [])
        signals: list[Signal] = state.get("signals", [])
        signal_map: dict[str, Signal] = {s.id: s for s in signals}

        self.log.info("blue_team.start", report_count=len(reports))

        updated_reports: list[RiskReport] = []
        for report in reports:
            signal = signal_map.get(report.signal_id)
            if not signal:
                self.log.warning("blue_team.no_signal", report_id=report.id)
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
                    "blue_team.memory",
                    signal_id=str(signal.id),
                    memories_found=len(memories),
                )
                result = await self._defend(signal, report, memories)
                report.deliberation.blue_team_argument = result["argument"]

                self.log.info(
                    "blue_team.report.done",
                    report_id=report.id,
                    supports_priority=result["supports_current_priority"],
                    confidence=result["confidence"],
                )
            except Exception:
                self.log.exception("blue_team.report.error", report_id=report.id)

            updated_reports.append(report)

        self.log.info("blue_team.done", total_reports=len(updated_reports))
        return {"risk_reports": updated_reports}

    async def _defend(
        self, signal: Signal, report: RiskReport, memories: list[MemoryEntry] | None = None,
    ) -> dict[str, Any]:
        """Generate optimistic defence for a single report."""
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
            memory_context = "No past mitigations found."
        template = await get_active_prompt("BlueTeamAgent", default=BLUE_TEAM_PROMPT_TEMPLATE)
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
            red_team_argument=report.deliberation.red_team_argument or "No Red Team argument available.",
            memory_context=memory_context,
        )

        # Thinking ON for BlueTeamAgent (deep defensive reasoning)
        raw_response = await self.llm_complete(prompt, thinking=True)

        return self._parse_defence(raw_response)

    def _parse_defence(self, raw: str) -> dict[str, Any]:
        """Parse LLM JSON response into defence dict."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            self.log.warning("blue_team.parse.invalid_json", raw=cleaned[:200])
            return {
                "argument": "Unable to generate defence argument.",
                "mitigating_factors": [],
                "supports_current_priority": True,
                "confidence": 0.0,
            }

        return {
            "argument": str(data.get("argument", "")),
            "mitigating_factors": [
                str(f) for f in data.get("mitigating_factors", [])
                if isinstance(data.get("mitigating_factors", []), list)
            ],
            "supports_current_priority": bool(
                data.get("supports_current_priority", True)
            ),
            "confidence": max(
                0.0, min(1.0, float(data.get("confidence", 0.0)))
            ),
        }
