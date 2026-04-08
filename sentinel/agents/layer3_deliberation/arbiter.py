"""ArbiterAgent — Layer 3 deliberation agent for final verdict.

Uses Gemini via sentinel/llm/client.py with **thinking=ON** to
weigh Red Team vs Blue Team arguments and render a final verdict.

Per CONTEXT.md:
- Thinking ON (budget_tokens=8000) — deep judicial reasoning
- Sets arbiter_verdict, arbiter_confidence, red_team_wins on DeliberationResult
- If red_team_wins: escalates final_priority one level, increments loop2_count
- Loop 2: if Red Team wins → back to RiskAssessor with escalated priority
- Level 3: fires alert via AlertDispatcher for P0/P1 or red_team_wins
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from sentinel.agents.base import BaseAgent
from sentinel.alerts.dispatcher import fire_alert
from sentinel.models.risk_report import RiskReport
from sentinel.models.signal import Signal, SignalPriority
from sentinel.optimiser.prompt_store import get_active_prompt
from sentinel.feedback.weights import get_priority_weight

logger = structlog.get_logger(__name__)

# Priority escalation map: P3→P2→P1→P0→P0 (P0 stays P0)
ESCALATION_MAP: dict[SignalPriority, SignalPriority] = {
    SignalPriority.P3: SignalPriority.P2,
    SignalPriority.P2: SignalPriority.P1,
    SignalPriority.P1: SignalPriority.P0,
    SignalPriority.P0: SignalPriority.P0,
}

ARBITER_PROMPT_TEMPLATE = """You are the Arbiter — a senior risk intelligence judge for an enterprise system.

You must weigh the Red Team's adversarial argument against the Blue Team's optimistic defence and render a final verdict.

Consider both sides carefully and decide:
1. Does the Red Team's argument (risk is worse than assessed) or the Blue Team's argument (risk is manageable) present a stronger case?
2. Should the risk priority be escalated?

Return a JSON object with:
- verdict: a 3–5 sentence final judgement summarising your decision and reasoning
- confidence: float 0.0–1.0 — how confident you are in this verdict
- red_team_wins: boolean — true if the Red Team presented a stronger case and priority should be escalated
- key_factors: a JSON array of 2–3 strings — the most important factors that influenced your decision

Return ONLY a JSON object. No explanation, no markdown fencing.

SIGNAL TITLE: {title}
SIGNAL SOURCE: {source}
CURRENT PRIORITY: {priority}

RISK ASSESSMENT:
- Impact: {impact} | Probability: {probability} | Exposure: {exposure}
- Overall Score: {overall}
- Summary: {summary}

RED TEAM ARGUMENT:
{red_team_argument}

