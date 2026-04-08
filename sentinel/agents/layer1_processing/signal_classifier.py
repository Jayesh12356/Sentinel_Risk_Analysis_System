"""SignalClassifier — Layer 1 processing agent for signal prioritisation.

Uses Gemini via sentinel/llm/client.py to classify each signal into
P0/P1/P2/P3 priority levels, assign a confidence score, and determine
a risk category.

Per CONTEXT.md:
- Thinking OFF (fast + cheap)
- Updates signal.priority, signal.confidence, signal.category
- Increments loop1_count in state when Loop 1 triggers (confidence < 0.5)
- Signal Priority Levels:
    P0 = Critical → instant alert
    P1 = High → daily digest
    P2 = Medium → weekly report
    P3 = Low → logged only
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from sentinel.agents.base import BaseAgent
from sentinel.models.signal import Signal, SignalPriority
from sentinel.optimiser.prompt_store import get_active_prompt
from sentinel.feedback.weights import get_confidence_multiplier

logger = structlog.get_logger(__name__)

CLASSIFY_PROMPT_TEMPLATE = """You are a risk intelligence signal classifier for an enterprise risk system.

Classify the following signal and return a JSON object with these fields:
- priority: one of "P0", "P1", "P2", "P3"
    P0 = Critical — active exploits, immediate financial/security threat, regulatory action in progress
    P1 = High — significant risk requiring prompt attention within 24h
    P2 = Medium — notable risk for weekly review
    P3 = Low — informational, log only
- confidence: a float 0.0–1.0 indicating your confidence in this classification
    0.85–1.00 = High confidence
    0.60–0.84 = Moderate confidence
    0.40–0.59 = Low confidence (will trigger re-analysis)
    < 0.40 = Insufficient data
- category: one of "cyber", "financial", "geopolitical", "regulatory", "operational", "reputational", "supply_chain"
- reasoning: a brief 1-2 sentence explanation of your classification

Return ONLY a JSON object. No explanation, no markdown fencing.
Example: {{"priority": "P1", "confidence": 0.82, "category": "cyber", "reasoning": "Active vulnerability with known exploits but patches available."}}

SIGNAL TITLE: {title}

SIGNAL SOURCE: {source}

SIGNAL CONTENT:
{content}

ENTITIES FOUND:
{entities}
"""


class SignalClassifier(BaseAgent):
    """Classifies signals into priority levels via Gemini LLM.

    Enriches each Signal in state["signals"] by setting:
    - priority (P0–P3)
    - confidence (0–1)
    - category (risk domain)

    Also increments loop1_count for Loop 1 awareness.
    """

    agent_name: str = "SignalClassifier"

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute signal classification — LangGraph node entry point."""
        signals: list[Signal] = state.get("signals", [])
        loop1_count: int = state.get("loop1_count", 0)

        self.log.info(
            "signal_classifier.start",
            signal_count=len(signals),
            loop1_count=loop1_count,
        )

        classified: list[Signal] = []
        for signal in signals:
            try:
                result = await self._classify_signal(signal)
                signal.priority = result["priority"]
                signal.confidence = result["confidence"]
                signal.category = result["category"]

                self.log.info(
                    "signal_classifier.signal.done",
                    signal_id=signal.id,
                    priority=signal.priority.value,
                    confidence=signal.confidence,
                    category=signal.category,
                )
            except Exception:
                self.log.exception(
                    "signal_classifier.signal.error", signal_id=signal.id
                )
                # Default to P3/low confidence on failure
                signal.priority = SignalPriority.P3
                signal.confidence = 0.0
            else:
                # Apply human feedback confidence multiplier (Level 5)
                source_str = signal.source.value if hasattr(signal.source, "value") else str(signal.source)
                multiplier = get_confidence_multiplier(source_str)
                original_conf = signal.confidence
                if multiplier != 1.0:
                    signal.confidence = max(0.0, min(1.0, original_conf * multiplier))
                    self.log.info(
                        "signal_classifier.feedback_weight_applied",
                        signal_id=signal.id,
                        source=source_str,
                        multiplier=multiplier,
                        confidence_before=original_conf,
                        confidence_after=signal.confidence,
                    )
            classified.append(signal)

        # Increment loop1_count so the conditional edge knows we've run
        new_loop1_count = loop1_count + 1

        self.log.info(
            "signal_classifier.done",
            total=len(classified),
            loop1_count=new_loop1_count,
        )

        return {
            "signals": classified,
            "loop1_count": new_loop1_count,
        }

    async def _classify_signal(self, signal: Signal) -> dict[str, Any]:
        """Classify a single signal via LLM.

        Returns dict with priority, confidence, category, reasoning.
        """
        # Format entities for context
        entity_str = "None"
        if signal.entities:
            entity_str = ", ".join(
                f"{e.name} ({e.entity_type})" for e in signal.entities
            )

        template = await get_active_prompt("SignalClassifier", default=CLASSIFY_PROMPT_TEMPLATE)
        prompt = template.format(
            title=signal.title,
            source=signal.source.value,
            content=signal.content,
            entities=entity_str,
        )

        # Thinking OFF for SignalClassifier (fast + cheap)
        raw_response = await self.llm_complete(prompt, thinking=False)

        return self._parse_classification(raw_response)

    def _parse_classification(self, raw: str) -> dict[str, Any]:
        """Parse LLM JSON response into classification dict.

        Returns safe defaults on parse failure.
        """
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            self.log.warning(
                "signal_classifier.parse.invalid_json", raw=cleaned[:200]
            )
            return {
                "priority": SignalPriority.P3,
                "confidence": 0.0,
                "category": "unknown",
                "reasoning": "Failed to parse LLM response",
            }

        # Parse priority
        priority_str = str(data.get("priority", "P3")).upper()
        try:
            priority = SignalPriority(priority_str)
        except ValueError:
            priority = SignalPriority.P3

        # Parse confidence
        try:
            confidence = float(data.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.0

        return {
            "priority": priority,
            "confidence": confidence,
            "category": str(data.get("category", "unknown")),
            "reasoning": str(data.get("reasoning", "")),
        }
