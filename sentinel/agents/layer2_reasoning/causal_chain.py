"""CausalChainBuilder — Layer 2 reasoning agent for root cause analysis.

Uses Gemini via sentinel/llm/client.py with **thinking=ON** (deep reasoning)
to build causal chains: root cause → intermediate events → downstream effects.

Per CONTEXT.md:
- Thinking ON (budget_tokens=8000) — deep reasoning required
- Populates risk_report.causal_chain with CausalLink objects
- Sets risk_report.root_cause
- Level 3: queries memory for past similar events to inform causal analysis
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from sentinel.agents.base import BaseAgent
from sentinel.memory.retriever import get_relevant_memories
from sentinel.models.memory_entry import MemoryEntry
from sentinel.models.risk_report import CausalLink, RiskReport
from sentinel.models.signal import Signal
from sentinel.optimiser.prompt_store import get_active_prompt
from sentinel.shared.pattern_reader import format_patterns_for_prompt

logger = structlog.get_logger(__name__)

CAUSAL_PROMPT_TEMPLATE = """You are a causal analysis expert for enterprise risk intelligence.

Given a risk signal and its assessment, build a causal chain that traces from the root cause through intermediate events to downstream effects.

Return a JSON object with:
- root_cause: a concise string identifying the fundamental root cause
- chain: a JSON array of objects, each with:
    - cause: string — the upstream cause or event
    - effect: string — the downstream consequence
    - confidence: float 0.0–1.0 — how confident you are in this causal link

Build 3–6 links in the chain, ordered from root cause to final downstream impact.
Think deeply about second- and third-order effects.

Return ONLY a JSON object. No explanation, no markdown fencing.
Example: {{"root_cause": "Unpatched software vulnerability", "chain": [{{"cause": "Unpatched vulnerability discovered", "effect": "Exploit code published publicly", "confidence": 0.95}}, {{"cause": "Exploit code available", "effect": "Threat actors begin active scanning", "confidence": 0.88}}]}}

SIGNAL TITLE: {title}
SIGNAL SOURCE: {source}
SIGNAL CATEGORY: {category}
SIGNAL PRIORITY: {priority}

SIGNAL CONTENT:
{content}

RISK ASSESSMENT:
- Impact: {impact}
- Probability: {probability}
- Exposure: {exposure}
- Overall Score: {overall}
- Evidence: {evidence}
- Summary: {summary}

PAST SIMILAR EVENTS (from memory):
{memory_context}

CROSS-COMPANY INTELLIGENCE (anonymised patterns from other organisations):
{shared_context}
"""


class CausalChainBuilder(BaseAgent):
    """Builds causal chains for risk reports via Gemini with deep reasoning.

    For each RiskReport in state, identifies the root cause and constructs
    a chain of cause → effect links with confidence scores.
    """

    agent_name: str = "CausalChainBuilder"

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute causal chain building — LangGraph node entry point."""
        reports: list[RiskReport] = state.get("risk_reports", [])
        signals: list[Signal] = state.get("signals", [])

        # Build signal lookup for enriching prompts
        signal_map: dict[str, Signal] = {s.id: s for s in signals}

        self.log.info("causal_chain.start", report_count=len(reports))

        updated_reports: list[RiskReport] = []
        for report in reports:
            # Skip reports that already have causal chains (Loop 2 re-run)
            if report.causal_chain:
                self.log.debug(
                    "causal_chain.skip.existing", report_id=report.id
                )
                updated_reports.append(report)
                continue

            signal = signal_map.get(report.signal_id)
            if not signal:
                self.log.warning(
                    "causal_chain.no_signal", report_id=report.id
                )
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
                    "causal_chain.memory",
                    signal_id=str(signal.id),
                    memories_found=len(memories),
                )

                # Level 6: read cross-company shared patterns from state
                shared_patterns = state.get("shared_patterns", [])

                root_cause, chain = await self._build_chain(
                    signal, report, memories, shared_patterns=shared_patterns
                )
                report.root_cause = root_cause
                report.causal_chain = chain

                self.log.info(
                    "causal_chain.report.done",
                    report_id=report.id,
                    root_cause=root_cause[:80],
                    chain_length=len(chain),
                )
            except Exception:
                self.log.exception(
                    "causal_chain.report.error", report_id=report.id
                )

            updated_reports.append(report)

        self.log.info("causal_chain.done", total_reports=len(updated_reports))
        return {"risk_reports": updated_reports}

    async def _build_chain(
        self, signal: Signal, report: RiskReport,
        memories: list[MemoryEntry] | None = None,
        shared_patterns: list | None = None,
    ) -> tuple[str, list[CausalLink]]:
        """Build causal chain for a single report via LLM.

        Args:
            signal:          Processed Signal.
            report:          RiskReport from RiskAssessor.
            memories:        Past similar events from Qdrant memory (Level 3).
            shared_patterns: Cross-company anonymised patterns (Level 6).

        Returns (root_cause, list_of_CausalLink).
        """
        # Build memory context string
        if memories:
            memory_lines = []
            for m in memories:
                memory_lines.append(
                    f"- [{m.priority}] {m.title} (risk={m.risk_score:.1f}, "
                    f"entities={', '.join(m.entities[:3])}, "
                    f"route={m.route_path})"
                )
            memory_context = "\n".join(memory_lines)
        else:
            memory_context = "No past events found."
        entity_str = "None"
        if signal.entities:
            entity_str = ", ".join(
                f"{e.name} ({e.entity_type})" for e in signal.entities
            )

        template = await get_active_prompt("CausalChainBuilder", default=CAUSAL_PROMPT_TEMPLATE)

        # Build shared patterns context (Level 6)
        shared_context = format_patterns_for_prompt(shared_patterns or [])
        if not shared_context:
            shared_context = "No cross-company patterns available."

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
            memory_context=memory_context,
            shared_context=shared_context,
        )

        # Thinking ON for CausalChainBuilder (deep reasoning)
        raw_response = await self.llm_complete(prompt, thinking=True)

        return self._parse_chain(raw_response)

    def _parse_chain(self, raw: str) -> tuple[str, list[CausalLink]]:
        """Parse LLM JSON response into root_cause + CausalLink list."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            self.log.warning(
                "causal_chain.parse.invalid_json", raw=cleaned[:200]
            )
            return ("Unable to determine root cause", [])

        root_cause = str(data.get("root_cause", "Unknown root cause"))

        chain_data = data.get("chain", [])
        if not isinstance(chain_data, list):
            return (root_cause, [])

        links: list[CausalLink] = []
        for item in chain_data:
            if not isinstance(item, dict):
                continue
            try:
                conf = float(item.get("confidence", 0.0))
                conf = max(0.0, min(1.0, conf))
                links.append(
                    CausalLink(
                        cause=str(item.get("cause", "")),
                        effect=str(item.get("effect", "")),
                        confidence=conf,
                    )
                )
            except (ValueError, TypeError):
                self.log.warning(
                    "causal_chain.parse.bad_link", item=str(item)[:100]
                )

        return (root_cause, links)
