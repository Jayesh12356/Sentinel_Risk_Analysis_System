"""EntityExtractor — Layer 1 processing agent for Named Entity Recognition.

Uses Gemini via sentinel/llm/client.py to extract structured entities
(ORG, PERSON, CVE, PRODUCT, LOCATION, etc.) from each signal's content.

Per CONTEXT.md:
- Thinking OFF (fast + cheap)
- All LLM calls through sentinel/llm/client.py
- Populates signal.entities with Entity objects
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from sentinel.agents.base import BaseAgent
from sentinel.models.signal import Entity, Signal
from sentinel.optimiser.prompt_store import get_active_prompt

logger = structlog.get_logger(__name__)

NER_PROMPT_TEMPLATE = """You are a Named Entity Recognition (NER) system for enterprise risk intelligence.

Extract all named entities from the following text. For each entity, provide:
- name: the entity's display name
- entity_type: one of ORG, PERSON, CVE, PRODUCT, LOCATION, EVENT, REGULATION, METRIC
- relevance: a float 0.0–1.0 indicating how relevant this entity is to risk assessment

Return ONLY a JSON array of objects. No explanation, no markdown fencing.
Example: [{"name": "Apache Log4j", "entity_type": "PRODUCT", "relevance": 0.95}]

If no entities are found, return an empty array: []

TEXT:
{text}
"""


class EntityExtractor(BaseAgent):
    """Extracts named entities from signals via Gemini LLM.

    Enriches each Signal in state["signals"] by populating its
    `entities` field with a list of Entity objects.
    """

    agent_name: str = "EntityExtractor"

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute entity extraction — LangGraph node entry point."""
        signals: list[Signal] = state.get("signals", [])
        self.log.info("entity_extractor.start", signal_count=len(signals))

        enriched: list[Signal] = []
        for signal in signals:
            try:
                entities = await self._extract_entities(signal)
                # Update signal with extracted entities
                signal.entities = entities
                self.log.info(
                    "entity_extractor.signal.done",
                    signal_id=signal.id,
                    entity_count=len(entities),
                )
            except Exception:
                self.log.exception(
                    "entity_extractor.signal.error", signal_id=signal.id
                )
                # Keep signal with empty entities on failure
            enriched.append(signal)

        self.log.info("entity_extractor.done", total_signals=len(enriched))
        return {"signals": enriched}

    async def _extract_entities(self, signal: Signal) -> list[Entity]:
        """Extract entities from a single signal via LLM.

        Args:
            signal: The Signal to extract entities from.

        Returns:
            List of Entity objects parsed from LLM response.
        """
        # Combine title + content for richer extraction
        text = f"{signal.title}\n\n{signal.content}"

        template = await get_active_prompt("EntityExtractor", default=NER_PROMPT_TEMPLATE)
        prompt = template.format(text=text)

        # Thinking OFF for EntityExtractor (fast + cheap)
        raw_response = await self.llm_complete(prompt, thinking=False)

        return self._parse_entities(raw_response)

    def _parse_entities(self, raw: str) -> list[Entity]:
        """Parse LLM JSON response into Entity objects.

        Handles edge cases: markdown fences, partial JSON, empty responses.
        """
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first and last lines (fences)
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        if not cleaned:
            return []

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            self.log.warning("entity_extractor.parse.invalid_json", raw=cleaned[:200])
            return []

        if not isinstance(data, list):
            self.log.warning("entity_extractor.parse.not_list", type=type(data).__name__)
            return []

        entities: list[Entity] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                entities.append(
                    Entity(
                        name=str(item.get("name", "")),
                        entity_type=str(item.get("entity_type", "UNKNOWN")),
                        relevance=float(item.get("relevance", 0.0)),
                    )
                )
            except (ValueError, TypeError):
                self.log.warning(
                    "entity_extractor.parse.bad_entity", item=str(item)[:100]
                )

        return entities