BLUE TEAM DEFENCE:
{blue_team_argument}
"""


class ArbiterAgent(BaseAgent):
    """Final judge — weighs Red vs Blue and renders verdict.

    For each RiskReport, determines whether red_team_wins,
    sets the verdict, and optionally escalates priority (Loop 2).
    Fires alerts via AlertDispatcher for high-priority results.
    """

    agent_name: str = "ArbiterAgent"

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute arbitration — LangGraph node entry point."""
        reports: list[RiskReport] = state.get("risk_reports", [])
        signals: list[Signal] = state.get("signals", [])
        loop2_count: int = state.get("loop2_count", 0)
        signal_map: dict[str, Signal] = {s.id: s for s in signals}

        self.log.info(
            "arbiter.start",
            report_count=len(reports),
            loop2_count=loop2_count,
        )

        updated_reports: list[RiskReport] = []
        any_red_wins = False

        for report in reports:
            signal = signal_map.get(report.signal_id)
            if not signal:
                self.log.warning("arbiter.no_signal", report_id=report.id)
                updated_reports.append(report)
                continue

            try:
                result = await self._arbitrate(signal, report)

                # Update deliberation result
                report.deliberation.arbiter_verdict = result["verdict"]

                # Apply feedback priority weight to arbiter confidence (Level 5)
                source_str = signal.source.value if hasattr(signal.source, "value") else str(signal.source)
                priority_weight = get_priority_weight(source_str)
                raw_confidence = result["confidence"]
                adjusted_confidence = max(0.0, min(1.0, raw_confidence * priority_weight))
                if priority_weight != 1.0:
                    self.log.info(
                        "arbiter.feedback_weight_applied",
                        report_id=report.id,
                        source=source_str,
                        priority_weight=priority_weight,
                        confidence_before=raw_confidence,
                        confidence_after=adjusted_confidence,
                    )

                report.deliberation.arbiter_confidence = adjusted_confidence
                report.deliberation.red_team_wins = result["red_team_wins"]

                # If Red Team wins, escalate priority
                if result["red_team_wins"]:
                    any_red_wins = True
                    old_priority = report.final_priority
                    report.final_priority = ESCALATION_MAP.get(
                        old_priority, old_priority
                    )
                    self.log.info(
                        "arbiter.escalate",
                        report_id=report.id,
                        old_priority=old_priority.value,
                        new_priority=report.final_priority.value,
                    )

                # Level 3: Fire alert for P0/P1 or escalated reports
                should_alert = (
                    report.final_priority in (SignalPriority.P0, SignalPriority.P1)
                    or result["red_team_wins"]
                )
                if should_alert:
                    asyncio.create_task(
                        fire_alert(
                            title=signal.title,
                            priority=report.final_priority.value,
                            summary=report.summary or result["verdict"][:200],
                            signal_id=str(signal.id),
                            report_id=str(report.id),
                            recommended_action=result.get("verdict", "")[:200],
                        )
                    )

                self.log.info(
                    "arbiter.report.done",
                    report_id=report.id,
                    red_team_wins=result["red_team_wins"],
                    confidence=result["confidence"],
                    alert_fired=should_alert,
                )
            except Exception:
                self.log.exception("arbiter.report.error", report_id=report.id)

            updated_reports.append(report)

        # Increment loop2_count if any Red Team wins (for conditional edge)
        new_loop2_count = loop2_count + 1 if any_red_wins else loop2_count

        self.log.info(
            "arbiter.done",
            total_reports=len(updated_reports),
            any_red_wins=any_red_wins,
            loop2_count=new_loop2_count,
        )

        return {
            "risk_reports": updated_reports,
            "loop2_count": new_loop2_count,
        }

    async def _arbitrate(
        self, signal: Signal, report: RiskReport
    ) -> dict[str, Any]:
        """Render verdict for a single report."""
        template = await get_active_prompt("ArbiterAgent", default=ARBITER_PROMPT_TEMPLATE)
        prompt = template.format(
            title=signal.title,
            source=signal.source.value,
            priority=report.final_priority.value,
            impact=report.risk_score.impact,
            probability=report.risk_score.probability,
            exposure=report.risk_score.exposure,
            overall=report.risk_score.overall,
            summary=report.summary,
            red_team_argument=report.deliberation.red_team_argument or "No Red Team argument.",
            blue_team_argument=report.deliberation.blue_team_argument or "No Blue Team argument.",
        )

        # Thinking ON for ArbiterAgent (deep judicial reasoning)
        raw_response = await self.llm_complete(prompt, thinking=True)

        return self._parse_verdict(raw_response)

    def _parse_verdict(self, raw: str) -> dict[str, Any]:
        """Parse LLM JSON response into verdict dict."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            self.log.warning("arbiter.parse.invalid_json", raw=cleaned[:200])
            return {
                "verdict": "Unable to render verdict.",
                "confidence": 0.0,
                "red_team_wins": False,
                "key_factors": [],
            }

        return {
            "verdict": str(data.get("verdict", "")),
            "confidence": max(
                0.0, min(1.0, float(data.get("confidence", 0.0)))
            ),
            "red_team_wins": bool(data.get("red_team_wins", False)),
            "key_factors": [
                str(f) for f in data.get("key_factors", [])
                if isinstance(data.get("key_factors", []), list)
            ],
        }
